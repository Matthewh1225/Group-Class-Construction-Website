"""Future account helpers; current login and registration are unchanged."""


def issue_account_token(user_id, purpose):
    """Create a hashed, expiring verification or password-reset token."""
    pass


def consume_account_token(token, purpose):
    """Validate and consume an unused token atomically."""
    pass


def link_social_identity(user_id, provider, verified_identity):
    """Link a provider identity after its ownership is verified."""
    pass


def save_user_address(user_id, address_data):
    """Save an owned shipping or billing address and its default choice."""
    pass
