from flask import Blueprint, render_template, request, session

from planning.ai_config import WORKFLOW_TIERS
from routes.auth import login_required
from services.subscriptions import PRO_PLANS, get_user_subscription, process_subscription_payment

subscription_bp = Blueprint("subscription", __name__)


@subscription_bp.get("/subscription/about-pro")
def about_pro():
    return render_template("subscription/about_pro.html", tiers=WORKFLOW_TIERS)


@subscription_bp.route("/subscription/checkout", methods=["GET", "POST"])
@login_required
def subscribe():
    selected_plan = request.args.get("plan", "yearly")
    checkout_error = None
    status = 200
    if request.method == "POST":
        selected_plan = request.form.get("plan", "")

    if selected_plan not in PRO_PLANS:
        selected_plan = "yearly"
        if request.method == "POST":
            checkout_error = "Choose a valid membership plan."
            status = 400
    elif request.method == "POST":
        process_subscription_payment(session["user_id"], selected_plan)
        checkout_error = "Payment processing is not implemented."
        status = 503

    plans = {}
    for key, configuration in PRO_PLANS.items():
        plan = dict(configuration)
        plan["monthly_equivalent"] = ""
        plan["savings_cents"] = 0
        if plan["interval"] == "year":
            monthly_cents = plan["amount_cents"] / 12
            monthly_price = "${:,.2f}".format(monthly_cents / 100)
            plan["detail"] = monthly_price + "/month equivalent"
            plan["savings_cents"] = (PRO_PLANS["monthly"]["amount_cents"] *12 - PRO_PLANS["yearly"]["amount_cents"])*-1;
        plans[key] = plan
    return render_template(
        "subscription/checkout.html", tiers=WORKFLOW_TIERS, plans=plans,
        selected_plan=selected_plan, checkout_error=checkout_error,
    ), status


@subscription_bp.get("/dashboard/subscription")
@login_required
def manage_subscription():
    subscription = get_user_subscription(session["user_id"])
    if subscription:
        subscription["period_label"] = "Current period ends"
        if subscription["status"] in ["cancelled", "expired"]:
            subscription["period_label"] = "Access ends"
    return render_template(
        "dashboard/subscription.html", tiers=WORKFLOW_TIERS,
        subscription=subscription, invoices=[],
    )
