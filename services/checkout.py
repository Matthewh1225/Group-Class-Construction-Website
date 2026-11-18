from decimal import Decimal, ROUND_HALF_UP, localcontext


US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def check_checkout_form(checkout_data):
    """Clean the checkout form. Raises ValueError with a message if something is wrong."""
    cleaned = {}
    cleaned["email_receipt"] = checkout_data.get("email_receipt") == "1"
    for name in ["first_name", "last_name", "phone", "street_address",
                 "apartment", "city", "state", "zip_code"]:
        cleaned[name] = (checkout_data.get(name) or "").strip()

    required = {
        "first_name": "first name", "last_name": "last name",
        "street_address": "street address", "city": "city",
        "state": "state", "zip_code": "ZIP code",
    }
    for name, label in required.items():
        if cleaned[name] == "":
            raise ValueError("Please enter your " + label + ".")

    cleaned["state"] = cleaned["state"].upper()
    if len(cleaned["state"]) != 2 or not cleaned["state"].isalpha():
        raise ValueError("State must be a 2 letter abbreviation, like IL.")

    if not cleaned["zip_code"].isdigit() or len(cleaned["zip_code"]) != 5:
        raise ValueError("ZIP code must be 5 digits.")

    cleaned["shipping_method"] = get_shipping_method(checkout_data.get("shipping_method"))["key"]
    return cleaned


SHIPPING_METHODS = {
    "standard": {
        "key": "standard",
        "label": "Standard",
        "price_cents": 999,
        "price_display": "$9.99",
        "description": "Reliable ground delivery in 3–5 business days.",
    },
    "two_day": {
        "key": "two_day",
        "label": "2-Day",
        "price_cents": 1999,
        "price_display": "$19.99",
        "description": "Expedited delivery to your job site in 2 business days.",
    },
    "quantum": {
        "key": "quantum",
        "label": "Quantum",
        "price_cents": 100000000,
        "price_display": "$1,000,000.00",
        "description": "Teleported through a wormhole. Arrived yesterday; do not observe the box or Schrödinger's drywall will collapse.",
    },
}
DEFAULT_SHIPPING_METHOD = "standard"
DEFAULT_SHIPPING_CENTS = SHIPPING_METHODS[DEFAULT_SHIPPING_METHOD]["price_cents"]


def get_shipping_method(key):
    norm = (key or "").strip().lower().replace("-", "_")
    if norm in ("2_day", "2day"):
        norm = "two_day"
    return SHIPPING_METHODS.get(norm, SHIPPING_METHODS[DEFAULT_SHIPPING_METHOD])


TAX_RATE = Decimal("0.085")    # 8.5% estimated sales tax
DISCOUNT_CODES = {
    "BUILD10": ("Build10", Decimal("0.10")),
    "ADMIN": ("ADMIN", Decimal("0.9999999")),
}


def add_shipping_and_tax(subtotal_cents, shipping_cents=DEFAULT_SHIPPING_CENTS):
    """Turn a subtotal (in cents) into the full order totals (all in cents)."""
    # Tax is on the items only, rounded to the nearest cent
    subtotal_cents = int(subtotal_cents)
    with localcontext() as context:
        context.prec = max(28, len(str(abs(subtotal_cents))) + 10)
        tax_cents = int((subtotal_cents * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    total_cents = subtotal_cents + shipping_cents + tax_cents
    return {"subtotal_cents": subtotal_cents, "shipping_cents": shipping_cents,
            "tax_cents": tax_cents, "total_cents": total_cents}


def validate_discount_code(code):
    """Return a known discount code in its display form, or raise ValueError."""
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    if normalized not in DISCOUNT_CODES:
        raise ValueError("That discount code is not valid.")
    return DISCOUNT_CODES[normalized][0]


def apply_discount(totals, discount_code):
    """Apply a percentage discount last to the full order (subtotal, shipping, and tax)."""
    normalized = validate_discount_code(discount_code)
    if normalized is None:
        return totals

    rate = DISCOUNT_CODES[normalized.upper()][1]
    gross_total = totals["subtotal_cents"] + totals["shipping_cents"] + totals["tax_cents"]
    with localcontext() as context:
        context.prec = max(28, len(str(abs(gross_total))) + 10)
        discount_cents = int(
            (gross_total * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    new_totals = dict(totals)
    new_totals["subtotal_cents"] = totals["subtotal_cents"]
    new_totals["shipping_cents"] = totals["shipping_cents"]
    new_totals["tax_cents"] = totals["tax_cents"]
    new_totals["discount_cents"] = discount_cents
    new_totals["discount_code"] = normalized
    new_totals["discount_percent"] = float(rate * 100)
    new_totals["discounted_subtotal_cents"] = totals["subtotal_cents"]
    new_totals["total_cents"] = gross_total - discount_cents
    return new_totals


def calculate_totals(cart_items, discount_code=None, shipping_method=None):
    if not cart_items:
        validate_discount_code(discount_code)
        return None
    subtotal = 0
    for item in cart_items:
        if item.get("error") or item.get("total_cents") is None:
            return None
        subtotal += int(item["total_cents"])
    method = get_shipping_method(shipping_method)
    totals = apply_discount(add_shipping_and_tax(subtotal, shipping_cents=method["price_cents"]), discount_code)
    totals["shipping_method"] = method["key"]
    totals["shipping_label"] = method["label"]
    totals["in_stock_cents"] = sum(item["total_cents"] for item in cart_items
                                  if not item.get("preorder") and not item.get("crew"))
    totals["preorder_cents"] = sum(item["total_cents"] for item in cart_items if item.get("preorder"))
    totals["crew_cents"] = sum(item["total_cents"] for item in cart_items if item.get("crew"))
    return totals
