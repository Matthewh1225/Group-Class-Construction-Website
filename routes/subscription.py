# Subscription UI routes. Payment and subscription services remain stubs.

from flask import Blueprint, render_template, request

from planning.ai_config import WORKFLOW_TIERS
from routes.dashboard import dashboard_login_required

subscription_bp = Blueprint("subscription", __name__)

@subscription_bp.route("/subscription/checkout", methods=["GET", "POST"])
@dashboard_login_required
def checkout():
    # A request cannot initiate payment until the subscription service is implemented.
    failed = request.method == "POST"
    return render_template(
        "subscription/checkout.html", tiers=WORKFLOW_TIERS,
        pro_price=None, checkout_error=failed,
    ), 503 if failed else 200


@subscription_bp.get("/dashboard/subscription")
@dashboard_login_required
def manage():
    return render_template(
        "dashboard/subscription.html", tiers=WORKFLOW_TIERS, pro_price=None,
        subscription=None, payment_method=None, invoices=[],
    )
