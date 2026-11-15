

def check_checkout_form(checkout_data):
    """Clean the checkout form. Raises ValueError with a message if something is wrong."""
    cleaned = {}
    for name in ["first_name", "last_name", "email", "phone", "street_address",
                 "apartment", "city", "state", "zip_code"]:
        cleaned[name] = (checkout_data.get(name) or "").strip()

    required = {
        "first_name": "first name", "last_name": "last name", "email": "email",
        "street_address": "street address", "city": "city",
        "state": "state", "zip_code": "ZIP code",
    }
    for name, label in required.items():
        if cleaned[name] == "":
            raise ValueError("Please enter your " + label + ".")

    if "@" not in cleaned["email"] or "." not in cleaned["email"]:
        raise ValueError("Please enter a valid email address.")

    cleaned["state"] = cleaned["state"].upper()
    if len(cleaned["state"]) != 2 or not cleaned["state"].isalpha():
        raise ValueError("State must be a 2 letter abbreviation, like IL.")

    if not cleaned["zip_code"].isdigit() or len(cleaned["zip_code"]) != 5:
        raise ValueError("ZIP code must be 5 digits.")

    return cleaned


def calculate_totals(cart_items):
    if not cart_items:
        return None
    subtotal = 0
    for item in cart_items:
        # A pre-order with no price yet (price TBD) is left out of the subtotal
        if item.get("preorder") and item["total_cents"] is None:
            continue
        if item.get("error") or item.get("total_cents") is None:
            return None
        subtotal += item["total_cents"]
    return {"subtotal_cents": subtotal, "shipping_cents": None, "tax_cents": None, "total_cents": None}
