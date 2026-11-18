from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from routes.auth import login_required
from services.cart import (get_cart_contents, add_item, change_quantity, remove_item, clear_cart,
                           add_crew, get_cart_crews, remove_crew,
                           remove_preorder)
from services.checkout import calculate_totals, check_checkout_form, validate_discount_code, SHIPPING_METHODS, DEFAULT_SHIPPING_METHOD, US_STATES
from services.payments import list_cards, checkout_payment
from services.orders import add_receipt_totals, create_order, get_order, get_order_items

shopping_bp = Blueprint("shopping", __name__)


@shopping_bp.get("/cart")
@login_required
def show_cart():
    items, preorders = get_cart_contents(session["user_id"])
    crews = get_cart_crews(session["user_id"])
    everything = items + preorders + crews
    discount_code = request.args.get("discount_code", "")
    try:
        totals = calculate_totals(everything, discount_code)
    except ValueError as error:
        flash(str(error), "error")
        totals = calculate_totals(everything)
    return render_template("cart/cart.html", cart_items=items, preorder_items=preorders,
                           crew_items=crews, summary_items=everything,
                           totals=totals, discount_code=discount_code)


@shopping_bp.post("/cart/add")
def add_to_cart():
    endpoint = "products.products"
    if request.form.get("category") == "heavy-machinery":
        endpoint = "products.heavy_machinery"
    catalog_url = url_for(endpoint, category=request.form.get("category"), query=request.form.get("query"), sort=request.form.get("sort"), page=request.form.get("page", 1, type=int),
                          manufacturer=request.form.get("manufacturer", type=int))

    if "user_id" not in session:
        # Log in first; the item is added and they come back to this page afterwards.
        session["after_login"] = {
            "next": catalog_url,
            "add_product": {"product_id": request.form.get("product_id", type=int),
                            "quantity": request.form.get("quantity")},
        }
        flash("Log in to add items to your cart.", "message")
        return redirect(url_for("auth.login"), code=303)

    try:
        name = add_item(session["user_id"], request.form.get("product_id", type=int), request.form.get("quantity"))
        flash("Added " + name + " to your cart.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(catalog_url, code=303)


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


@shopping_bp.post("/cart/remove-all")
@login_required
def remove_all_from_cart():
    clear_cart(session["user_id"])
    return redirect(url_for("shopping.show_cart"), code=303)


@shopping_bp.post("/cart/preorders/<int:preorder_id>/remove")
@login_required
def remove_preorder_from_cart(preorder_id):
    remove_preorder(session["user_id"], preorder_id)
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
            discount_code = validate_discount_code(request.form.get("discount_code"))
            checkout_data = check_checkout_form(request.form)
            checkout_data["discount_code"] = discount_code
            card, save_new = checkout_payment(user_id, request.form)
            checkout_data["mock_card"] = card
            checkout_data["save_card"] = save_new
            order_id = create_order(user_id, checkout_data)
        except ValueError as problem:
            error = str(problem)
        else:
            return redirect(url_for("shopping.order_confirmation", order_id=order_id), code=303)
    elif request.args.get("discount_code"):
        form_data["discount_code"] = request.args["discount_code"]
        try:
            validate_discount_code(form_data["discount_code"])
        except ValueError as problem:
            error = str(problem)

    shipping_method = form_data.get("shipping_method") or request.args.get("shipping_method") or DEFAULT_SHIPPING_METHOD
    form_data.setdefault("shipping_method", shipping_method)
    items, preorders = get_cart_contents(user_id)
    items += preorders + get_cart_crews(user_id)
    try:
        totals = calculate_totals(items, form_data.get("discount_code"), shipping_method=shipping_method)
    except ValueError:
        totals = calculate_totals(items, shipping_method=shipping_method)
    page = render_template("cart/checkout.html", cart_items=items, totals=totals,
                           form_data=form_data, error=error,
                           saved_cards=list_cards(user_id),
                           shipping_methods=SHIPPING_METHODS, states=US_STATES)
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
        add_receipt_totals(order, order["items"])
    return render_template("cart/confirmation.html", verified_order=order)
