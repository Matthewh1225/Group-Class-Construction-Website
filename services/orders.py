"Order service placeholders."


def create_order(user_id, checkout_data):
    "vlidate the cart and stock, Return the order ID, or raise ValueError if it cannot be placed."
   
    pass

def get_user_orders(user_id):
    "Retrieve the user's order history, newest first, ready to show on the Orders page."
    pass

def get_order_by_id(order_id, user_id):
    "Retrieve one of the user's orders for display, or None if it does not exist or belongs to someone else."
    pass

def get_order_items(order_id, user_id):
    "Retrieve the products and quantities in one of the user's orders."
    pass

def get_order_confirmation(order_id, user_id):
    "Retrieve the order and its items for the confirmation page, or None if it is not the user's order."
    pass

def get_order_status(order_id, user_id):
    "Retrieve the current status of an order."
    pass

def cancel_order(user_id, order_id):
    "Cancel the user's own pending order and release its stock. Returns True if it was cancelled."
    pass
