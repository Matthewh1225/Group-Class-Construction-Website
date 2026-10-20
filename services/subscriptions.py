from datetime import date

from utils.database import database_cursor

# Pro is stored as one date on the user: User.proUntil is the last day of Pro access,and NULL means the user never had Pro.
# True when the user's Pro access has not run out yet (proUntil is today or later).
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM `User` WHERE Id = %s AND proUntil >= CURDATE()", (user_id,))
        return cursor.fetchone() is not None


def get_user_entitlements(user_id):
    "Read verified subscription status and expiry to determine Pro access."
    pass


def update_subscription_from_provider(verified_event):
    "Apply an authenticated provider event exactly once."
    pass


# Returns the user's plan name, status ("active" or "expired") and end date as a dict, or None if they never had Pro
def get_user_subscription(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT proUntil FROM `User` WHERE Id = %s", (user_id,))
        row = cursor.fetchone()
    if row is None or row["proUntil"] is None:
        return None
    if row["proUntil"] >= date.today():
        status = "active"
    else:
        status = "expired"
    return {"plan_name": "Pro", "status": status, "current_period_end": row["proUntil"]}


def start_pro_subscription(user_id, billing_details):
    "Create checkout; activate access only after a verified provider event."
    pass


def cancel_user_subscription(user_id, reason=None):
    "Cancel an owned subscription through the provider and record the result."
    pass


def resume_user_subscription(user_id):
    "Undo a pending cancellation on an owned subscription."
    pass
