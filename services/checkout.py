

def check_checkout_form(checkout_data):
    # TODO: Clean up contact and delivery details, and report missing or invalid fields.
    pass

def calculate_totals(cart_items):
    if not cart_items:
        return None
    subtotal = 0
    for item in cart_items:
        if item.get("error") or item.get("total_cents") is None:
            return None
        subtotal += item["total_cents"]
    return {"subtotal_cents": subtotal, "shipping_cents": None, "tax_cents": None, "total_cents": None}
