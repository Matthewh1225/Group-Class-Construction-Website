from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from planning.ai_config import WORKFLOW_TIERS
from routes.auth import login_required
from services.checkout import add_shipping_and_tax, apply_discount, validate_discount_code
from services.payments import list_cards
from services.subscriptions import PRO_PLANS, activate_pro, get_user_subscription

subscription_bp = Blueprint("subscription", __name__)


@subscription_bp.get("/subscription/about-pro")
def about_pro():
    return render_template("subscription/about_pro.html", tiers=WORKFLOW_TIERS)


@subscription_bp.route("/subscription/checkout", methods=["GET", "POST"])
@login_required
def subscribe():
    checkout_error = None
    status = 200
    discount_code = request.form.get("discount_code", "") if request.method == "POST" else ""
    if request.method == "POST":
        selected_plan = request.form.get("plan", "")
        if selected_plan in PRO_PLANS:
            try:
                validate_discount_code(discount_code)
            except ValueError as problem:
                checkout_error = str(problem)
                status = 400
            else:
                # Payments aren't connected yet, so Pro is activated right away.
                expires_on = activate_pro(session["user_id"], selected_plan)
                flash(f"{PRO_PLANS[selected_plan]['name']} is active through {expires_on:%B %d, %Y}.", "success")
                return redirect(url_for("subscription.manage_subscription"), code=303)
        else:
            selected_plan = "yearly"
            checkout_error = "Choose a valid membership plan."
            status = 400
    else:
        selected_plan = request.args.get("plan", "yearly")
        if selected_plan not in PRO_PLANS:
            selected_plan = "yearly"

    plans = {}
    for key, configuration in PRO_PLANS.items():
        plan = dict(configuration)
        plan["savings_cents"] = 0
        if plan["interval"] == "year":
            monthly_cents = plan["price"] / 12
            monthly_price = "${:,.2f}".format(monthly_cents / 100)
            plan["detail"] = monthly_price + "/month equivalent"
            plan["savings_cents"] = PRO_PLANS["monthly"]["price"] * 12 - PRO_PLANS["yearly"]["price"]
        plans[key] = plan
    totals = add_shipping_and_tax(plans[selected_plan]["price"], shipping_cents=0)
    if not checkout_error:
        totals = apply_discount(totals, discount_code)
    return render_template(
        "subscription/checkout.html", tiers=WORKFLOW_TIERS, plans=plans,
        selected_plan=selected_plan, checkout_error=checkout_error,
        totals=totals, discount_code=discount_code,
        saved_cards=list_cards(session["user_id"]),
    ), status


@subscription_bp.get("/dashboard/subscription")
@login_required
def manage_subscription():
    subscription = get_user_subscription(session["user_id"])
    if subscription:
        subscription["period_label"] = "Access through"
        if subscription["status"] == "expired":
            subscription["period_label"] = "Access ended"
    days_left = None
    if subscription and subscription["status"] == "active":
        days_left = (subscription["current_period_end"] - date.today()).days

    plans = []
    for key, plan in PRO_PLANS.items():
        dollars = plan["price"] / 100
        price = "${:,.0f}".format(dollars) if dollars == int(dollars) else "${:,.2f}".format(dollars)
        plans.append({"key": key, "name": plan["name"], "price": price,
                      "frequency": plan["frequency"], "badge": plan["badge"]})
    return render_template(
        "dashboard/subscription.html", tiers=WORKFLOW_TIERS,
        subscription=subscription, days_left=days_left, plans=plans,
    )
