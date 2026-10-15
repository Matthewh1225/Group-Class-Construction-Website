"""Future checkout services. Backend implementation is pending."""


def validate_checkout_data(checkout_data):
    'Validate customer contact and shipping information on the server.'
    pass


def calculate_order_total(user_id, checkout_data):
    'Calculate the final order total including shipping and tax.'
    pass


def reserve_order_inventory(user_id, order_id):
    'Validate an owned order and reserve available stock transactionally.'
    pass


def apply_discount_code(user_id, order_id, code):
    'Validate eligibility and limits before applying a discount.'
    pass
