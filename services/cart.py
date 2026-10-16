"Cart service placeholders."


def read_quantity(text):
    "Turn the text typed in a quantity box into a Decimal. Raises ValueError if it is not a positive number."
    pass

def get_cart_items(user_id):
    "Retrieve saved cart items with product details for the current user."
    pass

def add_cart_item(user_id, product_id, quantity):
    "Add a product to the user's cart (adding it again increases the quantity). Returns the product name."
    pass

def update_cart_quantity(user_id, product_id, quantity):
    "Set a product's quantity in the user's cart."
    pass

def remove_cart_item(user_id, product_id):
    "Remove a product from the user's cart."
    pass

def calculate_cart_subtotal(user_id):
    "Calculate the saved cart subtotal using current product prices."
    pass

def add_material_list_to_cart(user_id, material_list_id):
    "Map owned materials to purchasable products and pack quantities."
    pass

def clear_cart(user_id):
    "Remove every item from the user's cart. (Checkout empties the cart itself, inside its transaction.)"
    pass
