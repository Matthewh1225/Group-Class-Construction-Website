import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from routes.auth import login_required
from services.cart import (get_cart, add_item, change_quantity, remove_item,
                           add_crew, get_cart_crews, remove_crew)
from services.checkout import calculate_totals, check_checkout_form
from services.orders import create_order, get_order, get_order_items

shopping_bp = Blueprint("shopping", __name__)


@shopping_bp.get("/cart")
@login_required
def show_cart():
    items = get_cart(session["user_id"])
    return render_template("cart/cart.html", cart_items=items, totals=calculate_totals(items),
                           crew_items=get_cart_crews(session["user_id"]))


@shopping_bp.post("/cart/add")
@login_required
def add_to_cart():
    try:
        name = add_item(session["user_id"], request.form.get("product_id", type=int), request.form.get("quantity"))
        flash("Added " + name + " to your cart.", "success")
    except ValueError as error:
        flash(str(error), "error")
    endpoint = "products.products"
    if request.form.get("category") == "heavy-machinery":
        endpoint = "products.heavy_machinery"
    return redirect(url_for(endpoint, category=request.form.get("category"),query=request.form.get("query"), page=request.form.get("page", 1, type=int),
                            manufacturer=request.form.get("manufacturer", type=int)), code=303)


@shopping_bp.post("/cart/update")
@login_required
def update_cart():
    try:
        change_quantity(session["user_id"], request.form.get("product_id", type=int), request.form.get("quantity"))
        flash("Cart quantity updated.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("shopping.show_cart"), code=303)


@shopping_bp.post("/cart/remove")
@login_required
def remove_from_cart():
    remove_item(session["user_id"], request.form.get("product_id", type=int))
    return redirect(url_for("shopping.show_cart"), code=303)


@shopping_bp.post("/cart/crews/add")
@login_required
def add_crew_to_cart():
    try:
        name = add_crew(session["user_id"], request.form.get("crew"))
        flash("Added " + name + " to your cart.", "success")
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("crews.crews"), code=303)
    return redirect(url_for("shopping.show_cart"), code=303)


@shopping_bp.post("/cart/crews/<int:crew_id>/remove")
@login_required
def remove_crew_from_cart(crew_id):
    remove_crew(session["user_id"], crew_id)
    return redirect(url_for("shopping.show_cart"), code=303)


@shopping_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    user_id = session["user_id"]
    form_data = {}
    error = None

    if request.method == "POST":
        form_data = request.form.to_dict()
        try:
            checkout_data = check_checkout_form(request.form)
            order_id = create_order(user_id, checkout_data)
        except ValueError as problem:
            error = str(problem)
        else:
            if order_id is not None:
                return redirect(url_for("shopping.order_confirmation", order_id=order_id), code=303)
            error = "Placing orders is not available yet."

    items = get_cart(user_id)
    # TODO: Reject reused keys in create_order so double clicks create only one order.
    checkout_key = form_data.get("checkout_key") or secrets.token_urlsafe(24)
    page = render_template("cart/checkout.html", cart_items=items, totals=calculate_totals(items),
                           form_data=form_data, error=error, checkout_key=checkout_key)
    if error:
        return page, 400
    return page


@shopping_bp.route("/order-confirmation", defaults={"order_id": None})
@shopping_bp.route("/order-confirmation/<int:order_id>")
@login_required
def order_confirmation(order_id):
    order = None
    if order_id is not None:
        order = get_order(order_id, session["user_id"])
    if order is not None:
        order["items"] = get_order_items(order_id, session["user_id"])
    return render_template("cart/confirmation.html", verified_order=order)
