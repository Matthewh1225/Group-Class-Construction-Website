from decimal import Decimal, ROUND_HALF_UP


def check_checkout_form(checkout_data):
    """Clean the checkout form. Raises ValueError with a message if something is wrong."""
    cleaned = {}
    cleaned["email_receipt"] = checkout_data.get("email_receipt") == "1"
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


SHIPPING_CENTS = 1999          # flat $19.99 shipping on every order
TAX_RATE = Decimal("0.085")    # 8.5% estimated sales tax


def add_shipping_and_tax(subtotal_cents):
    """Turn a subtotal (in cents) into the full order totals (all in cents)."""
    # Tax is on the items only, rounded to the nearest cent
    tax_cents = int((subtotal_cents * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    total_cents = subtotal_cents + SHIPPING_CENTS + tax_cents
    return {"subtotal_cents": subtotal_cents, "shipping_cents": SHIPPING_CENTS,
            "tax_cents": tax_cents, "total_cents": total_cents}


def calculate_totals(cart_items):
    if not cart_items:
        return None
    subtotal = 0
    for item in cart_items:
        if item.get("error") or item.get("total_cents") is None:
            return None
        subtotal += item["total_cents"]
    return add_shipping_and_tax(subtotal)
