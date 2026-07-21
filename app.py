import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'canan_bbosa_ventures_sacco_secret')
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing in Render settings.")
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode=" not in url:
        url += "?sslmode=require" if "?" not in url else "&sslmode=require"
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT,
                status TEXT,
                phone TEXT,
                nin TEXT
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                username TEXT,
                amount NUMERIC,
                frequency TEXT,
                date TEXT,
                status TEXT,
                type TEXT DEFAULT 'deposit'
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS payouts (
                id SERIAL PRIMARY KEY,
                username TEXT,
                amount NUMERIC,
                date TEXT,
                notes TEXT
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS loans (
                id SERIAL PRIMARY KEY,
                username TEXT,
                amount NUMERIC,
                balance NUMERIC,
                status TEXT DEFAULT 'active',
                date TEXT
            );
        ''')
        conn.commit()
        cur.execute('''
            INSERT INTO users (full_name, username, password, role, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET password = EXCLUDED.password, role = EXCLUDED.role, status = EXCLUDED.status;
        ''', ('Canan Bbosa Admin', 'admin', 'admin123', 'admin', 'approved'))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("DB Init Error:", e)

try:
    init_db()
except Exception:
    pass

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

@app.route('/')
def home():
    if 'user' in session:
        if str(session['user'].get('role', '')).lower().strip() == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('staff_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s)) AND TRIM(password) = %s", (username, password))
        user_row = cur.fetchone()
        cur.close()
        conn.close()
        if user_row:
            user_dict = dict(user_row)
            role = str(user_dict.get('role', 'staff')).lower().strip()
            status = str(user_dict.get('status', 'approved')).lower().strip()
            if role != 'admin' and status != 'approved':
                flash('Account pending admin approval.', 'warning')
                return redirect(url_for('login'))
            session.clear()
            session['user'] = user_dict
            return redirect(url_for('admin_dashboard') if role == 'admin' else url_for('staff_dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        phone = request.form.get('phone', '').strip()
        nin = request.form.get('nin', '').strip()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s))", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            flash('Username already taken.', 'warning')
            return redirect(url_for('register'))
        cur.execute("INSERT INTO users (full_name, username, password, role, status, phone, nin) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (full_name, username, password, 'staff', 'pending', phone, nin))
        conn.commit()
        cur.close()
        conn.close()
        flash('Registration successful. Awaiting admin approval.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

# --- ADMIN TABS & VIEWS ---
@app.route('/admin', methods=['GET'])
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    search = request.args.get('q', '').strip()
    
    cur.execute("SELECT * FROM users WHERE status = 'pending' AND role != 'admin'")
    pending_users = cur.fetchall()
    cur.execute("SELECT * FROM transactions WHERE status = 'pending'")
    pending_txs = cur.fetchall()
    
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE status='approved'")
    approved_deposits = float(cur.fetchone()['total'])
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE status='pending'")
    pending_deposits = float(cur.fetchone()['total'])
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM payouts")
    total_paid_out = float(cur.fetchone()['total'])
    reserve_vault = approved_deposits - total_paid_out

    cur.execute("SELECT * FROM users WHERE role != 'admin' ORDER BY id DESC")
    staff_list = cur.fetchall()
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    transactions = cur.fetchall()
    cur.execute("SELECT * FROM loans ORDER BY id DESC")
    loans = cur.fetchall()
    cur.execute("SELECT * FROM payouts ORDER BY id DESC")
    payout_history = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='dashboard', pending_users=pending_users, pending_txs=pending_txs,
                           approved=approved_deposits, pending=pending_deposits, total_paid_out=total_paid_out,
                           reserve_vault=reserve_vault, staff_list=staff_list, transactions=transactions,
                           loans=loans, payout_history=payout_history, search_query=search)

@app.route('/admin/members')
@admin_required
def admin_members():
    conn = get_db_connection()
    cur = conn.cursor()
    search = request.args.get('q', '').strip()
    if search:
        cur.execute("SELECT * FROM users WHERE role != 'admin' AND (username ILIKE %s OR full_name ILIKE %s) ORDER BY id DESC", (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("SELECT * FROM users WHERE role != 'admin' ORDER BY id DESC")
    staff_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='members', staff_list=staff_list, search_query=search)

@app.route('/admin/accounts')
@admin_required
def admin_accounts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE status='approved'")
    approved = float(cur.fetchone()['total'])
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE status='pending'")
    pending = float(cur.fetchone()['total'])
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM payouts")
    total_paid_out = float(cur.fetchone()['total'])
    reserve_vault = approved - total_paid_out
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    transactions = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='accounts', approved=approved, pending=pending, total_paid_out=total_paid_out, reserve_vault=reserve_vault, transactions=transactions)

@app.route('/admin/shares')
@admin_required
def admin_shares():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE role != 'admin'")
    staff_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='shares', staff_list=staff_list)

@app.route('/admin/loans')
@admin_required
def admin_loans():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM loans ORDER BY id DESC")
    loans = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='loans', loans=loans)

@app.route('/admin/savings')
@admin_required
def admin_savings():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE role != 'admin'")
    staff_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='savings', staff_list=staff_list)

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    transactions = cur.fetchall()
    cur.execute("SELECT * FROM payouts ORDER BY id DESC")
    payout_history = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='transactions', transactions=transactions, payout_history=payout_history)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payouts ORDER BY id DESC")
    payout_history = cur.fetchall()
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    transactions = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', active_tab='reports', payout_history=payout_history, transactions=transactions)

# --- STAFF TABS & VIEWS ---
@app.route('/staff_dashboard', methods=['GET', 'POST'])
@login_required
def staff_dashboard():
    username = session['user']['username']
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        frequency = request.form.get('frequency', 'Weekly')
        date_str = request.form.get('date')
        if amount and float(amount) > 0:
            cur.execute("INSERT INTO transactions (username, amount, frequency, date, status, type) VALUES (%s, %s, %s, %s, %s, %s)",
                        (username, float(amount), frequency, date_str, 'pending', 'deposit'))
            conn.commit()
            flash('Deposit request submitted.', 'success')
        return redirect(url_for('staff_dashboard'))

    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = dict(cur.fetchone())
    cur.execute("SELECT * FROM transactions WHERE username = %s ORDER BY id DESC", (username,))
    transactions = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE username = %s AND status='approved'", (username,))
    balance = float(cur.fetchone()['total'])
    cur.execute("SELECT * FROM loans WHERE username = %s ORDER BY id DESC", (username,))
    loans = cur.fetchall()
    cur.execute("SELECT * FROM payouts WHERE username = %s ORDER BY id DESC", (username,))
    payouts = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('staff.html', active_tab='dashboard', user=user, transactions=transactions, balance=balance, loans=loans, my_payouts=payouts)

@app.route('/staff/profile')
@login_required
def staff_profile():
    return staff_dashboard()

@app.route('/staff/accounts')
@login_required
def staff_accounts():
    return staff_dashboard()

@app.route('/staff/shares')
@login_required
def staff_shares():
    return staff_dashboard()

@app.route('/staff/loans')
@login_required
def staff_loans():
    return staff_dashboard()

@app.route('/staff/savings')
@login_required
def staff_savings():
    return staff_dashboard()

@app.route('/staff/transactions')
@login_required
def staff_transactions():
    return staff_dashboard()

@app.route('/staff/statements')
@login_required
def staff_statements():
    return staff_dashboard()

# --- ACTIONS & UTILITIES ---
@app.route('/admin/approve_user/<username>')
@admin_required
def approve_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET status = 'approved' WHERE username = %s", (username,))
    conn.commit()
    cur.close()
    conn.close()
    flash(f'User {username} approved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_tx/<int:tx_id>')
@admin_required
def approve_tx(tx_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status = 'approved' WHERE id = %s", (tx_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Transaction approved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/clear_loan/<int:loan_id>')
@admin_required
def clear_loan(loan_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE loans SET status = 'cleared', balance = 0 WHERE id = %s", (loan_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Loan marked as fully cleared.', 'success')
    return redirect(url_for('admin_loans'))

@app.route('/admin/reset_password/<username>', methods=['POST'])
@admin_required
def reset_password(username):
    new_pass = request.form.get('new_password', 'password123')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password = %s WHERE username = %s", (new_pass, username))
    conn.commit()
    cur.close()
    conn.close()
    flash(f"Password for {username} reset successfully.", 'success')
    return redirect(url_for('admin_members'))

@app.route('/admin/change_password', methods=['POST'])
@admin_required
def admin_change_password():
    new_pass = request.form.get('new_password')
    if new_pass:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password = %s WHERE role = 'admin'", (new_pass,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Admin password updated successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)