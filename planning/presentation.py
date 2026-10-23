
from decimal import Decimal, ROUND_CEILING

from services.products import get_products_by_ids
from planning.jobs import pending_stages

STATUS_LABELS = {
    "queued": ("Queued for planning", "neutral"),
    "running": ("Preparing your plan", "neutral"),
    "needs_input": ("Details needed", "attention"),
    "failed": ("Planning failed", "attention"),
    "cancelled": ("Cancelled", "neutral"),
    "complete": ("Complete", "ready"),
}


def status_label(job):
    return STATUS_LABELS.get(job.get("status"), ("Status unavailable", "neutral"))


STAGE_STATUS_LABELS = {
    "pending": "Pending", "processing": "Processing", "done": "Done",
    "failed": "Failed", "cancelled": "Cancelled",
}


def stage_rows(job):
    names = {"interpreter": "Interpreter", "planner": "Planner",
             "second_planner": "Planner 2", "auditor": "Auditor"}
    stages = job.get("stages") or {}
    rows = []
    for name in pending_stages(job["tier"]):
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


# Other spellings of a unit that mean the same thing. This is only read, never changed.
UNIT_ALIASES = {"feet": "ft", "foot": "ft", "inches": "in", "inch": "in",
                "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
                "square meters": "sq_m", "sq m": "sq_m", "layers": "count",
                "layer": "count", "coats": "count", "coat": "count",
                "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
                "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag"}


# Plan units and store units must match before a product can be bought.
def normalize_unit(unit):
    text = unit.strip().lower()
    return UNIT_ALIASES.get(text, text)


# Products are purchased as whole sellable units (boxes, bags, pieces, etc.).
def round_up_quantity(needed):
    return needed.to_integral_value(rounding=ROUND_CEILING)


def buy_quantity(material, product):
    if product is None:
        return None
    if normalize_unit(material["unit"]) != normalize_unit(product["unit"]):
        return None
    return round_up_quantity(Decimal(str(material["quantity"])))


# Use current store prices and stock when showing a plan.
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
        row["product"] = product
        row["buy_quantity"] = buy_quantity(material, product)

        row["out_of_stock"] = False
        if product is not None and product["available_quantity"] is not None:
            row["out_of_stock"] = product["available_quantity"] <= 0

        row["can_add"] = row["buy_quantity"] is not None and not row["out_of_stock"]

        row["match_status"] = "unmatched"
        row["stock_status"] = "unknown"
        row["incompatible_units"] = False
        row["insufficient_stock"] = False
        row["show_store_link"] = False
        if product is None:
            if material.get("product_id") is not None:
                row["match_status"] = "missing"
        else:
            row["match_status"] = "matched"
            row["incompatible_units"] = row["buy_quantity"] is None
            row["show_store_link"] = row["incompatible_units"] and not row["out_of_stock"]
            stock = product["available_quantity"]
            if stock is not None:
                if row["out_of_stock"]:
                    row["stock_status"] = "out_of_stock"
                else:
                    row["stock_status"] = "available"
                if row["buy_quantity"] is not None:
                    row["insufficient_stock"] = stock < row["buy_quantity"]

        row["line_total"] = None
        if row["can_add"] and product["unit_price"] is not None:
            row["line_total"] = row["buy_quantity"] * Decimal(str(product["unit_price"]))
        rows.append(row)
    return rows


# Add matching amounts before rounding so shared packs are not bought twice.
def cart_items(rows):
    needed = {}    # amounts by product ID
    products = {}  # products by ID
    for row in rows:
        if not row["can_add"]:
            continue
        product_id = row["product"]["product_id"]
        if product_id not in needed:
            needed[product_id] = Decimal("0")
            products[product_id] = row["product"]
        needed[product_id] += Decimal(str(row["quantity"]))

    items = []
    for product_id in needed:
        product = products[product_id]
        items.append({"product": product, "quantity": round_up_quantity(needed[product_id])})
    return items


def cart_total(items):
    total = Decimal("0")
    for item in items:
        if item["product"]["unit_price"] is not None:
            total += item["quantity"] * Decimal(str(item["product"]["unit_price"]))
    return total
