import secrets

from flask import flash, redirect, render_template, request, session, url_for

from routes.dashboard import dashboard_login_required
from services.cart import add_cart_item, get_cart_items, remove_cart_item, update_cart_quantity
from services.checkout import calculate_order_total, validate_checkout_data
from services.orders import create_order, get_order_confirmation

# These functions are registered in app.py (add_url_rule) so their endpoint names stay "cart", "checkout" and so on, which the templates use.
# Every one needs a signed-in user.
# Payment is FAKE: checkout saves a "test" payment and charges nothing (services/orders.py).

# Shows the items in the cart with their totals.
@dashboard_login_required
def cart():
    items = get_cart_items(session["user_id"])
    return render_template("cart/cart.html", cart_items=items, totals=calculate_order_total(items))


# Adds a product to the cart, then returns to the product list.
@dashboard_login_required
def cart_add():
    product_id = request.form.get("product_id", type=int)
    try:
        product_name = add_cart_item(session["user_id"], product_id, request.form.get("quantity"))
        if product_name == None:
            product_name="no name for Product"
        else:
            flash("Added " + product_name + " to your cart.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("products.products", category=request.form.get("category") or None,
                            q=request.form.get("q") or None, page=request.form.get("page", type=int),
                            _anchor="catalog-results"), code=303)


# Changes how many of a product are in the cart.
@dashboard_login_required
def cart_update():
    product_id = request.form.get("product_id", type=int)
    try:
        update_cart_quantity(session["user_id"], product_id, request.form.get("quantity"))
        flash("Cart updated.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("cart"), code=303)


# Takes a product out of the cart.
@dashboard_login_required
def cart_remove():
    product_id = request.form.get("product_id", type=int)
    remove_cart_item(session["user_id"], product_id)
    flash("Item removed.", "success")
    return redirect(url_for("cart"), code=303)


# GET shows the checkout form. POST checks the form and places the order, or shows the error.
@dashboard_login_required
def checkout():
    user_id = session["user_id"]
    form_data = {}
    error = None

    if request.method == "POST":
        form_data = request.form.to_dict()
        try:
            checkout_data = validate_checkout_data(request.form)
            order_id = create_order(user_id, checkout_data)
            return redirect(url_for("order_confirmation", order_id=order_id), code=303)
        except ValueError as problem:
            error = str(problem)

    items = get_cart_items(user_id)
    # Reuse the key after validation errors so retrying the form cannot create a second order.
    checkout_key = form_data.get("checkout_key") or secrets.token_urlsafe(24)
    page = render_template("cart/checkout.html", cart_items=items, totals=calculate_order_total(items),
                           form_data=form_data, error=error, checkout_key=checkout_key)
    if error:
        return page, 400
    return page

#shown after an order is placed..
@dashboard_login_required
def order_confirmation(order_id):
    order = None
    if order_id is not None:
        order = get_order_confirmation(order_id, session["user_id"])
    return render_template("cart/confirmation.html", verified_order=order)
