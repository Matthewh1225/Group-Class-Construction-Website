"Payment helpers are not written yet."


def create_payment_session(user_id, order_data):
    "Start payment through the payment provider."
    pass


def verify_payment(payment_reference):
    "Check payment with the provider, not the browser."
    pass


def process_provider_event(verified_event):
    "Apply a verified payment update only once."
    pass


def save_payment_method(user_id, provider_reference):
    "Save the user's provider reference and display details, not card numbers."
    pass


def request_payment_refund(user_id, payment_id, amount):
    "Check the user's payment before requesting a refund."
    pass


def get_default_payment_method(user_id):
    "Return the default card's brand and last four digits."
    pass


def update_default_payment_method(user_id, provider_reference):
    "Use only a payment method that belongs to the user."
    pass


def list_billing_history(user_id):
    "Return invoice dates, descriptions, amounts, statuses and links, newest first."
    pass


def get_payment_status(order_id, user_id):
    "Return the user's latest order payment status, or None."
    pass
