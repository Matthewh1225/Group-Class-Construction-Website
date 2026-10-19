# Subscription UI routes. Payment and subscription services remain stubs.

from flask import Blueprint, render_template, request, session

from planning.ai_config import WORKFLOW_TIERS
from routes.dashboard import dashboard_login_required
from services.subscriptions import get_user_subscription

subscription_bp = Blueprint("subscription", __name__)


# Public page that describes the Pro tier.
@subscription_bp.get("/subscription/about-pro")
def about_pro():
    return render_template("subscription/about_pro.html", tiers=WORKFLOW_TIERS)


@subscription_bp.route("/subscription/checkout", methods=["GET", "POST"])
@dashboard_login_required
def checkout():
    # A request cannot initiate payment until the subscription service is implemented.
    failed = request.method == "POST"
    return render_template(
        "subscription/checkout.html", tiers=WORKFLOW_TIERS,
        pro_price=None, checkout_error=failed,
    ), 503 if failed else 200


# Shows the user's subscription page 
@subscription_bp.get("/dashboard/subscription")
@dashboard_login_required
def manage():
    return render_template(
        "dashboard/subscription.html", tiers=WORKFLOW_TIERS, pro_price=None,
        subscription=get_user_subscription(session["user_id"]), payment_method=None, invoices=[],
    )
