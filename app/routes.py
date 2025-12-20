from flask import Blueprint, render_template, request, redirect, url_for, flash
from .models import Bill
from .extensions import db


main = Blueprint('main', __name__)

@main.route('/')
def dashboard():
    return render_template('dashboard.html')

@main.route('/bills')
def bills():
    bills = Bill.query.order_by(Bill.due_day.asc(), Bill.name.asc()).all()
    return render_template('bills.html', bills=bills)

# Create Bills Forms/Route
@main.route('/bill/new', methods=['POST'])
def create_bill():
    name = request.form.get('name' '').strip()
    category = request.form.get('category', 'Other').strip() or "Other"
    amount_raw = request.form.get('amount', '0').strip()
    due_day_raw = request.form.get('due_day', '1').strip()

    # Basic Validation
    if not name:
        flash("Bill name is required.", "danger")
        return redirect(url_for('main.bills'))
    
    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Amount must be a number.", "danger")
        return redirect(url_for('main.bills'))
    
    try: 
        due_day = int(due_day_raw)
        if due_day < 1 or due_day > 31:
            raise ValueError
    except ValueError:
        flash("Due Day Must be an Integer between 1 and 31.", "danger")
        return redirect(url_for('main.bills'))
    
    bill = Bill(
        name=name,
        category=category,
        amount=amount,
        due_day=due_day,
        is_active=True
    )
    db.session.add(bill)
    db.session.commit()

    flash("Bill Added.", "success")
    return redirect(url_for('main.bills'))