"Order helpers are not written yet."


def create_order(user_id, checkout_data):
    "Check cart and stock, then return the order ID or raise ValueError."
   
    pass

def get_user_orders(user_id):
    "Return the user's orders, newest first."
    pass

def get_order_by_id(order_id, user_id):
    "Return None if the order is missing or belongs to someone else."
    pass

def get_order_items(order_id, user_id):
    "Include product details and quantities from the user's order."
    pass

def get_order_confirmation(order_id, user_id):
    "Return the order and items, or None if it is not the user's order."
    pass

def get_order_status(order_id, user_id):
    pass

def cancel_order(user_id, order_id):
    "Cancel the user's pending order and release stock. Return whether it was cancelled."
    pass
