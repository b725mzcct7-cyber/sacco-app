from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import date

app = Flask(__name__)
app.secret_key = 'sacco_secret_key_123'
DB_NAME = 'sacco.db'

# Helper function to get database connection
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Create Database Tables Automatically
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            status TEXT NOT NULL DEFAULT 'pending',
            full_name TEXT NOT NULL,
            phone TEXT,
            national_id TEXT,
            dob TEXT,
            reset_requested INTEGER DEFAULT 0
        )
    ''')

    # Create Transactions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            frequency TEXT DEFAULT 'Weekly',
            date TEXT NOT NULL
        )
    ''')

    # Create Payout History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payout_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_code TEXT NOT NULL,
            recipient TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            cycle TEXT DEFAULT 'Weekly Rotation',
            payout_status TEXT DEFAULT 'PAID'
        )
    ''')

    # Add Default Admin if doesn't exist
    admin = cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        cursor.execute('''
            INSERT INTO users (username, password, role, status, full_name, phone, national_id, dob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', '123', 'admin', 'approved', 'System Admin', '0700000000', 'CM1234567890AB', '1990-01-01'))

    conn.commit()
    conn.close()

# Initialize DB structure on launch
init_db()

# ----------------------------------------------------
# ROUTES
# ----------------------------------------------------

@app.route('/')
def home():
    if 'user' in session:
        if session['user'].get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('staff_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username')
        pwd = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (uname, pwd)).fetchone()
        conn.close()
        
        if user:
            user_dict = dict(user)
            if user_dict.get('status') == 'pending':
                flash('Your account is pending Admin approval.', 'warning')
                return render_template('login.html')
            elif user_dict.get('status') == 'suspended':
                flash('Your account has been suspended. Contact Admin.', 'danger')
                return render_template('login.html')
                
            session['user'] = user_dict
            flash(f'Welcome back, {user_dict.get("full_name", uname)}!', 'success')
            if user_dict.get('role') == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('staff_dashboard'))
        else:
            flash('Invalid Username or Password!', 'danger')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        national_id = request.form.get('national_id')
        dob = request.form.get('dob')
        uname = request.form.get('username')
        pwd = request.form.get('password')
        
        conn = get_db_connection()
        existing = conn.execute('SELECT id FROM users WHERE username = ?', (uname,)).fetchone()
        if existing:
            conn.close()
            flash('Username already exists! Choose another.', 'danger')
            return render_template('signup.html')
            
        conn.execute('''
            INSERT INTO users (username, password, role, status, full_name, phone, national_id, dob)
            VALUES (?, ?, 'staff', 'pending', ?, ?, ?, ?)
        ''', (uname, pwd, full_name, phone, national_id, dob))
        conn.commit()
        conn.close()
        
        flash('Registration submitted! Await Admin approval before logging in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/staff/dashboard', methods=['GET', 'POST'])
def staff_dashboard():
    if 'user' not in session or session['user'].get('role') != 'staff':
        return redirect(url_for('login'))
        
    username = session['user']['username']
    conn = get_db_connection()
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        frequency = request.form.get('frequency', 'Weekly')
        tx_date = request.form.get('date')
        
        if amount > 0:
            conn.execute('''
                INSERT INTO transactions (username, amount, status, frequency, date)
                VALUES (?, ?, 'pending', ?, ?)
            ''', (username, amount, frequency, tx_date))
            conn.commit()
            flash('Contribution deposit request submitted!', 'info')
            
    my_txs_raw = conn.execute('SELECT * FROM transactions WHERE username = ?', (username,)).fetchall()
    my_txs = [dict(t) for t in my_txs_raw]
    
    approved_balance = sum(t['amount'] for t in my_txs if t['status'] == 'approved')
    my_full_name = session['user'].get('full_name', username)
    
    payouts_raw = conn.execute('SELECT * FROM payout_history WHERE recipient = ? OR recipient = ?', (my_full_name, username)).fetchall()
    my_payouts = [dict(p) for p in payouts_raw]
    conn.close()

    return render_template('staff.html', 
                           user=session['user'], 
                           transactions=my_txs, 
                           balance=approved_balance,
                           my_payouts=my_payouts)

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'admin_change_password':
            new_pwd = request.form.get('new_password')
            if new_pwd:
                session['user']['password'] = new_pwd
                conn.execute('UPDATE users SET password = ? WHERE username = "admin"', (new_pwd,))
                conn.commit()
                flash('Admin password changed successfully!', 'success')
            conn.close()
            return redirect(url_for('admin_dashboard'))
            
        elif action == 'disburse_batch_payout':
            recipients = request.form.getlist('recipients')
            amounts = request.form.getlist('amounts')
            payout_date = request.form.get('payout_date', str(date.today()))
            cycle_notes = request.form.get('cycle_notes', 'Weekly Rotation')
            
            disbursed_count = 0
            for r_name, amt_str in zip(recipients, amounts):
                if r_name.strip() and amt_str and float(amt_str) > 0:
                    amt = float(amt_str)
                    conn.execute('''
                        INSERT INTO payout_history (receipt_code, recipient, amount, date, cycle, payout_status)
                        VALUES (?, ?, ?, ?, ?, 'PAID')
                    ''', (f"REC-{date.today().strftime('%Y%m')}", r_name.strip(), amt, payout_date, cycle_notes))
                    disbursed_count += 1
            conn.commit()
            
            if disbursed_count > 0:
                flash(f"Successfully disbursed rotation payouts for {disbursed_count} staff member(s)!", 'success')
            conn.close()
            return redirect(url_for('admin_dashboard'))

    # Load All Data From SQLite
    tx_raw = conn.execute('SELECT * FROM transactions').fetchall()
    transactions = [dict(t) for t in tx_raw]
    
    payout_raw = conn.execute('SELECT * FROM payout_history').fetchall()
    payout_history = [dict(p) for p in payout_raw]
    
    users_raw = conn.execute('SELECT * FROM users').fetchall()
    users_list = [dict(u) for u in users_raw]
    conn.close()

    total_approved = sum(t['amount'] for t in transactions if t.get('status') == 'approved')
    total_pending = sum(t['amount'] for t in transactions if t.get('status') == 'pending')
    total_paid_out = sum(p['amount'] for p in payout_history)
    sacco_reserve_vault = total_approved - total_paid_out

    pending_users = [u for u in users_list if u.get('status') == 'pending']
    approved_staff = [u for u in users_list if u.get('role') == 'staff' and u.get('status') != 'pending']
    
    return render_template('admin.html', 
                           transactions=transactions, 
                           approved=total_approved, 
                           pending=total_pending,
                           reserve_vault=sacco_reserve_vault,
                           total_paid_out=total_paid_out,
                           payout_history=payout_history,
                           pending_users=pending_users,
                           staff_list=approved_staff)

@app.route('/admin/approve_user/<username>')
def approve_user(username):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE users SET status = "approved" WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    flash(f'Account for {username} approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_tx/<int:tx_id>')
def approve_tx(tx_id):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE transactions SET status = "approved" WHERE id = ?', (tx_id,))
    conn.commit()
    conn.close()
    flash(f'Transaction #{tx_id} approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)