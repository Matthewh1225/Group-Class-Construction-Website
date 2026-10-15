
from flask import render_template


def cart():
    return render_template("cart/cart.html", cart_items=[])


def checkout():
    return render_template("cart/checkout.html", cart_items=[], form_data={}, error=None)


def order_confirmation():
    return render_template("cart/confirmation.html", verified_order=None)
