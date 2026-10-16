"Payment and billing service placeholders; billing functions are not yet called."


def create_payment_session(user_id, order_data):
    "Create a payment session through a secure payment provider."
    pass


def verify_payment(payment_reference):
    "Verify completed payment directly with the payment provider."
    pass


def process_provider_event(verified_event):
    "Apply a verified payment notification exactly once."
    pass


def save_payment_method(user_id, provider_reference):
    "Save only an owned provider method reference and display metadata."
    pass


def request_payment_refund(user_id, payment_id, amount):
    "Validate the payment and request a refund through its provider."
    pass


def get_default_payment_method(user_id):
    "Return the brand and last four digits of the user's default saved method."
    pass


def update_default_payment_method(user_id, provider_reference):
    "Replace the default saved method with an owned provider method reference."
    pass


def list_billing_history(user_id):
    "Return the user's subscription_invoices rows (date, description, amount, status, link), newest first."
    pass


def get_payment_status(order_id, user_id):
    "Return the latest payment status for the user's own order, or None if there is no payment."
    pass
