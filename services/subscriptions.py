"Subscription integration placeholders, including unconnected subscription page services."
# The AI Planner's Pro access rules (planning/jobs.py pro_access_allowed) are separate.


def get_user_entitlements(user_id):
    "Read verified subscription status and expiry to determine Pro access."
    pass


def update_subscription_from_provider(verified_event):
    "Apply an authenticated provider event exactly once."
    pass


def get_user_subscription(user_id):
    "Return the user's plan, status, renewal or end date, and cancellation state."
    pass


def start_pro_subscription(user_id, billing_details):
    "Create checkout; activate access only after a verified provider event."
    pass


def cancel_user_subscription(user_id, reason=None):
    "Cancel an owned subscription through the provider and record the result."
    pass


def resume_user_subscription(user_id):
    "Undo a pending cancellation on an owned subscription."
    pass
