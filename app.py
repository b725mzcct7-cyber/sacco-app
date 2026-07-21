import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps

# ---------------------------------------------------------
# 1. INITIALIZE FLASK APP
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'canan_bbosa_ventures_sacco_secret')

# Retrieve PostgreSQL URL from Render environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')


# ---------------------------------------------------------
# 2. DATABASE HELPER & INITIALIZATION
# ---------------------------------------------------------
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing in Render settings.")
        
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn


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

        # Guarantee Admin Account
        cur.execute('''
            INSERT INTO users (full_name, username, password, role, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET password = EXCLUDED.password, role = EXCLUDED.role, status = EXCLUDED.status;
        ''', ('Canan Bbosa Admin', 'admin', 'admin123', 'admin', 'approved'))
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database tables initialized successfully.")
    except Exception as e:
        print("Database init warning/error:", e)

init_db()


# ---------------------------------------------------------
# 3. AUTH & DECORATOR HELPERS
# ---------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or str(session['user'].get('role', '')).lower().strip() != 'admin':
            flash("Admin privilege required.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
# 4. APPLICATION ROUTES
# ---------------------------------------------------------

@app.route('/')
def home():
    if 'user' in session:
        user_role = str(session['user'].get('role', '')).lower().strip()
        if user_role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('staff_dashboard'))
    return redirect(url_for('login'))


# --- LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and 'user' in session:
        role = str(session['user'].get('role', '')).lower().strip()
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('staff_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) AND TRIM(password) = %s", 
                (username, password)
            )
            user_row = cur.fetchone()
            cur.close()
            conn.close()
            
            if user_row:
                user_dict = dict(user_row)
                role = str(user_dict.get('role', 'staff')).lower().strip()
                raw_status = user_dict.get('status')
                status = str(raw_status).lower().strip() if raw_status else 'approved'
                
                if role != 'admin' and status not in ['approved', 'none', 'null', '']:
                    session.clear()
                    flash('Your account is pending approval by Canan Bbosa Ventures admin.', 'warning')
                    return redirect(url_for('login'))

                # Clear session to prevent cross-role contamination
                session.clear()
                
                session['user'] = {
                    'id': user_dict.get('id'),
                    'full_name': user_dict.get('full_name'),
                    'username': str(user_dict.get('username')).strip(),
                    'role': role,
                    'status': status
                }
                
                if role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid username or password.', 'danger')
                return redirect(url_for('login'))
        except Exception as e:
            if conn: conn.rollback(); conn.close()
            flash(f'Login Database Error: {e}', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')


# --- REGISTER / SIGNUP ROUTE ---
@app.route('/register', methods=['GET', 'POST'])
@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))
            
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute('SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))', (username,))
            existing_user = cur.fetchone()
            
            if existing_user:
                cur.close()
                conn.close()
                flash('Username already exists. Please select another.', 'warning')
                return redirect(url_for('register'))
                
            cur.execute(
                'INSERT INTO users (full_name, username, password, role, status) VALUES (%s, %s, %s, %s, %s)',
                (full_name, username, password, 'staff', 'pending')
            )
            conn.commit()
            cur.close()
            conn.close()
            
            flash('Registration successful! Account is pending admin approval.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            if conn: conn.rollback(); conn.close()
            flash(f'Error creating account: {e}', 'danger')

    return render_template('signup.html')


# --- STAFF DASHBOARD ---
@app.route('/dashboard', methods=['GET', 'POST'])
@app.route('/staff_dashboard', methods=['GET', 'POST'])
@login_required
def staff_dashboard():
    username = session['user'].get('username', '').strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))", (username,))
    db_user = cur.fetchone()

    if not db_user:
        cur.close()
        conn.close()
        session.clear()
        return redirect(url_for('login'))

    user_dict = dict(db_user)
    role = str(user_dict.get('role', 'staff')).lower().strip()

    if role == 'admin':
        cur.close()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Handle Deposit Submission
    if request.method == 'POST':
        amount = request.form.get('amount')
        frequency = request.form.get('frequency', 'Weekly')
        date_str = request.form.get('date')

        if amount and float(amount) > 0:
            try:
                cur.execute(
                    "INSERT INTO transactions (username, amount, frequency, date, status) VALUES (%s, %s, %s, %s, %s)",
                    (username, float(amount), frequency, date_str, 'pending')
                )
                conn.commit()
                flash('Deposit request submitted! Awaiting admin confirmation.', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Failed to record deposit: {e}', 'danger')
        else:
            flash('Please enter a valid deposit amount.', 'danger')
        
        cur.close()
        conn.close()
        return redirect(url_for('staff_dashboard'))

    # Fetch User Transactions & Balances
    try:
        cur.execute('SELECT * FROM transactions WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) ORDER BY id DESC', (username,))
        user_txs = cur.fetchall()
    except Exception:
        conn.rollback()
        user_txs = []

    try:
        cur.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total 
            FROM transactions 
            WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) 
              AND LOWER(TRIM(status)) = 'approved'
            """, 
            (username,)
        )
        res = cur.fetchone()
        balance = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        balance = 0.0

    try:
        cur.execute(
            """
            SELECT id, date, amount, username AS recipient, notes AS cycle 
            FROM payouts 
            WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) 
            ORDER BY id DESC
            """, 
            (username,)
        )
        my_payouts = cur.fetchall()
    except Exception:
        conn.rollback()
        my_payouts = []

    cur.close()
    conn.close()
    
    return render_template(
        'staff.html', 
        user=user_dict, 
        transactions=user_txs, 
        balance=balance, 
        my_payouts=my_payouts
    )


@app.route('/deposit', methods=['GET', 'POST'])
@app.route('/make_payment', methods=['GET', 'POST'])
@login_required
def make_payment():
    return staff_dashboard()


# --- ADMIN DASHBOARD ---
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    username = session['user'].get('username', '').strip()
    
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM users WHERE LOWER(TRIM(status)) = 'pending' AND (LOWER(TRIM(role)) != 'admin' OR role IS NULL) ORDER BY id DESC")
        pending_users = cur.fetchall()
    except Exception:
        conn.rollback()
        pending_users = []

    try:
        cur.execute("SELECT * FROM users WHERE (LOWER(TRIM(status)) = 'approved' OR status IS NULL) AND (LOWER(TRIM(role)) != 'admin' OR role IS NULL) ORDER BY id DESC")
        staff_list = cur.fetchall()
    except Exception:
        conn.rollback()
        staff_list = []

    try:
        cur.execute("SELECT * FROM transactions ORDER BY id DESC")
        transactions = cur.fetchall()
    except Exception:
        conn.rollback()
        transactions = []

    try:
        cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE LOWER(TRIM(status)) = 'approved'")
        res = cur.fetchone()
        approved = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        approved = 0.0

    try:
        cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE LOWER(TRIM(status)) = 'pending'")
        res = cur.fetchone()
        pending = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        pending = 0.0

    try:
        cur.execute("SELECT * FROM payouts ORDER BY id DESC")
        payout_history = cur.fetchall()
    except Exception:
        conn.rollback()
        payout_history = []

    try:
        cur.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payouts")
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


# --- DISBURSE PAYOUTS QUEUE ROUTE (FOR ROTATION QUEUE) ---
@app.route('/admin/disburse_payouts', methods=['POST'])
@admin_required
def disburse_payouts():
    payout_date = request.form.get('payout_date')
    notes = request.form.get('notes', 'Rotation Payout Cycle')

    disbursed_count = 0
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Process multi-slot form values (e.g., staff_1 to staff_5)
        for i in range(1, 6):
            staff_username = request.form.get(f'staff_{i}')
            amount = request.form.get(f'amount_{i}')

            if staff_username and amount:
                try:
                    amount_val = float(amount)
                    if amount_val > 0:
                        cur.execute(
                            "INSERT INTO payouts (username, amount, date, notes) VALUES (%s, %s, %s, %s)",
                            (staff_username.strip(), amount_val, payout_date, notes)
                        )
                        disbursed_count += 1
                except ValueError:
                    continue

        conn.commit()
        if disbursed_count > 0:
            flash(f"Successfully disbursed rotation payout for {disbursed_count} staff member(s).", "success")
        else:
            flash("No valid amounts submitted for disbursement.", "warning")
    except Exception as e:
        conn.rollback()
        flash(f"Error processing payouts: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    # STRICT FIX: Always redirect directly back to admin dashboard
    return redirect(url_for('admin_dashboard'))


# --- DIRECT SINGLE PAYOUT ROUTE ---
@app.route('/admin/add_payout', methods=['POST'])
@admin_required
def add_payout():
    username = request.form.get('username', '').strip()
    amount = request.form.get('amount')
    date_str = request.form.get('date')
    notes = request.form.get('notes', 'Direct Payout')

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
            flash(f'Payout of UGX {float(amount):,.2f} recorded for {username}!', 'success')
        except Exception as e:
            flash(f'Error adding payout: {e}', 'danger')
    else:
        flash('Please fill in a valid payout amount and username.', 'danger')

    return redirect(url_for('admin_dashboard'))


# --- MEMBER LEDGER VIEW ---
@app.route('/admin/member/<username>', methods=['GET', 'POST'])
@app.route('/ledger/<username>', methods=['GET', 'POST'])
@admin_required
def view_member_ledger(username):
    conn = get_db_connection()
    cur = conn.cursor()
    target_username = str(username).strip()

    # Password Reset Action
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        if new_password:
            try:
                cur.execute(
                    "UPDATE users SET password = %s WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))", 
                    (new_password, target_username)
                )
                conn.commit()
                flash(f'Password for {target_username} updated successfully!', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Failed to update password: {e}', 'danger')
        else:
            flash('Password cannot be empty.', 'danger')

    # Profile Data
    try:
        cur.execute("SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))", (target_username,))
        member_row = cur.fetchone()
        member_data = dict(member_row) if member_row else {'username': target_username, 'full_name': target_username}
    except Exception:
        conn.rollback()
        member_data = {'username': target_username, 'full_name': target_username}

    # Member Transactions
    try:
        cur.execute("SELECT * FROM transactions WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) ORDER BY id DESC", (target_username,))
        transactions = cur.fetchall()
    except Exception:
        conn.rollback()
        transactions = []

    # Member Approved Deposits
    try:
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) AND LOWER(TRIM(status)) = 'approved'", 
            (target_username,)
        )
        res = cur.fetchone()
        approved_total = float(res['total']) if res and res['total'] is not None else 0.0
    except Exception:
        conn.rollback()
        approved_total = 0.0

    # Member Pending Deposits
    try:
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) AND LOWER(TRIM(status)) = 'pending'", 
            (target_username,)
        )
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


# --- APPROVE USER REGISTRATION ---
@app.route('/admin/approve_user/<username>')
@admin_required
def approve_user(username):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'approved' WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))", (username,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Account for {username} approved successfully!', 'success')
    except Exception as e:
        flash(f'Approval error: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- DELETE USER / REMOVE STAFF MEMBER ---
@app.route('/admin/delete_user/<username>')
@admin_required
def delete_user(username):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) AND LOWER(TRIM(role)) != 'admin'", (username,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Staff member "{username}" removed permanently.', 'info')
    except Exception as e:
        flash(f'Error deleting staff member: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- APPROVE DEPOSIT TRANSACTION ---
@app.route('/admin/approve_tx/<int:tx_id>')
@admin_required
def approve_tx(tx_id):
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


# --- DELETE TRANSACTION RECORD ---
@app.route('/admin/delete_tx/<int:tx_id>')
@admin_required
def delete_tx(tx_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Transaction #{tx_id} removed permanently!', 'warning')
    except Exception as e:
        flash(f'Deletion error: {e}', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- LOGOUT ROUTE ---
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)