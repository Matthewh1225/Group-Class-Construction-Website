MAX_QUANTITY = 2_147_483_647


def read_quantity(quantity):
    # TODO: Check that the quantity is a whole number of at least one and is not too large.
    pass


def find_product(cursor, product_id):
    # TODO: Look up the product and its current price, stock, and availability.
    pass


def check_product_available(product, quantity):
    # TODO: Check that the product is still sold, has a price, and has enough stock.
    pass


def get_cart(user_id):
    # TODO: Get the user's cart items with current prices, totals, and any stock problems.
    pass


def add_item(user_id, product_id, quantity):
    # TODO: Add the product to the user's cart, checking the combined quantity if it is already there.
    pass


def change_quantity(user_id, product_id, quantity):
    # TODO: Update an item in the user's cart after checking the quantity and stock.
    pass


def remove_item(user_id, product_id):
    # TODO: Remove this product from the user's cart and say whether it was found.
    pass


def add_materials_to_cart(user_id, materials):
    # TODO: Add matching planner materials to the cart and report what was added, skipped, or failed.
    pass


def add_crew(user_id, crew_json):
    # TODO: Check the crew selection and add it to the user's cart without saving it twice.
    pass


def get_cart_crews(user_id):
    # TODO: Get the user's cart crews with their estimated costs.
    pass


def remove_crew(user_id, crew_id):
    # TODO: Remove this crew selection from the user's cart and say whether it was found.
    pass
