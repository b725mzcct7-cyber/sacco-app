import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session

# 1. INITIALIZE FLASK
app = Flask(__name__)
app.secret_key = 'sacco_secret_key_here'


# 2. DATABASE HELPER & INITIALIZATION
def get_db_connection():
    conn = sqlite3.connect('sacco.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Ensure standard tables exist
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            status TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            amount REAL,
            frequency TEXT,
            date TEXT,
            status TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            amount REAL,
            date TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize tables when starting up
init_db()


# --- 3. ROUTES ---

# --- ROOT HOME ROUTE ---
@app.route('/')
def home():
    return redirect(url_for('login'))


# --- LOGIN ROUTE (FIXED) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db_connection()
        # Case-insensitive username check
        user_row = conn.execute(
            'SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND password = ?', 
            (username, password)
        ).fetchone()
        conn.close()
        
        if user_row:
            user_dict = dict(user_row)
            role = str(user_dict.get('role', 'staff')).lower()
            raw_status = user_dict.get('status')
            status = str(raw_status).lower() if raw_status else 'approved'
            
            # Admin Login
            if role == 'admin':
                session['user'] = user_dict
                return redirect(url_for('admin_dashboard'))
            
            # Staff Login (Allows 'approved', 'none', or 'null')
            if status in ['approved', 'none', 'null']:
                session['user'] = user_dict
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('login'))
        else:
            flash('Invalid username or password.', 'danger')
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
            
        conn = get_db_connection()
        
        existing_user = conn.execute(
            'SELECT * FROM users WHERE LOWER(username) = LOWER(?)', 
            (username,)
        ).fetchone()
        
        if existing_user:
            conn.close()
            flash('Username already exists. Please choose another or login.', 'warning')
            return redirect(url_for('register'))
            
        try:
            conn.execute(
                'INSERT INTO users (full_name, username, password, role, status) VALUES (?, ?, ?, ?, ?)',
                (full_name, username, password, 'staff', 'pending')
            )
            conn.commit()
            conn.close()
            flash('Registration successful! Your account is pending admin approval.', 'success')
            return redirect(url_for('login'))
        except Exception:
            conn.close()
            try:
                conn = get_db_connection()
                conn.execute(
                    'INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)',
                    (username, password, 'staff', 'pending')
                )
                conn.commit()
                conn.close()
                flash('Registration successful! Your account is pending admin approval.', 'success')
                return redirect(url_for('login'))
            except Exception:
                flash('Error creating account. Please try again or contact administrator.', 'danger')
                return redirect(url_for('register'))

    return render_template('signup.html')


# --- STAFF DASHBOARD ROUTE ---
@app.route('/dashboard')
@app.route('/staff_dashboard')
def staff_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    user = session.get('user', {})
    username = user.get('username', '')
    
    conn = get_db_connection()
    
    try:
        user_txs = conn.execute(
            'SELECT * FROM transactions WHERE LOWER(username) = LOWER(?) ORDER BY id DESC', 
            (username,)
        ).fetchall()
    except Exception:
        user_txs = []
        
    try:
        approved_val = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE LOWER(username) = LOWER(?) AND LOWER(status) = 'approved'", 
            (username,)
        ).fetchone()[0]
        total_approved = approved_val if approved_val else 0
    except Exception:
        total_approved = 0

    try:
        pending_val = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE LOWER(username) = LOWER(?) AND LOWER(status) = 'pending'", 
            (username,)
        ).fetchone()[0]
        total_pending = pending_val if pending_val else 0
    except Exception:
        total_pending = 0

    conn.close()
    
    return render_template(
        'staff.html', 
        user=user, 
        transactions=user_txs, 
        total_approved=total_approved, 
        total_pending=total_pending
    )


# --- STAFF DEPOSIT / PAYMENT ROUTE ---
@app.route('/deposit', methods=['GET', 'POST'])
@app.route('/make_payment', methods=['GET', 'POST'])
def make_payment():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        amount = request.form.get('amount')
        frequency = request.form.get('frequency', 'Monthly')
        date_str = request.form.get('date')
        
        user = session.get('user', {})
        username = user.get('username')

        if not amount or float(amount) <= 0:
            flash('Please enter a valid deposit amount.', 'danger')
            return redirect(url_for('staff_dashboard'))

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO transactions (username, amount, frequency, date, status) VALUES (?, ?, ?, ?, ?)",
                (username, float(amount), frequency, date_str, 'pending')
            )
            conn.commit()
            flash('Deposit submitted successfully! Awaiting admin approval.', 'success')
        except Exception:
            flash('Failed to submit deposit. Please try again.', 'danger')
        finally:
            conn.close()

        return redirect(url_for('staff_dashboard'))

    return redirect(url_for('staff_dashboard'))


# --- ADMIN DASHBOARD ROUTE ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    try:
        pending_users = conn.execute(
            "SELECT * FROM users WHERE LOWER(status) = 'pending' AND (LOWER(role) != 'admin' OR role IS NULL)"
        ).fetchall()
    except Exception:
        pending_users = []
        
    try:
        staff_list = conn.execute(
            "SELECT * FROM users WHERE (LOWER(status) = 'approved' OR status IS NULL) AND (LOWER(role) != 'admin' OR role IS NULL)"
        ).fetchall()
    except Exception:
        staff_list = []

    try:
        transactions = conn.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    except Exception:
        transactions = []

    try:
        approved_val = conn.execute("SELECT SUM(amount) FROM transactions WHERE LOWER(status) = 'approved'").fetchone()[0]
        approved = approved_val if approved_val else 0
    except Exception:
        approved = 0

    try:
        pending_val = conn.execute("SELECT SUM(amount) FROM transactions WHERE LOWER(status) = 'pending'").fetchone()[0]
        pending = pending_val if pending_val else 0
    except Exception:
        pending = 0

    try:
        payout_history = conn.execute("SELECT * FROM payouts ORDER BY id DESC").fetchall()
    except Exception:
        payout_history = []

    try:
        total_paid_out_val = conn.execute("SELECT SUM(amount) FROM payouts").fetchone()[0]
        total_paid_out = total_paid_out_val if total_paid_out_val else 0
    except Exception:
        total_paid_out = 0

    reserve_vault = approved - total_paid_out
    
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


# --- ADMIN MEMBER LEDGER VIEW ROUTE (FIXED) ---
@app.route('/admin/member/<username>')
@app.route('/ledger/<username>')
def view_member_ledger(username):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    
    member_row = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    member_data = dict(member_row) if member_row else {'username': username}

    try:
        transactions = conn.execute(
            "SELECT * FROM transactions WHERE LOWER(username) = LOWER(?) ORDER BY id DESC", 
            (username,)
        ).fetchall()
    except Exception:
        transactions = []
    
    try:
        approved_val = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE LOWER(username) = LOWER(?) AND LOWER(status) = 'approved'", 
            (username,)
        ).fetchone()[0]
        approved_total = approved_val if approved_val else 0
    except Exception:
        approved_total = 0

    try:
        pending_val = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE LOWER(username) = LOWER(?) AND LOWER(status) = 'pending'", 
            (username,)
        ).fetchone()[0]
        pending_total = pending_val if pending_total else 0
    except Exception:
        pending_total = 0

    conn.close()

    return render_template(
        'member_detail.html', 
        member=member_data, 
        transactions=transactions, 
        approved_total=approved_total,
        pending_total=pending_total
    )


# --- APPROVE USER / STAFF ROUTE ---
@app.route('/admin/approve_user/<username>')
def approve_user(username):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    conn.execute("UPDATE users SET status = 'approved' WHERE LOWER(username) = LOWER(?)", (username,))
    conn.commit()
    conn.close()
    
    flash(f'Account for {username} has been approved!', 'success')
    return redirect(url_for('admin_dashboard'))


# --- APPROVE TRANSACTION ROUTE ---
@app.route('/admin/approve_tx/<int:tx_id>')
def approve_tx(tx_id):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    conn.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    
    flash(f'Transaction #{tx_id} approved!', 'success')
    return redirect(url_for('admin_dashboard'))


# --- DELETE TRANSACTION ROUTE ---
@app.route('/admin/delete_tx/<int:tx_id>')
def delete_tx(tx_id):
    if 'user' not in session or str(session['user'].get('role')).lower() != 'admin':
        return redirect(url_for('login'))
        
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        conn.close()
        flash(f'Transaction #{tx_id} deleted permanently!', 'danger')
    except Exception:
        flash('Could not delete transaction.', 'warning')
        
    return redirect(url_for('admin_dashboard'))


# --- LOGOUT ROUTE ---
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# --- APP RUNNER ---
if __name__ == '__main__':
    app.run(debug=True)