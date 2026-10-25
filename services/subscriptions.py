from utils.database import database_cursor

PRO_PLANS = {
    "monthly": {
        "name": "Monthly Pro", "amount_cents": 1999, "interval": "month",
        "billing": "Billed monthly",
        "badge": "Stay flexible", "frequency": "per month",
        "detail": "Renews every month", "button_label": "Subscribe to Pro",
        "terms": "Renews at $19.99 every month until canceled."
    },
    "yearly": {
        "name": "Yearly Pro", "amount_cents": 19200, "interval": "year",
        "billing": "Billed yearly",
        "badge": "Save about 20%", "frequency": "per year",
        "button_label": "Subscribe to Pro",
        "terms": "Renews until canceled.",
    },
    "lifetime": {
        "name": "Lifetime Pro", "amount_cents": 100000000, "interval": "once",
        "billing": "One-time payment",
        "badge": "One payment", "frequency": "One-time purchase",
        "detail": "No recurring charges", "button_label": "Complete purchase",
        "terms": "Pay $1,000,000.00 once for lifetime Pro access.",
    },
}


# proDate is the last day of Pro access; NULL means none.
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM Customer WHERE userId = %s AND proDate >= CURDATE()", (user_id,))
        return cursor.fetchone() is not None


def get_user_subscription(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT proDate, proDate >= CURDATE() AS active FROM Customer WHERE userId = %s", (user_id,))
        row = cursor.fetchone()
    if row is None or row["proDate"] is None:
        return None
    if row["active"]:
        status = "active"
    else:
        status = "expired"
    return {"plan_name": "Pro", "status": status, "current_period_end": row["proDate"]}
