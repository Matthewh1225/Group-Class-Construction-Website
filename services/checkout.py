"""Cart totals work; checkout details are still unfinished."""

from decimal import Decimal


def validate_checkout_data(checkout_data):
    "TODO: return cleaned contact and shipping details, or raise ValueError."
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
