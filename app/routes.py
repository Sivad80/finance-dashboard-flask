from flask import Blueprint, render_template, request, redirect, url_for, flash
from .models import Bill, Paycheck
from .extensions import db
from datetime import date
from sqlalchemy import func



main = Blueprint('main', __name__)

@main.route("/")
def dashboard():
    today = date.today()
    first_day = date(today.year, today.month, 1)
    
    # First Day of Next Month
    if today.month == 12:
        first_next = date(today.year + 1, 1, 1)
    else:
        first_next = date(today.year, today.month + 1, 1)

    total_bills = (
        db.session.query(func.coalesce(func.sum(Bill.amount), 0))
        .filter(Bill.is_active == True)
        .scalar()
    )

    total_income = (
        db.session.query(func.coalesce(func.sum(Paycheck.amount), 0))
        .filter(Paycheck.pay_date >= first_day)
        .filter(Paycheck.pay_date < first_next)
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

@main.route("/bills/<int:bill_id>/delete", methods=["POST"])
def delete_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    db.session.delete(bill)
    db.session.commit()
    flash("Bill deleted.", "success")
    return redirect(url_for("main.bills"))


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

# Edit Bills
@main.route("/bills/<int:bill_id>/edit")
def edit_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    return render_template("bill_edit.html", bill=bill)


@main.route("/bills/<int:bill_id>/update", methods=["POST"])
def update_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "Other").strip() or "Other"
    amount_raw = request.form.get("amount", "0").strip()
    due_day_raw = request.form.get("due_day", "1").strip()
    is_active_raw = request.form.get("is_active", "on")  # checkbox sends "on" when checked

    if not name:
        flash("Bill name is required.", "danger")
        return redirect(url_for("main.edit_bill", bill_id=bill_id))

    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Amount must be a number.", "danger")
        return redirect(url_for("main.edit_bill", bill_id=bill_id))

    try:
        due_day = int(due_day_raw)
        if due_day < 1 or due_day > 31:
            raise ValueError
    except ValueError:
        flash("Due day must be an integer between 1 and 31.", "danger")
        return redirect(url_for("main.edit_bill", bill_id=bill_id))

    bill.name = name
    bill.category = category
    bill.amount = amount
    bill.due_day = due_day
    bill.is_active = (is_active_raw == "on")

    db.session.commit()
    flash("Bill updated.", "success")
    return redirect(url_for("main.bills"))

# Paychecks Routes

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

# Edit/Delete Paychecks

@main.route('/paychecks/<int:paycheck_id>/delete', methods=['POST'])
def delete_paycheck(paycheck_id):
    paycheck = Paycheck.query.get_or_404(paycheck_id)
    db.session.delete(paycheck)
    db.session.commit()
    flash("Paycheck deleted.", "success")
    return redirect(url_for("main.paychecks"))

@main.route("/paychecks/<int:paycheck_id>/edit")
def edit_paycheck(paycheck_id):
    paycheck = Paycheck.query.get_or_404(paycheck_id)
    return render_template("paycheck_edit.html", paycheck=paycheck)


@main.route("/paychecks/<int:paycheck_id>/update", methods=["POST"])
def update_paycheck(paycheck_id):
    paycheck = Paycheck.query.get_or_404(paycheck_id)

    source = request.form.get("source", "").strip()
    amount_raw = request.form.get("amount", "0").strip()
    pay_date_raw = request.form.get("pay_date", "").strip()

    if not source:
        flash("Paycheck source is required.", "danger")
        return redirect(url_for("main.edit_paycheck", paycheck_id=paycheck_id))

    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Amount must be a number.", "danger")
        return redirect(url_for("main.edit_paycheck", paycheck_id=paycheck_id))

    try:
        pay_date = date.fromisoformat(pay_date_raw)
    except ValueError:
        flash("Pay date must be a valid date.", "danger")
        return redirect(url_for("main.edit_paycheck", paycheck_id=paycheck_id))

    paycheck.source = source
    paycheck.amount = amount
    paycheck.pay_date = pay_date

    db.session.commit()
    flash("Paycheck updated.", "success")
    return redirect(url_for("main.paychecks"))

