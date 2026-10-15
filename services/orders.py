"""Future orders services. Backend implementation is pending."""


def get_user_orders(user_id):
    'the order history for a user.'
    pass


def get_order_by_id(order_id, user_id):
    'single order with ownership validation.'
    pass


def get_order_items(order_id, user_id):
    'Retrieve products and quantities in an order.'
    pass


def get_order_status(order_id, user_id):
    'Retrieve the current status of an order.'
    pass


def create_order(user_id, checkout_data):
    'Create a customer order from validated checkout information.'
    pass


def get_order_confirmation(order_id, user_id):
    "Retrieve verified order and payment details for the order's owner."
    pass
