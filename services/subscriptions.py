from utils.database import database_cursor

# Prices are stored in cents.
PRO_PLANS = {
    "monthly": {
        "name": "Monthly Pro", "price": 1999, "interval": "month",
        "billing": "Monthly",
        "badge": "Stay flexible", "frequency": "per month",
        "detail": "Monthly plan", "button_label": "Continue",
        "terms": "All prices are in USD."
    },
    "yearly": {
        "name": "Yearly Pro", "price": 19200, "interval": "year",
        "billing": "Yearly",
        "badge": "Save about 20%", "frequency": "per year",
        "button_label": "Continue",
        "terms": "All prices are in USD.",
    },
    "lifetime": {
        "name": "Lifetime Pro", "price": 100000000, "interval": "once",
        "billing": "One-time",
        "badge": "One payment", "frequency": "One-time purchase",
        "detail": "Lifetime plan", "button_label": "Continue",
        "terms": "All prices are in USD.",
    },
}


# pro_expires_on is the last Pro day; NULL means no access.
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM `User` WHERE id = %s AND pro_expires_on >= CURDATE()", (user_id,))
        return cursor.fetchone() is not None


def get_user_subscription(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT pro_expires_on, pro_expires_on >= CURDATE() AS active FROM `User` WHERE id = %s", (user_id,))
        row = cursor.fetchone()
    if row is None or row["pro_expires_on"] is None:
        return None
    if row["active"]:
        status = "active"
    else:
        status = "expired"
    return {"plan_name": "Pro", "status": status, "current_period_end": row["pro_expires_on"]}
