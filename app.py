import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session

# 1. INITIALIZE FLASK (This MUST be defined before any @app.route!)
app = Flask(__name__)
app.secret_key = 'sacco_secret_key_here'

# 2. DATABASE HELPER
def get_db_connection():
    conn = sqlite3.connect('sacco.db')
    conn.row_factory = sqlite3.Row
    return conn


# --- 3. ROUTES ---

# --- LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user_row = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user_row:
            user_dict = dict(user_row)
            role = user_dict.get('role', 'staff')
            raw_status = user_dict.get('status')
            status = str(raw_status).lower() if raw_status else 'approved'
            
            if role == 'admin':
                session['user'] = user_dict
                return redirect(url_for('admin_dashboard'))
            
            if status == 'approved':
                session['user'] = user_dict
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('login'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')


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
        user_txs = conn.execute('SELECT * FROM transactions WHERE username = ? ORDER BY id DESC', (username,)).fetchall()
    except Exception:
        user_txs = []
        
    try:
        approved_val = conn.execute("SELECT SUM(amount) FROM transactions WHERE username = ? AND LOWER(status) = 'approved'", (username,)).fetchone()[0]
        total_approved = approved_val if approved_val else 0
    except Exception:
        total_approved = 0

    try:
        pending_val = conn.execute("SELECT SUM(amount) FROM transactions WHERE username = ? AND LOWER(status) = 'pending'", (username,)).fetchone()[0]
        total_pending = pending_val if pending_val else 0
    except Exception:
        total_pending = 0

    conn.close()
    
    return render_template('staff.html', 
                           user=user, 
                           transactions=user_txs, 
                           total_approved=total_approved, 
                           total_pending=total_pending)


# --- ADMIN DASHBOARD ROUTE ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    try:
        pending_users = conn.execute("SELECT * FROM users WHERE LOWER(status) = 'pending' AND (role != 'admin' OR role IS NULL)").fetchall()
    except Exception:
        pending_users = []
        
    try:
        staff_list = conn.execute("SELECT * FROM users WHERE (LOWER(status) = 'approved' OR status IS NULL) AND (role != 'admin' OR role IS NULL)").fetchall()
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
    
    return render_template('admin.html', 
                           pending_users=pending_users, 
                           staff_list=staff_list, 
                           transactions=transactions,
                           approved=approved,
                           pending=pending,
                           total_paid_out=total_paid_out,
                           reserve_vault=reserve_vault,
                           payout_history=payout_history)


# --- APPROVE USER / STAFF ROUTE ---
@app.route('/admin/approve_user/<username>')
def approve_user(username):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    conn.execute("UPDATE users SET status = 'approved' WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    
    flash(f'Account for {username} has been approved!', 'success')
    return redirect(url_for('admin_dashboard'))


# --- APPROVE TRANSACTION ---
@app.route('/admin/approve_tx/<int:tx_id>')
def approve_tx(tx_id):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    conn.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    
    flash(f'Transaction #{tx_id} approved!', 'success')
    return redirect(url_for('admin_dashboard'))


# --- DELETE TRANSACTION ---
@app.route('/admin/delete_tx/<int:tx_id>')
def delete_tx(tx_id):
    if 'user' not in session or session['user'].get('role') != 'admin':
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


# --- APP RUNNER (FOR LOCAL TESTING) ---
if __name__ == '__main__':
    app.run(debug=True)