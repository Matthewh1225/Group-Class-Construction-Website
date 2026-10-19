"Subscription integration placeholders, including unconnected subscription page services."
# The AI Planner's Pro access rules (planning/jobs.py pro_access_allowed) are separate.


from utils.database import database_cursor


# True when the user has an active Pro subscription that has not run out yet.
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT 1 FROM subscriptions
               WHERE user_id = %s AND plan_name = 'Pro' AND status = 'active'
               AND (current_period_end IS NULL OR current_period_end > NOW())
               LIMIT 1""",
            (user_id,),
        )
        return cursor.fetchone() is not None


def get_user_entitlements(user_id):
    "Read verified subscription status and expiry to determine Pro access."
    pass


def update_subscription_from_provider(verified_event):
    "Apply an authenticated provider event exactly once."
    pass


# Returns the user's plan name, status and end date as a dict, or None if they have no subscription.
# An active subscription is preferred over older ones.
def get_user_subscription(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT plan_name, status, current_period_end FROM subscriptions
               WHERE user_id = %s
               ORDER BY (status = 'active') DESC, subscription_id DESC
               LIMIT 1""",
            (user_id,),
        )
        return cursor.fetchone()


def start_pro_subscription(user_id, billing_details):
    "Create checkout; activate access only after a verified provider event."
    pass


def cancel_user_subscription(user_id, reason=None):
    "Cancel an owned subscription through the provider and record the result."
    pass


def resume_user_subscription(user_id):
    "Undo a pending cancellation on an owned subscription."
    pass
