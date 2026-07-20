# --- LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user:
            # Safely get status and role
            role = user['role'] if 'role' in user.keys() else 'staff'
            status = str(user['status']).lower() if 'status' in user.keys() and user['status'] else 'approved'
            
            if role == 'admin':
                session['user'] = dict(user)
                return redirect(url_for('admin_dashboard'))
            
            if status == 'approved':
                session['user'] = dict(user)
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('login'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')


# --- ADMIN DASHBOARD ROUTE ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # Safely fetch pending & staff users
    try:
        pending_users = conn.execute("SELECT * FROM users WHERE LOWER(status) = 'pending' AND role != 'admin'").fetchall()
    except Exception:
        pending_users = []
        
    try:
        staff_list = conn.execute("SELECT * FROM users WHERE (LOWER(status) = 'approved' OR status IS NULL) AND role != 'admin'").fetchall()
    except Exception:
        staff_list = []

    # Safely fetch transactions
    try:
        transactions = conn.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    except Exception:
        transactions = []

    # Financial Stats (safely handle NULL / empty sums)
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

    # Safely fetch payout history and vault totals if columns exist
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
        
    conn = get_db_connection()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    
    flash(f'Transaction #{tx_id} deleted permanently!', 'danger')
    return redirect(url_for('admin_dashboard'))