
from decimal import Decimal, ROUND_CEILING

from services.products import get_products_by_ids, normalize_unit
from planning.jobs import pending_stages
# AI planner status labels
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


# Buy whole boxes, bags, or pieces
def round_up_quantity(needed):
    return needed.to_integral_value(rounding=ROUND_CEILING)


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
            "match_status": "unmatched",
            "stock_status": "unknown",
            "insufficient_stock": False,
            "show_store_link": False,
            "line_total": None,
        })
        if product is None:
            if material.get("product_id") is not None:
                row["match_status"] = "missing"
            rows.append(row)
            continue

        row["match_status"] = "matched"
        material_unit = normalize_unit(material["unit"])
        product_unit = normalize_unit(product["unit"])
        units_match = material_unit == product_unit
        if units_match:
            needed = Decimal(str(material["quantity"]))
            row["buy_quantity"] = round_up_quantity(needed)

        stock = product["available_quantity"]
        in_stock = stock > 0
        if in_stock:
            row["stock_status"] = "available"
        else:
            row["stock_status"] = "out_of_stock"

        if units_match:
            has_enough_stock = stock >= row["buy_quantity"]
            row["insufficient_stock"] = not has_enough_stock

        # Allow adding if any stock remains; show shortages separately.
        row["can_add"] = units_match and in_stock
        row["show_store_link"] = not units_match and in_stock
        if row["can_add"]:
            row["line_total"] = row["buy_quantity"] * product["unit_price"]
        rows.append(row)
    return rows


# Combine quantities for each matched product before rounding.
def suggested_items(rows):
    needed = {}
    products = {}
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


def matched_materials_total(items):
    total = Decimal("0")
    for item in items:
        total += item["quantity"] * item["product"]["unit_price"]
    return total


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
