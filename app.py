from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import date

app = Flask(__name__)
app.secret_key = 'sacco_secret_key_123'

# Default users list
users = [
    {
        "username": "admin", 
        "password": "123", 
        "role": "admin", 
        "status": "approved", 
        "full_name": "System Admin", 
        "phone": "0700000000",
        "national_id": "CM1234567890AB",
        "dob": "1990-01-01",
        "reset_requested": False
    },
    {
        "username": "staff", 
        "password": "123", 
        "role": "staff", 
        "status": "approved", 
        "full_name": "John Doe", 
        "phone": "0771234567",
        "national_id": "CF9876543210XY",
        "dob": "1995-05-15",
        "reset_requested": False
    },
    {
        "username": "bbosa", 
        "password": "123", 
        "role": "staff", 
        "status": "approved", 
        "full_name": "bbosa canan", 
        "phone": "0704180730",
        "national_id": "cm90456297yzug",
        "dob": "1992-08-10",
        "reset_requested": False
    }
]

# Transactions list
transactions = [
    {"id": 1, "username": "staff", "amount": 50000.0, "status": "approved", "frequency": "Monthly", "date": "2026-07-01"},
    {"id": 2, "username": "staff", "amount": 20000.0, "status": "pending", "frequency": "Weekly", "date": "2026-07-15"}
]

# Payout history log
payout_history = []

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
        
        user = next((u for u in users if u['username'] == uname and u['password'] == pwd), None)
        
        if user:
            if user.get('status') == 'pending':
                flash('Your account is pending Admin approval.', 'warning')
                return render_template('login.html')
            elif user.get('status') == 'suspended':
                flash('Your account has been suspended. Contact Admin.', 'danger')
                return render_template('login.html')
                
            session['user'] = user
            flash(f'Welcome back, {user.get("full_name", uname)}!', 'success')
            if user.get('role') == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('staff_dashboard'))
        else:
            flash('Invalid Username or Password!', 'danger')
            
    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        user = next((u for u in users if u['username'] == identifier or u.get('phone') == identifier or u.get('national_id') == identifier), None)
        
        if user:
            user['reset_requested'] = True
            flash('Password reset request submitted! Notify the Admin.', 'info')
            return redirect(url_for('login'))
        else:
            flash('No member account found with those details!', 'danger')
            
    return render_template('forgot_password.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        national_id = request.form.get('national_id')
        dob = request.form.get('dob')
        uname = request.form.get('username')
        pwd = request.form.get('password')
        
        if any(u['username'] == uname for u in users):
            flash('Username already exists! Choose another.', 'danger')
            return render_template('signup.html')
            
        users.append({
            "username": uname,
            "password": pwd,
            "role": "staff",
            "status": "pending",
            "full_name": full_name,
            "phone": phone,
            "national_id": national_id,
            "dob": dob,
            "reset_requested": False
        })
        flash('Registration submitted! Await Admin approval before logging in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/staff/dashboard', methods=['GET', 'POST'])
def staff_dashboard():
    if 'user' not in session or session['user'].get('role') != 'staff':
        return redirect(url_for('login'))
        
    username = session['user']['username']
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        frequency = request.form.get('frequency', 'Weekly')
        tx_date = request.form.get('date')
        
        if amount > 0:
            tx_id = len(transactions) + 1
            transactions.append({
                "id": tx_id,
                "username": username,
                "amount": amount,
                "status": "pending",
                "frequency": frequency,
                "date": tx_date
            })
            flash('Contribution deposit request submitted!', 'info')
            return redirect(url_for('staff_dashboard'))
            
    my_txs = [t for t in transactions if t['username'] == username]
    approved_balance = sum(t['amount'] for t in my_txs if t['status'] == 'approved')
    my_full_name = session['user'].get('full_name', username)
    my_payouts = [p for p in payout_history if p['recipient'] == my_full_name or p['recipient'] == username]

    return render_template('staff.html', 
                           user=session['user'], 
                           transactions=my_txs, 
                           balance=approved_balance,
                           my_payouts=my_payouts)

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'admin_change_password':
            new_pwd = request.form.get('new_password')
            if new_pwd:
                session['user']['password'] = new_pwd
                admin_user = next((u for u in users if u['username'] == 'admin'), None)
                if admin_user:
                    admin_user['password'] = new_pwd
                flash('Admin password changed successfully!', 'success')
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
                    p_id = len(payout_history) + 1
                    payout_history.append({
                        "id": f"REC-{p_id:04d}",
                        "recipient": r_name.strip(),
                        "amount": amt,
                        "date": payout_date,
                        "cycle": cycle_notes,
                        "payout_status": "PAID"
                    })
                    disbursed_count += 1
            
            if disbursed_count > 0:
                flash(f"Successfully disbursed rotation payouts for {disbursed_count} staff member(s)!", 'success')
            else:
                flash("No valid staff or amounts provided for disbursement.", 'warning')
            return redirect(url_for('admin_dashboard'))

    total_approved = sum(t['amount'] for t in transactions if t.get('status') == 'approved')
    total_pending = sum(t['amount'] for t in transactions if t.get('status') == 'pending')
    total_paid_out = sum(p['amount'] for p in payout_history)
    sacco_reserve_vault = total_approved - total_paid_out

    pending_users = [u for u in users if u.get('status') == 'pending']
    approved_staff = [u for u in users if u.get('role') == 'staff' and u.get('status') != 'pending']
    reset_requests = [u for u in users if u.get('reset_requested', False)]
    
    return render_template('admin.html', 
                           transactions=transactions, 
                           approved=total_approved, 
                           pending=total_pending,
                           reserve_vault=sacco_reserve_vault,
                           total_paid_out=total_paid_out,
                           payout_history=payout_history,
                           pending_users=pending_users,
                           staff_list=approved_staff,
                           reset_requests=reset_requests)

@app.route('/admin/member/<username>', methods=['GET', 'POST'])
def view_member(username):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
        
    member = next((u for u in users if u['username'] == username), None)
    if not member:
        flash('Member not found!', 'danger')
        return redirect(url_for('admin_dashboard'))
        
    if request.method == 'POST':
        member['full_name'] = request.form.get('full_name')
        member['phone'] = request.form.get('phone')
        member['national_id'] = request.form.get('national_id')
        member['dob'] = request.form.get('dob')
        member['status'] = request.form.get('status')
        
        new_password = request.form.get('password')
        if new_password:
            member['password'] = new_password
            member['reset_requested'] = False
            flash(f'Password updated for {member["full_name"]}!', 'success')
        else:
            flash(f'Profile updated for {member["full_name"]}!', 'success')
        return redirect(url_for('view_member', username=username))
        
    member_txs = [t for t in transactions if t['username'] == username]
    total_paid = sum(t['amount'] for t in member_txs if t.get('status') == 'approved')
    
    return render_template('member_detail.html', member=member, transactions=member_txs, total_paid=total_paid)

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

@app.route('/admin/delete_tx/<int:tx_id>')
def delete_tx(tx_id):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM transactions WHERE id = ?', (tx_id,))
    conn.commit()
    conn.close()
    flash(f'Transaction #{tx_id} deleted permanently!', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_user/<username>')
def approve_user(username):
    if 'user' not in session or session['user'].get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE users SET status = "approved" WHERE LOWER(username) = LOWER(?)', (username,))
    conn.commit()
    conn.close()
    flash(f'Account for {username} approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)