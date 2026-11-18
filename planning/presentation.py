import re
from decimal import Decimal, ROUND_CEILING

from services import product_specs
from services.products import get_products_by_ids, guess_unit_price, normalize_unit
from planning.jobs import pending_stages

STATUS_LABELS = {
    "queued": ("Queued for planning", "neutral"),
    "running": ("Preparing your plan", "neutral"),
    "needs_input": ("Details needed", "attention"),
    "failed": ("Planning failed", "attention"),
    "cancelled": ("Cancelled", "neutral"),
    "complete": ("Plan ready", "ready"),
}


def status_label(job):
    if job.get("status") == "running" and job.get("stages", {}).get("matcher") == "processing":
        return "Matching products and machinery", "neutral"
    return STATUS_LABELS.get(job.get("status"), ("Status unavailable", "neutral"))


STAGE_STATUS_LABELS = {
    "pending": "Pending", "processing": "Processing", "done": "Done",
    "failed": "Failed", "cancelled": "Cancelled",
}


def stage_rows(job):
    names = {"interpreter": "Interpreter", "planner": "Planner",
             "second_planner": "Planner 2", "auditor": "Auditor", "matcher": "Catalog & Machinery Matcher"}
    stages = job.get("stages") or {}
    rows = []
    for name in pending_stages(job["tier"]):
        # Older plans may not have a Matcher step.
        if name == "matcher" and name not in stages and job.get("status") in ("complete", "failed", "cancelled"):
            continue
        state = stages.get(name, "pending")
        rows.append({"name": name, "label": names[name], "state": state,
                     "status_label": STAGE_STATUS_LABELS.get(state, "Status unavailable")})
    return rows


def format_amount(value):
    if value is None:
        return "Unknown"
    number = float(value)
    if 0 < number < 0.01:
        return "{:g}".format(number)
    return "{:,.2f}".format(number).rstrip("0").rstrip(".")


def project_spec_rows(project):
    rows = []
    for name, value in (project.get("dimensions") or {}).items():
        rows.append({"label": name.replace("_", " ").capitalize(),
                     "value": format_amount(value)})
    hidden_fields = ["dimensions", "description", "project_type", "project_mode",
                     "project_size", "project_template"]
    for name, value in project.items():
        if name in hidden_fields or value is None:
            continue
        if value is True:
            display_value = "Yes"
        elif value is False:
            display_value = "No"
        elif isinstance(value, (int, float, Decimal)):
            display_value = format_amount(value)
        else:
            display_value = value
        rows.append({"label": name.replace("_", " ").capitalize(), "value": display_value})
    return rows


def round_up_quantity(needed):
    return needed.to_integral_value(rounding=ROUND_CEILING)


COUNT_UNITS = ["piece", "screw", "nail"]
# A "piece" of caulk or compound can mean one container.
CONTAINER_SALE_UNITS = product_specs.CONTAINER_SALE_UNITS
# Package counts are usable only when the estimate states the store's package size.
PACKAGE_UNITS = product_specs.PACKAGE_UNITS

# Spellings that mean the same unit inside a size such as "80-lb bag" or "4.5 gal pail".
SIZE_WORDS = {"lbs": "lb", "pound": "lb", "pounds": "lb", "gal": "gallon", "gallons": "gallon",
              "feet": "ft", "foot": "ft", "linear": "", "ounce": "oz", "ounces": "oz", "fl": "",
              "pcs": "piece", "pieces": "piece", "count": "piece", "ct": "piece", "pack": "piece",
              "screws": "piece", "nails": "piece", "square": "sq"}


def size_text(text):
    """Normalize size wording, such as "80-lb" and "80 pounds", to "80 lb"."""
    text = text.lower().replace("×", "x").replace("'", " ft").replace("-", " ").replace("_", " ")
    words = []
    for word in text.split():
        word = SIZE_WORDS.get(word, word)
        if word:
            words.append(word)
    return " ".join(words)


def package_size_stated(material, product):
    """Check whether the estimate states a package size listed for this product."""
    estimate = size_text(" ".join([material.get("material_name") or "", material.get("specification") or "",
                                   material.get("notes") or ""]))
    sizes = []
    if product.get("content_quantity") is not None:
        sizes.append(product_specs.number_text(product["content_quantity"]) + " " + size_text(product["content_unit"]))
    specs = product.get("specs") or {}
    if specs.get("width_ft") and specs.get("length_ft"):
        width = product_specs.number_text(specs["width_ft"])
        length = product_specs.number_text(specs["length_ft"])
        sizes += [f"{width} x {length}", f"{width}x{length}", f"{width} ft x {length} ft"]
    # Sizes written in the product name, such as "10.1 oz" or "100 piece" (from "100-pack").
    sizes += re.findall(r"\d+(?:\.\d+)? (?:oz|lb|gallon|piece|ft)\b", size_text(product.get("product_name") or ""))
    for size in sizes:
        # The number must not be part of a longer number: "8 lb" is not inside "18 lb".
        if re.search(r"(?<![\d./])" + re.escape(size) + r"(?![\d])", estimate):
            return True
    return False


def store_units_needed(material, product):
    """Convert to sale units before rounding, or return None for an unconfirmed pre-order.

    Use catalog sizes only; the estimate already includes waste.
    Only older saved plans have required_specs (and so a min_length_ft).
    """
    material_unit = normalize_unit(material["unit"])
    sale_unit = normalize_unit(product["unit"])
    quantity = Decimal(str(material["quantity"]))
    required = material.get("required_specs") or {}
    min_length = required.get("min_length_ft")

    if material_unit == sale_unit:
        if sale_unit in PACKAGE_UNITS and not package_size_stated(material, product):
            return None  # the estimate's box may hold a different amount than the store's box
        return quantity

    # One sheet of listed sheet goods sold individually is one sale piece.
    if material_unit in {"sheet", "panel"} and sale_unit == "piece":
        if re.search(r"\b(sheet|panel|plywood|osb)\b", product.get("product_name") or "", re.I):
            return quantity

    if material_unit in COUNT_UNITS and sale_unit == "ft":
        # Piece counts need a known length when the store sells by the foot.
        if min_length is None:
            return None
        return quantity * Decimal(str(min_length))

    if material_unit in COUNT_UNITS and sale_unit == "system" and quantity == 1:
        # "1 freight elevator" bought as one "Configurable freight elevator system".
        # Larger counts could be parts of a system, so the customer picks the quantity.
        return quantity

    if material_unit in COUNT_UNITS and sale_unit in CONTAINER_SALE_UNITS:
        if not package_size_stated(material, product):
            return None
        return quantity

    # Everything else, including counts sold as a set or kit, converts only through stated contents.
    content_quantity = product.get("content_quantity")
    content_unit = normalize_unit(product.get("content_unit") or "")
    if content_quantity is None or material_unit != content_unit:
        return None

    if material_unit == "ft" and min_length is not None:
        # Each unbroken piece uses a whole board; leftovers are not shared.
        return round_up_quantity(quantity / Decimal(str(min_length)))
    # Tiny division leftovers must not cause an extra unit when rounding up.
    return (quantity / Decimal(str(content_quantity))).quantize(Decimal("0.000001"))


def make_preorder(material, product, buy_quantity):
    if product is not None and buy_quantity is not None:
        return {
            "product_id": product["product_id"],
            "name": product["product_name"],
            "unit": product["unit"],
            "quantity": buy_quantity,
            "unit_price": product["unit_price"],
            "price_note": None,
        }

    name = material["material_name"]
    if material.get("specification"):
        name += " (" + material["specification"] + ")"
    unit_price = material.get("estimated_unit_price")
    if unit_price is not None and unit_price > 0:
        unit_price = Decimal(str(unit_price)).quantize(Decimal("0.01"))
        price_note = "AI estimate"
    else:
        # Older plans have no AI price, so make a rough guess from the unit
        unit_price = guess_unit_price(material["unit"])
        price_note = "rough estimate"
    return {
        "product_id": None,
        "name": name[:255],
        "unit": material["unit"][:50],
        "quantity": Decimal(str(material["quantity"])).quantize(Decimal("0.01")),
        "unit_price": unit_price,
        "price_note": price_note,
    }


def block_reason_for(row, product):
    """Why a matched product can't go straight into the cart, or None when it can."""
    if row["buy_quantity"] is None:
        return "quantity not converted"
    if product["available_quantity"] < row["buy_quantity"]:
        return "not enough stock"
    return None


def add_store_details(materials):
    product_ids = []
    for material in materials:
        if material.get("product_id") is not None:
            product_ids.append(material["product_id"])
    products = get_products_by_ids(product_ids)

    rows = []
    for material in materials:
        row = dict(material)
        product = products.get(material.get("product_id"))
        row.update({
            "product": product,
            "buy_quantity": None,
            "can_add": False,
            "has_partial_stock": False,
            "in_stock_quantity": None,
            "remaining_quantity": None,
            "remaining_preorder": None,
            "in_stock_total": None,
            "remaining_total": None,
            "match_status": "unmatched",
            "stock_status": "unknown",
            "show_store_link": False,
            "line_total": None,
            "preorder": None,
            "block_reason": None,
        })

        if product is not None:
            if product["available_quantity"] > 0:
                row["stock_status"] = "available"
            else:
                row["stock_status"] = "out_of_stock"
            row["match_status"] = "matched"
            needed = store_units_needed(material, product)
            if needed is not None:
                row["buy_quantity"] = round_up_quantity(needed)
            # Without a confirmed quantity, the user can still look at the product in the store.
            row["show_store_link"] = needed is None and product["available_quantity"] > 0
            row["block_reason"] = block_reason_for(row, product)
        elif material.get("product_id") is not None:
            row["match_status"] = "missing"

        if product is not None and row["block_reason"] is None:
            row["can_add"] = True
            row["in_stock_quantity"] = row["buy_quantity"]
            row["line_total"] = row["buy_quantity"] * product["unit_price"]
        elif product is not None and row["block_reason"] == "quantity not converted":
            # A stocked listing with an unknown conversion needs a customer-selected quantity.
            row["show_store_link"] = True
        else:
            row["preorder"] = make_preorder(material, product, row["buy_quantity"])
            row["line_total"] = row["preorder"]["quantity"] * row["preorder"]["unit_price"]
            if (row["block_reason"] == "not enough stock"
                    and row["buy_quantity"] is not None
                    and product is not None
                    and product["available_quantity"] > 0):
                available = Decimal(str(product["available_quantity"]))
                if available < row["buy_quantity"]:
                    row["has_partial_stock"] = True
                    row["in_stock_quantity"] = available
                    row["remaining_quantity"] = row["buy_quantity"] - available
                    if product.get("unit_price") is not None:
                        row["in_stock_total"] = row["in_stock_quantity"] * product["unit_price"]
                        row["remaining_total"] = row["remaining_quantity"] * product["unit_price"]
                    row["remaining_preorder"] = make_preorder(material, product, row["remaining_quantity"])
        rows.append(row)
    return rows


def in_stock_summary(rows):
    """Count of different in-stock products and their subtotal, matching "Add all to cart"."""
    product_ids = set()
    subtotal = Decimal("0")
    for row in rows:
        if row["can_add"]:
            product_ids.add(row["product"]["product_id"])
            subtotal += row["line_total"]
        elif row.get("has_partial_stock") and row.get("in_stock_total") is not None:
            product_ids.add(row["product"]["product_id"])
            subtotal += row["in_stock_total"]
    return len(product_ids), subtotal


def add_machinery_details(machinery):
    products = get_products_by_ids([item["product_id"] for item in machinery])
    rows = []
    for item in machinery:
        row = dict(item)
        product = products.get(item["product_id"])
        if product is not None and product["category"] != "heavy-machinery":
            product = None
        row["product"] = product
        row["line_total"] = None
        if product is not None and product["unit_price"] is not None:
            row["line_total"] = item["quantity"] * product["unit_price"]
        rows.append(row)
    return rows
