from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import os
import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'canan_bbosa_ventures_sacco_secret')

# ==========================================
# AUTHENTICATION & ROLE HELPERS
# ==========================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Enforce strict Admin role check to prevent misdirection to staff routes
        if not session.get('logged_in') or session.get('role') != 'admin':
            flash("Admin access required.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def index():
    if session.get('logged_in'):
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('staff_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Dummy/Database Auth Logic
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            session['username'] = 'admin'
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            # Check regular staff credentials...
            session['logged_in'] = True
            session['username'] = username
            session['role'] = 'staff'
            return redirect(url_for('staff_dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))


# ==========================================
# ADMIN DASHBOARD & DISBURSEMENT ROUTES
# ==========================================

@app.route('/admin', methods=['GET'])
@admin_required
def admin_dashboard():
    # Placeholder data structures passed to admin.html
    approved = 1500000.00
    pending = 250000.00
    total_paid_out = 400000.00
    reserve_vault = approved - total_paid_out

    pending_users = []
    staff_list = [
        {"username": "john_d", "full_name": "John Doe", "phone": "0700000001", "national_id": "CM12345", "status": "approved"},
        {"username": "mary_k", "full_name": "Mary Kyomugisha", "phone": "0700000002", "national_id": "CM67890", "status": "approved"},
    ]
    payout_history = []
    transactions = []

    return render_template(
        'admin.html',
        approved=approved,
        pending=pending,
        total_paid_out=total_paid_out,
        reserve_vault=reserve_vault,
        pending_users=pending_users,
        staff_list=staff_list,
        payout_history=payout_history,
        transactions=transactions
    )


@app.route('/admin/disburse_payouts', methods=['POST'])
@admin_required
def disburse_payouts():
    """
    Handles payout form submission from admin.html.
    Strictly protected by @admin_required and explicitly re-routes back to /admin.
    """
    payout_date = request.form.get('payout_date')
    notes = request.form.get('notes', 'Weekly Rotation')

    disbursed_count = 0
    # Process up to 5 staff payouts submitted from the admin interface
    for i in range(1, 6):
        staff_username = request.form.get(f'staff_{i}')
        amount = request.form.get(f'amount_{i}')

        if staff_username and amount:
            try:
                amount_val = float(amount)
                if amount_val > 0:
                    # TODO: Insert payout log into your database execution table
                    # db.execute("INSERT INTO payouts (recipient, amount, date, notes) VALUES (%s, %s, %s, %s)", ...)
                    disbursed_count += 1
            except ValueError:
                continue

    if disbursed_count > 0:
        flash(f"Successfully disbursed rotation payout for {disbursed_count} staff member(s).", "success")
    else:
        flash("No valid staff amounts were submitted for payout.", "warning")

    # FIXED: Explicitly redirect back to admin dashboard to stop any bounce to staff dashboard
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/approve_user/<username>')
@admin_required
def approve_user(username):
    # Logic to approve pending user registration
    flash(f"User {username} approved successfully.", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/change_password', methods=['POST'])
@admin_required
def change_password():
    new_password = request.form.get('new_password')
    # Logic to update admin password in DB
    flash("Admin password updated successfully.", "success")
    return redirect(url_for('admin_dashboard'))


# ==========================================
# STAFF DASHBOARD ROUTE
# ==========================================

@app.route('/dashboard')
@login_required
def staff_dashboard():
    # If an Admin lands here by mistake, redirect back to Admin
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    return render_template('dashboard.html', username=session.get('username'))


if __name__ == '__main__':
    app.run(debug=True)