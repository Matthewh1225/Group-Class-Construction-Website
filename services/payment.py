def create_payment_session(user_id, order_data):
    """Create a payment session through a secure payment provider."""
    pass


def verify_payment(payment_reference):
    """Verify completed payment directly with the payment provider."""
    pass


def process_provider_event(verified_event):
    """Apply a verified payment notification exactly once."""
    pass


def save_payment_method(user_id, provider_reference):
    """Save only an owned provider method reference and display metadata."""
    pass


def request_payment_refund(user_id, payment_id, amount):
    """Validate the payment and request a refund through its provider."""
    pass
