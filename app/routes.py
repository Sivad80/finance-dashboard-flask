from flask import Blueprint, render_template, request, redirect, url_for, flash
from .models import Bill, Paycheck
from .extensions import db
from datetime import date
from sqlalchemy import func



main = Blueprint('main', __name__)

@main.route("/")
def dashboard():
    total_bills = (
        db.session.query(func.coalesce(func.sum(Bill.amount), 0))
        .filter(Bill.is_active == True)
        .scalar()
    )

    total_income = (
        db.session.query(func.coalesce(func.sum(Paycheck.amount), 0))
        .scalar()
    )

    remaining = float(total_income) - float(total_bills)

    next_paycheck = (
        Paycheck.query
        .filter(Paycheck.pay_date >= date.today())
        .order_by(Paycheck.pay_date.asc())
        .first()
    )

    next_paycheck_label = next_paycheck.pay_date.strftime("%b %d, %Y") if next_paycheck else "—"

    return render_template(
        "dashboard.html",
        total_income=float(total_income),
        total_bills=float(total_bills),
        remaining=float(remaining),
        next_paycheck_label=next_paycheck_label,
    )


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

@main.route("/paychecks")
def paychecks():
    paychecks = Paycheck.query.order_by(Paycheck.pay_date.asc()).all()
    return render_template("paychecks.html", paychecks=paychecks)

@main.route("/paychecks/new", methods=["POST"])
def create_paycheck():
    source = request.form.get("source", "").strip()
    amount_raw = request.form.get("amount", "0").strip()
    pay_date_raw = request.form.get("pay_date", "").strip()

    if not source:
        flash("Paycheck source is required.", "danger")
        return redirect(url_for("main.paychecks"))

    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Amount must be a number.", "danger")
        return redirect(url_for("main.paychecks"))

    try:
        pay_date = date.fromisoformat(pay_date_raw)
    except ValueError:
        flash("Pay date must be a valid date.", "danger")
        return redirect(url_for("main.paychecks"))

    paycheck = Paycheck(source=source, amount=amount, pay_date=pay_date)
    db.session.add(paycheck)
    db.session.commit()

    flash("Paycheck added.", "success")
    return redirect(url_for("main.paychecks"))
