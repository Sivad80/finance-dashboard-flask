from datetime import date
import calendar

def next_due_date(due_day: int, today: date) -> date:
    """Return the next due date for a monthly bill given its due_day (1-31)"""
    # Clamp Day to Last Day of This Month
    last_day_this_month = calendar.monthrange(today.year, today.month)[1]
    day = min(due_day, last_day_this_month)
    candidate = date(today.year, today.month, day)
    
    if candidate >= today:
        return candidate
    
    # Move to Next Month
    if today.month == 12:
        year, month = today.year + 1, 1
    else:
        year, month = today.year, today.month + 1
        
    last_day_next_month = calendar.monthrange(year, month)[1]
    day = min(due_day, last_day_next_month)
    return date(year, month, day)

