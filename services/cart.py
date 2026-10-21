"Cart helpers are not written yet."


def read_quantity(text):
    "Return a positive Decimal, or raise ValueError."
    pass

def get_cart_items(user_id):
    "Include current product details with the cart items."
    pass

def add_cart_item(user_id, product_id, quantity):
    "Add to any existing quantity and return the product name."
    pass

def update_cart_quantity(user_id, product_id, quantity):
    pass

def remove_cart_item(user_id, product_id):
    pass

def calculate_cart_subtotal(user_id):
    "Use current product prices."
    pass

def add_material_list_to_cart(user_id, material_list_id):
    "Use the user's materials and round amounts to store pack sizes."
    pass

def clear_cart(user_id):
    "Checkout clears the cart as part of saving the order."
    pass
