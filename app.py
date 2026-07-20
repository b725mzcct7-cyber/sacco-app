import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session

# ---------------------------------------------------------
# 1. INITIALIZE FLASK APP
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = 'sacco_secret_key_here'

# Retrieve PostgreSQL URL from Render environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')


# ---------------------------------------------------------
# 2. DATABASE HELPER & INITIALIZATION
# ---------------------------------------------------------
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing in Render settings.")
        
    url = DATABASE_URL
    # Fix legacy postgres:// URL scheme if passed by Render
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Users Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT,
                status TEXT
            );
        ''')
        
        # 2. Transactions Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                username TEXT,
                amount NUMERIC,
                frequency TEXT,
                date TEXT,
                status TEXT
            );
        ''')
        
        # 3. Payouts Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS payouts (
                id SERIAL PRIMARY KEY,
                username TEXT,
                amount NUMERIC,
                date TEXT,
                notes TEXT
            );
        ''')
        
        conn.commit()

        # Guarantee Admin Account exists and credentials match admin/admin123
        cur.execute('''
            INSERT INTO users (full_name, username, password, role, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET password = EXCLUDED.password, role = EXCLUDED.role, status = EXCLUDED.status;
        ''', ('Administrator', 'admin', 'admin123', 'admin', 'approved'))
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database tables verified & admin account ready.")
    except Exception as e:
        print("Database initialization notice/error:", e)

# Run database setup safely on app boot
init_db()


# ---------------------------------------------------------
# 3. APPLICATION ROUTES
# ---------------------------------------------------------

@app.route('/')
def home():
    return redirect(url_for('login'))


# --- LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                'SELECT * FROM users WHERE LOWER(username) = LOWER(%s) AND password = %s', 
                (username, password)
            )
            user_row = cur.fetchone()
            cur.close()
            conn.close()
            
            if user_row:
                user_dict = dict(user_row)
                role = str(user_dict.get('role', 'staff')).lower()
                raw_status = user_dict.get('status')
                status = str(raw_status).lower() if raw_status else 'approved'
                
                if role == 'admin':
                    session['user'] = user_dict
                    return redirect(url_for('admin_dashboard'))
                
                if status in ['approved', 'none', 'null']:
                    session['user'] = user_dict
                    return redirect(url_for('staff_dashboard'))
                else:
                    flash('Your account is pending admin approval.', 'warning')
                    return redirect(url_for('login'))
            else:
                flash('Invalid username or password.', 'danger')
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Database login error: {e}', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')


# --- REGISTER / SIGNUP ROUTE ---
@app.route('/register', methods=['GET', 'POST'])
@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(%s)', (username,))
            existing_user = cur.fetchone()
            
            if existing_user:
                cur.close()
                conn.close()
                flash('Username already exists. Please choose another.', 'warning')
                return redirect(url_for('register'))
                
            cur.execute(
                'INSERT INTO users (full_name, username, password, role, status) VALUES (%s, %s, %s, %s, %s)',
                (full_name, username, password, 'staff', 'pending')
            )
            conn.commit()
            cur.close()
            conn.close()
            
            flash('Registration successful! Pending admin approval.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error creating account: {e}', 'danger')

    return render_template('signup.html')


# --- STAFF DASHBOARD (VIEW TRANSACTIONS & SUBMIT DEPOSITS) ---
@app.route('/dashboard', methods=['GET', 'POST'])
@app.route('/staff_dashboard', methods=['GET', 'POST'])
def staff_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    user = session.get('user', {})
    username = user.get('username', '')
    
    conn = get_db_connection()
    cur = conn.cursor()

    # Process Deposit Form Submission
    if request.method == 'POST':
        amount = request.form.get('amount')
        frequency = request.form.get('frequency', 'Monthly')
        date_str = request.form.get('date')

        if amount and float(amount) > 0:
            try:
                cur.execute(
                    "INSERT INTO transactions (username, amount, frequency, date, status) VALUES (%s, %s, %s, %s, %s)",
                    (username, float(amount), frequency, date_str, 'pending')
                )
                conn.commit()
                flash('Deposit submitted successfully! Awaiting admin approval.', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Failed to submit deposit: {e}', 'danger')
        else:
            flash('Please enter a valid deposit amount.', 'danger')
        return redirect(url_for('staff_dashboard'))

    # Fetch User Transactions
    try:
        cur.execute('SELECT * FROM transactions WHERE LOWER(username) = LOWER(%s) ORDER BY id DESC', (username,))
        user_txs = cur.fetchall()
    except Exception:
        conn.rollback()
        user_txs = []

    # Calculate User Totals
    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(username) = LOWER(%s) AND LOWER(status) = 'approved'", (username,))
        res = cur.fetchone()
        total_approved = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        total_approved = 0.0

    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(username) = LOWER(%s) AND LOWER(status) = 'pending'", (username,))
        res = cur.fetchone()
        total_pending = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        total_pending = 0.0

    cur.close()
    conn.close()
    
    return render_template(
        'staff.html', 
        user=user, 
        transactions=user_txs, 
        total_approved=total_approved, 
        total_pending=total_pending
    )


# --- DEPOSIT / PAYMENT ROUTE REDIRECT ---
@app.route('/deposit', methods=['GET', 'POST'])
@app.route('/make_payment', methods=['GET', 'POST'])
def make_payment():
    return staff_dashboard()


# --- ADMIN DASHBOARD ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pending Approval Users
    try:
        cur.execute("SELECT * FROM users WHERE LOWER(status) = 'pending' AND (LOWER(role) != 'admin' OR role IS NULL)")
        pending_users = cur.fetchall()
    except Exception:
        conn.rollback()
        pending_users = []

    # Approved Staff List
    try:
        cur.execute("SELECT * FROM users WHERE (LOWER(status) = 'approved' OR status IS NULL) AND (LOWER(role) != 'admin' OR role IS NULL)")
        staff_list = cur.fetchall()
    except Exception:
        conn.rollback()
        staff_list = []

    # All Transactions
    try:
        cur.execute("SELECT * FROM transactions ORDER BY id DESC")
        transactions = cur.fetchall()
    except Exception:
        conn.rollback()
        transactions = []

    # Vault & Summary Calculations
    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(status) = 'approved'")
        res = cur.fetchone()
        approved = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        approved = 0.0

    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(status) = 'pending'")
        res = cur.fetchone()
        pending = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        pending = 0.0

    # Payouts History
    try:
        cur.execute("SELECT * FROM payouts ORDER BY id DESC")
        payout_history = cur.fetchall()
    except Exception:
        conn.rollback()
        payout_history = []

    try:
        cur.execute("SELECT SUM(amount) AS total FROM payouts")
        res = cur.fetchone()
        total_paid_out = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        total_paid_out = 0.0

    reserve_vault = float(approved) - float(total_paid_out)
    
    cur.close()
    conn.close()
    
    return render_template(
        'admin.html', 
        pending_users=pending_users, 
        staff_list=staff_list, 
        transactions=transactions,
        approved=approved,
        pending=pending,
        total_paid_out=total_paid_out,
        reserve_vault=reserve_vault,
        payout_history=payout_history
    )


# --- ADMIN ADD PAYOUT ROUTE ---
@app.route('/admin/add_payout', methods=['POST'])
def add_payout():
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    username = request.form.get('username', '').strip()
    amount = request.form.get('amount')
    date_str = request.form.get('date')
    notes = request.form.get('notes', '')

    if username and amount and float(amount) > 0:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO payouts (username, amount, date, notes) VALUES (%s, %s, %s, %s)",
                (username, float(amount), date_str, notes)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash(f'Payout of {amount} recorded for {username}!', 'success')
        except Exception as e:
            flash(f'Error adding payout: {e}', 'danger')
    else:
        flash('Please fill in a valid payout amount and username.', 'danger')

    return redirect(url_for('admin_dashboard'))


# --- ADMIN MEMBER LEDGER & PASSWORD RESET ROUTE ---
@app.route('/admin/member/<username>', methods=['GET', 'POST'])
@app.route('/ledger/<username>', methods=['GET', 'POST'])
def view_member_ledger(username):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    target_username = str(username).strip()

    # Process Password Reset if submitted
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        if new_password:
            try:
                cur.execute(
                    "UPDATE users SET password = %s WHERE LOWER(username) = LOWER(%s)", 
                    (new_password, target_username)
                )
                conn.commit()
                flash(f'Password for {target_username} updated successfully!', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Failed to update password: {e}', 'danger')
        else:
            flash('Password cannot be empty.', 'danger')

    # Member Profile Info
    try:
        cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (target_username,))
        member_row = cur.fetchone()
        member_data = dict(member_row) if member_row else {'username': target_username, 'full_name': target_username}
    except Exception:
        conn.rollback()
        member_data = {'username': target_username, 'full_name': target_username}

    # Member Transactions
    try:
        cur.execute("SELECT * FROM transactions WHERE LOWER(username) = LOWER(%s) ORDER BY id DESC", (target_username,))
        transactions = cur.fetchall()
    except Exception:
        conn.rollback()
        transactions = []

    # Member Totals
    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(username) = LOWER(%s) AND LOWER(status) = 'approved'", (target_username,))
        res = cur.fetchone()
        approved_total = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        approved_total = 0.0

    try:
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE LOWER(username) = LOWER(%s) AND LOWER(status) = 'pending'", (target_username,))
        res = cur.fetchone()
        pending_total = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        pending_total = 0.0

    cur.close()
    conn.close()

    return render_template(
        'member_detail.html', 
        member=member_data, 
        transactions=transactions, 
        approved_total=approved_total,
        pending_total=pending_total
    )


# --- APPROVE USER ROUTE ---
@app.route('/admin/approve_user/<username>')
def approve_user(username):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'approved' WHERE LOWER(username) = LOWER(%s)", (username,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Account for {username} approved!', 'success')
    except Exception as e:
        flash(f'Approval error: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- APPROVE TRANSACTION ROUTE ---
@app.route('/admin/approve_tx/<int:tx_id>')
def approve_tx(tx_id):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE transactions SET status = 'approved' WHERE id = %s", (tx_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Transaction #{tx_id} approved!', 'success')
    except Exception as e:
        flash(f'Approval error: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- DELETE TRANSACTION ROUTE ---
@app.route('/admin/delete_tx/<int:tx_id>')
def delete_tx(tx_id):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Transaction #{tx_id} deleted permanently!', 'danger')
    except Exception as e:
        flash(f'Deletion error: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- LOGOUT ROUTE ---
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)