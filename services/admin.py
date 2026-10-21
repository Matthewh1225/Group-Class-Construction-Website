def get_admin_dashboard_statistics():
    pass


def get_filtered_users(search=None, role=None, page=1, page_size=10, sort_by="username", sort_direction="asc"):
    pass


def get_admin_user_details(user_id):
    pass


def get_user_role_counts():
    pass


def get_low_stock_products(threshold=10):
    "Return active products at or below the stock limit, lowest first."
    pass


def update_product_stock(product_id, new_stock_quantity):
    "Return False if the product does not exist."
    pass


def get_all_orders(status=None, page=1, page_size=20):
    "Return all users' orders, newest first."
    pass


def update_order_status(order_id, new_status):
    "Return whether the order status changed."
    pass


def set_discount_code_active(discount_id, is_active):
    "Return False if the discount code does not exist."
    pass
