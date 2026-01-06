from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .models import Bill, Paycheck, Expense, PaySchedule
from .extensions import db
from datetime import date, timedelta, datetime
from sqlalchemy import func
from .utils import next_due_date
import csv
import io
from .constants import EXPENSE_CATEGORIES
import hashlib
import re

# Helper Functions
def expense_fingerprint(spent_date, amount, description):
    desc = (description or "").strip().lower()
    desc = re.sub(r"\s+", " ", desc)
    desc = re.sub(r"[^a-z0-9 \-]", "", desc)
    
    key = f"{spent_date.isoformat()}|{float(amount):.2f}|{desc}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def get_pay_period(today: date) -> tuple[date, date]:
    """
    Returns (start, end) for the current bi-weekly pay period ancored to a stored payday.
    """
    schedule = PaySchedule.query.order_by(PaySchedule.id.desc()).first()
    
    # Fallback if not configured yet: Rolling 14 days
    if not schedule:
        start = today - timedelta(days=13)
        return start, today
    anchor = schedule.anchor_payday # A real Friday Payday
    delta_days = (today - anchor).days
    
    # How many 14 day blocks since anchor (floor)
    periods = delta_days // 14
    
    # Most recent payday on/before today
    start = anchor + timedelta(days=periods * 14)
    
    # If today is before anchor (negative delta), correct:
    if start > today:
        start = start - timedelta(days=14)
        
    end = start + timedelta(days=13)
    return start, end

    



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
    payday_date = next_paycheck.pay_date if next_paycheck else None
    
    active_bills = Bill.query.filter(Bill.is_active == True).all()
    
    bills_before_payday = []
    for b in active_bills:
        due = next_due_date(b.due_day, today)
        # Skip if already marked paid for this due date
        if b.paid_through and b.paid_through >= due: 
            continue
        
        
        # If we don't have a payday yet, we won't filter (Show empty list for now)
        if payday_date and today <= due <= payday_date:
            bills_before_payday.append({
                "name": b.name,
                "due": due, 
                "amount": float(b.amount),
            })
    bills_before_payday.sort(key=lambda x: x['due'])
    total_due_before_payday = sum(x['amount'] for x in bills_before_payday)
    
    window_end = today + timedelta(days=30)
    
    upcoming_bills = []
    for b in active_bills:
        due = next_due_date(b.due_day, today)
        # Skip if already marked paid for this due date
        if b.paid_through and b.paid_through >= due: 
            continue
        
        # If we have a payday, "upcoming" means after payday but within 30 days
        if payday_date:
            if due > payday_date and due <= window_end:
                upcoming_bills.append({"name": b.name, "due": due, "amount": float(b.amount)})
            else:
                # If no payday exists yet, just show next 30 days
                if today <= due <= window_end:
                    upcoming_bills.append({"name": b.name, "due": due, "amount": float(b.amount)})  
    upcoming_bills.sort(key=lambda x: x["due"])

    return render_template(
        "dashboard.html",
        total_income=float(total_income),
        total_bills=float(total_bills),
        remaining=float(remaining),
        next_paycheck_label=next_paycheck_label,
        bills_before_payday=bills_before_payday,
        total_due_before_payday=total_due_before_payday,
        payday_date=payday_date,
        upcoming_bills=upcoming_bills,
        window_end=window_end,
    )
    
# Expenses Routes

@main.route("/expenses")
def expenses():
    # --- filters from query string ---
    preset = request.args.get("preset", "this_month")
    show = request.args.get("show", "all")  # all | dupes

    today = date.today()
    end = today

    # default date range
    if preset == 'all_time': 
        start = date(2000, 1, 1)
    elif preset == 'this_pay_period':
        start, end = get_pay_period(today)
    elif preset == "last_30":
        start = today - timedelta(days=30)
    elif preset == "last_90":
        start = today - timedelta(days=90)
    else:
        start = date(today.year, today.month, 1)

    

    # optional custom override
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    try:
        if start_raw:
            start = date.fromisoformat(start_raw)
        if end_raw:
            end = date.fromisoformat(end_raw)
    except ValueError:
        flash("Invalid date filter. Use YYYY-MM-DD.", "warning")

    # --- build query ---
    q = Expense.query.filter(Expense.spent_date >= start, Expense.spent_date <= end)

    if show == "dupes":
        q = q.filter(Expense.is_duplicate == True)

    expenses = q.order_by(Expense.spent_date.desc(), Expense.id.desc()).limit(200).all()
    total = q.with_entities(func.coalesce(func.sum(Expense.amount), 0)).scalar()

    return render_template(
        "expenses.html",
        expenses=expenses,
        total=total,
        categories=EXPENSE_CATEGORIES,
        show=show,
        preset=preset,
        start=start,
        end=end,
    )


@main.route("/expenses/upload", methods=["GET"])
def expenses_upload():
    return render_template("expenses_upload.html")

@main.route("/expenses/upload", methods=["POST"])
def expenses_upload_post():
    """
    Upload CSV -> parse -> store preview rows in session -> redirect to preview page.
    Expected columns (case-insensitive): date, description, amount, category(optional)
    """
    f = request.files.get("file")
    if not f or f.filename == "":
        flash("Please choose a CSV file.", "danger")
        return redirect(url_for("main.expenses_upload"))
    
    raw_bytes = f.read()

    raw = None
    for enc in ("utf-8-sig", "utf-16", "utf-16le", "utf-16be", "cp1252", "latin-1"):
        try:
            raw = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if raw is None:
        raw = raw_bytes.decode("utf-8", errors="replace")

    
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        flash("CSV appears to be empty or missing a header row.", "danger")
        return redirect(url_for("main.expenses_upload"))
    
    # Normalize header names
    headers = [h.strip().lower() for h in reader.fieldnames]
    
    def pick(col_name: str) -> str | None:
        for h in reader.fieldnames:
            if h and h.strip().lower() == col_name:
                return h
        return None
    
    col_date = pick("date")
    col_desc = pick("description")
    col_amt = pick("amount")
    col_cat = pick("category")
    
    if not (col_date and col_desc and col_amt):
        flash("CSV must include headers: date, description, amount (category optional).", "danger")
        return redirect(url_for("main.expenses_upload"))
    
    preview = []
    errors = 0
    
    for i, row in enumerate(reader, start=1):
        if i > 2000: # Safety Cap
            break
        
        date_raw = (row.get(col_date) or "").strip()
        desc = (row.get(col_desc) or "").strip()
        amt_raw = (row.get(col_amt) or "").strip()
        cat = ((row.get(col_cat) or "").strip() if col_cat else "") or "Uncategorized"

        if not date_raw or not desc or not amt_raw:
            errors += 1
            continue
        
        # Parse Date: Expects YYYY-MM-DD (Expand Later)
        try:
            # Supports YYYY-MM-DD and MM/DD/YYYY
            if "-" in date_raw:
                spent_date = date.fromisoformat(date_raw)
            else:
                spent_date = datetime.strptime(date_raw, "%m/%d/%Y").date()
        except ValueError:
            errors += 1
            continue
    
        # Parse Amount
        try: 
            amount = float(amt_raw.replace("$", "").replace(",", ""))
        except ValueError:
            errors += 1
            continue
        
        preview.append({
            "spent_date": spent_date.isoformat(),
            "description": desc,
            "amount": round(amount, 2),
            "category": cat,
        })
        
        
        
    session["expense_import_preview"] = preview
    session["expense_import_errors"] = errors
    
    if not preview:
        flash("No valid rows found. Check date format (YYYY-MM-DD) and required columns.", "danger")
        return redirect(url_for("main.expenses_upload"))
    
    return redirect(url_for("main.expenses_preview"))

@main.route("/expenses/preview")
def expenses_preview():
    preview = session.get("expense_import_preview", [])
    errors = session.get("expense_import_errors", 0)
    preview_rows = preview[:50] 
    return render_template("expenses_preview.html", preview=preview_rows, total_rows=len(preview), errors=errors)

@main.route("/expenses/import", methods=["POST"])
def expenses_import():
    preview = session.get("expense_import_preview", [])
    if not preview:
        flash("Nothing to import, Upload a CSV first.", "warning")
        return redirect(url_for("main.expenses_upload"))
    
    count = 0

    for item in preview:
        spent_date = date.fromisoformat(item["spent_date"])
        amount = float(item["amount"])
        description = item["description"]
        category = item.get("category") or "Uncategorized"

        fp = expense_fingerprint(spent_date, amount, description)

        existing = Expense.query.filter_by(fingerprint=fp).first()

        e = Expense(
            spent_date=spent_date,
            description=description,
            amount=amount,
            category=category,
            fingerprint=fp,
            is_duplicate=bool(existing),
            duplicate_of_id=existing.id if existing else None
        )

        db.session.add(e)
        count += 1

        
    db.session.commit()
    
    # Clear Preview
    session.pop("expense_import_preview", None)
    session.pop("expense_import_errors", None)
    
    flash(f"Imported {count} expenses.", "success")
    return redirect(url_for("main.expenses"))

@main.route("/expenses/<int:expense_id>/category", methods=["POST"])
def update_expense_category(expense_id):
    e = Expense.query.get_or_404(expense_id)
    category = (request.form.get("category") or "").strip()
    
    if category not in EXPENSE_CATEGORIES:
        flash("Invalid category.", "danger")
        return redirect(request.referrer or url_for("main.expenses"))

    e.category = category
    db.session.commit()
    flash("Category updated.", "success")
    return redirect(request.referrer or url_for("main.expenses"))

@main.route("/expenses/bulk-category", methods=["POST"])
def bulk_update_expense_category():
    category = (request.form.get("category") or "").strip()
    ids = request.form.getlist("expense_ids")
    
    if category not in EXPENSE_CATEGORIES:
        flash("Invalid category.", "danger")
        return redirect(request.referrer or url_for("main.expenses"))
    
    if not ids:
        flash("Select at least one expense.", "warning")
        return redirect(request.referrer or url_for("main.expenses"))
    
    # Convert to Ints Safely
    expense_ids = []
    for x in ids:
        try: 
            expense_ids.append(int(x))
        except ValueError:
            continue
        
    if not expense_ids:
        flash("No valid expenses selected.", "warning")
        return redirect(request.referrer or url_for("main.expenses"))
    
    Expense.query.filter(Expense.id.in_(expense_ids)).update(
        {"category": category},
        synchronize_session=False
    )
    db.session.commit()
    
    flash(f"Updated {len(expense_ids)} expenses.", "success")
    return redirect(request.referrer or url_for("main.expenses"))
    
@main.route("/expenses/<int:expense_id>/delete", methods=["POST"])  
def delete_expense(expense_id):
    e = Expense.query.get_or_404(expense_id)
    db.session.delete(e)
    db.session.commit()
    flash("Expense deleted.", "success")
    return redirect(request.referrer or url_for("main.expenses"))

@main.route("/expenses/bulk-delete", methods=["POST"])
def bulk_delete_expenses():
    ids = request.form.getlist("expense_ids")
    
    if not ids: 
        flash("Select at least one expense to delete.", "warning") 
        return redirect(request.referrer or url_for("main.expenses"))
    
    expense_ids = []
    for x in ids:
        try:
            expense_ids.append(int(x))
        except ValueError:
            continue
        
    if not expense_ids:
        flash("No valid expenses selected.", "warning")
        return redirect(request.referrer or url_for("main.expenses"))
    
    deleted = Expense.query.filter(Expense.id.in_(expense_ids)).delete(synchronize_session=False)
    db.session.commit()
    
    flash(f"Deleted {deleted} expenses.", "success")
    return redirect(request.referrer or url_for("main.expenses"))

    
# Bills Routes
        
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
    next_url = request.args.get('next')

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
    return redirect(next_url or url_for('main.bills'))

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

@main.route("/bills/<int:bill_id>/paid", methods=["POST"])
def mark_bill_paid(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    today = date.today()
    
    # Use Helper to Mark Paid through the next Due Date
    due = next_due_date(bill.due_day, today)
    bill.paid_through = due
    
    db.session.commit()
    flash("Bill marked as paid.", "success")
    return redirect(request.referrer or url_for("main.bills"))

@main.route("/bills/<int:bill_id>/unpaid", methods=["POST"])
def mark_bill_unpaid(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    bill.paid_through = None
    db.session.commit()
    flash("Bill marked as unpaid.", "info")
    return redirect(request.referrer or url_for("main.bills"))

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
    next_url = request.args.get('next')

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
    return redirect(next_url or url_for("main.paychecks"))

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

# Settings Routes
@main.route("/settings/pay-schedule", methods=["GET", "POST"])
def pay_schedule_settings():
    schedule = PaySchedule.query.order_by(PaySchedule.id.desc()).first()
    
    if request.method == "POST":
        anchor_raw = request.form.get("anchor_payday", "").strip()
        if not anchor_raw:
            flash("Please choose an anchor payday.", "danger")
            return redirect(url_for("main.pay_schedule_settings"))
        
        try:
            anchor = date.fromisoformat(anchor_raw)
        except ValueError:
            flash("Invalid date format. Use YYYY-MM-DD.", "danger")
            return redirect(url_for("main.pay_schedule_settings"))
        
        if anchor.weekday() != 4:
            flash("That date is not a Friday. Please select a Friday payday.", "warning")
            return redirect(url_for("main.pay_schedule_settings"))
        
        db.session.add(PaySchedule(anchor_payday=anchor))
        db.session.commit()
        flash("Pay schedule saved.", "success")
        return redirect(url_for("main.pay_schedule_settings"))
    
    return render_template("pay_schedule_settings.html", schedule=schedule)
        

