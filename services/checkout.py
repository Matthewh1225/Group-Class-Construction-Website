"""Cart totals work; order and delivery helpers are still unfinished."""

from decimal import Decimal


def validate_checkout_data(checkout_data):
    "Return cleaned contact and shipping details, or raise ValueError."
    pass

def calculate_order_total(cart_items):
    if not cart_items:
        return {}
    subtotal = Decimal("0")
    for item in cart_items:
        if item["error"] or item["total_cents"] is None:
            return {}
        subtotal += Decimal(item["total_cents"])
    return {"subtotal_cents": int(subtotal), "shipping_cents": 0,
            "tax_cents": 0, "total_cents": int(subtotal)}

def reserve_order_inventory(user_id, order_id):
    "Check the order belongs to the user and reserve stock in the same update."
    pass

def apply_discount_code(user_id, order_id, code):
    "Check the user's eligibility and discount limits before applying it."
    pass

def validate_discount_code(code, user_id, subtotal):
    "Check dates, usage limits and minimum spend. Return (discount or None, error message)."
    pass

def calculate_discount_amount(discount, subtotal):
    "Work out the discount in dollars, capped at the subtotal."
    pass

def release_order_inventory(order_id):
    "Release stock for a cancelled or expired order."
    pass
