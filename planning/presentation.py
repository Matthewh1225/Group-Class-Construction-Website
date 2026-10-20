# Small helpers for the plan pages. The templates read the result dict (planning/schemas.py) directly;
# these only add the status label and the store details that come from the database.

from decimal import Decimal, ROUND_CEILING

from services.products import get_products_by_ids

from .schemas import normalize_unit

STATUS_LABELS = {
    "queued": ("Queued for planning", "neutral"),
    "running": ("Preparing your plan", "neutral"),
    "needs_input": ("Details needed", "attention"),
    "failed": ("Planning failed", "attention"),
    "cancelled": ("Cancelled", "neutral"),
    "partial": ("Partial result", "neutral"),
    "complete": ("Complete", "ready"),
}


# Returns (label, tone) for a job's status, for example ("Complete", "ready").
def status_label(job):
    return STATUS_LABELS.get(job.get("status"), ("Status unavailable", "neutral"))


# Text compared without differences in spacing, capitals or a final full stop.
def same_text(text):
    return " ".join(text.split()).rstrip(".").casefold()


# The interpreter's details for the "Planner's interpretation" list, without any
# "Assumption: ..." line whose text the final plan already lists in its own assumptions.
# Details that say something new are kept.
def interpretation_details(specification, result):
    if not specification:
        return []
    final_assumptions = set()
    if result:
        for assumption in result.get("assumptions", []):
            final_assumptions.add(same_text(assumption))
    details = []
    for detail in specification.get("details", []):
        text = detail
        if text.casefold().startswith("assumption:"):
            text = text[len("assumption:"):]
        if same_text(text) in final_assumptions:
            continue
        details.append(detail)
    return details


# How many of a store product to buy for one material, or None when it cannot be worked out.
def buy_quantity(material, product):
    if product is None or material["quantity"] is None:
        return None
    if normalize_unit(material["unit"]) != normalize_unit(product["unit"]):
        return None
    increment = Decimal(str(product["purchase_increment"]))
    if increment <= 0:
        return None
    needed = Decimal(str(material["quantity"]))
    steps = (needed / increment).to_integral_value(rounding=ROUND_CEILING)
    return steps * increment


# Returns a copy of each material with two keys added for the page to show:
#   "product"       the store product read from the database (name, unit, price, stock)              
#   "buy_quantity"  how many to buy 
def add_store_details(materials):
    product_ids = []
    for material in materials:
        if material.get("product_id") is not None:
            product_ids.append(material["product_id"])
    products = get_products_by_ids(product_ids)

    rows = []
    for material in materials:
        row = dict(material)
        row["product"] = products.get(material.get("product_id"))
        row["buy_quantity"] = buy_quantity(material, row["product"])
        rows.append(row)
    return rows
