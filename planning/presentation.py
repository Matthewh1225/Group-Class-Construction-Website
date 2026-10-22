
from decimal import Decimal, ROUND_CEILING

from services.products import get_products_by_ids

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


# Plan units and store units must match before a product can be bought.
def normalize_unit(unit):
    aliases = {"feet": "ft", "foot": "ft", "inches": "in", "inch": "in",
               "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
               "square meters": "sq_m", "sq m": "sq_m", "layers": "count",
               "layer": "count", "coats": "count", "coat": "count",
               "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
               "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag"}
    text = unit.strip().lower()
    return aliases.get(text, text)


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
