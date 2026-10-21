from datetime import date

from utils.database import database_cursor

# proUntil is the last day of Pro access; NULL means none.
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM `User` WHERE Id = %s AND proUntil >= CURDATE()", (user_id,))
        return cursor.fetchone() is not None


def get_user_entitlements(user_id):
    "Check subscription status and expiry for Pro access."
    pass


def update_subscription_from_provider(verified_event):
    "Apply a verified subscription update only once."
    pass


# No expiry date means there is no subscription.
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
    "Start checkout; wait for a verified payment update before enabling Pro."
    pass


def cancel_user_subscription(user_id, reason=None):
    "Cancel the user's subscription with the provider and save the result."
    pass


def resume_user_subscription(user_id):
    "Undo a pending cancellation on the user's subscription."
    pass
