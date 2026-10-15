"""Future cart services. Backend implementation is pending."""


def get_cart_items(user_id):
    'Retrieve saved cart items with product details for the current user.'
    pass


def update_cart_quantity(user_id, product_id, quantity):
    "Update a product's quantity in the user's saved cart."
    pass


def remove_cart_item(user_id, product_id):
    "Remove a product from the user's saved cart."
    pass


def calculate_cart_subtotal(user_id):
    'Calculate the saved cart subtotal using current product prices.'
    pass


def add_cart_item(user_id, product_id, quantity):
    'Validate sale units and availability before adding an owned cart item.'
    pass


def add_material_list_to_cart(user_id, material_list_id):
    'Map owned materials to purchasable products and pack quantities.'
    pass
