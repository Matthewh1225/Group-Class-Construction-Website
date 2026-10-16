def get_admin_dashboard_statistics():
    "Retrieve administration summary statistics."
    pass


def get_filtered_users(search=None, role=None, page=1, page_size=10, sort_by="username", sort_direction="asc"):
    "Retrieve filtered, sorted, and paginated user records."
    pass


def get_admin_user_details(user_id):
    "Retrieve additional account details for administration."
    pass


def get_user_role_counts():
    "Retrieve total administrator and regular-user counts."
    pass


def get_low_stock_products(threshold=10):
    "Return active products whose stock is at or below the threshold, lowest first."
    pass


def update_product_stock(product_id, new_stock_quantity):
    "Set a product's stock after an admin count. Returns True if the product exists."
    pass


def get_all_orders(status=None, page=1, page_size=20):
    "Return every customer's orders for the admin page, newest first, optionally filtered by status."
    pass


def update_order_status(order_id, new_status):
    "Move an order to processing, shipped, completed or cancelled. Returns True if it changed."
    pass


def set_discount_code_active(discount_id, is_active):
    "Turn a discount code on or off. Returns True if the code exists."
    pass
