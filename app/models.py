from datetime import date
from .extensions import db

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Other")

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_day = db.Column(db.Integer, nullable=False) # 1-31

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    create_at = db.Column(db.Date, nullable=False, default=date.today)

    paid_through = db.Column(db.Date, nullable=True)

class Paycheck(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    source = db.Column(db.String(120), nullable=False) # e.g. Job, Side Gig
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    pay_date = db.Column(db.Date, nullable=False)

    created_at = db.Column(db.Date, nullable=False, default=date.today)
    
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    spent_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    
    category = db.Column(db.String(50), nullable=False, default="Uncategorized")
    
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    