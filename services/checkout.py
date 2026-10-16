"Checkout service placeholders."


def validate_checkout_data(checkout_data):
    "Check the contact and shipping form on the server. Returns the cleaned values, or raises ValueError."
    pass

def calculate_order_total(cart_items):
    "Work out the subtotal, shipping, tax and total (all in cents) for items from get_cart_items. Returns {} if the cart is empty or an item has a problem."
    pass

def reserve_order_inventory(user_id, order_id):
    "Validate an owned order and reserve available stock transactionally."
    pass

def apply_discount_code(user_id, order_id, code):
    "Validate eligibility and limits before applying a discount."
    pass

def validate_discount_code(code, user_id, subtotal):
    "Check a code is active, started, not expired, under its use limit and meets the minimum. Returns (discount row or None, error message)."
    pass

def calculate_discount_amount(discount, subtotal):
    "Return the dollars off for a percent or fixed discount, never more than the subtotal."
    pass

def release_order_inventory(order_id):
    "Give back the stock held for a cancelled or expired order (reservations become 'released')."
    pass
