from decimal import Decimal
import re

from services import product_specs, vector_search
from utils.database import database_cursor

PAGE_SIZES = [10, 25, 50, 100]
DEFAULT_PAGE_SIZE = 25
# Drill-driver, exterior wood screws, tape measure, claw hammer, wood glue, excavator and wheel loader.
FEATURED_PRODUCT_IDS = (1016, 4031, 1062, 1006, 4059, 1019, 1021)
CATALOG_SORTS = {
    "price_asc": ("Price: low to high", "p.price ASC, p.name ASC, p.id ASC"),
    "price_desc": ("Price: high to low", "p.price DESC, p.name ASC, p.id ASC"),
    "name_asc": ("Name: A–Z", "p.name ASC, p.id ASC"),
    "name_desc": ("Name: Z–A", "p.name DESC, p.id ASC"),
}


def name_match_order(query):
    """Prefer a product explicitly named by a short query, including its typed size."""
    words = list(dict.fromkeys(re.findall(r"[\w#]+(?:[./-][\w]+)*", query)))
    if not words or len(query) > 200:
        return "", []
    checks = " AND ".join("LOCATE(%s, p.name) > 0" for _ in words)
    return "(LOCATE(%s, p.name) > 0) DESC, (" + checks + ") DESC, ", [query.strip(), *words]


UNIT_ALIASES = {"linear_ft": "ft", "linear feet": "ft", "each": "piece", "feet": "ft", "foot": "ft", "inches": "in", "inch": "in", "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
                "square meters": "sq_m", "sq m": "sq_m", "layers": "count", "layer": "count", "coats": "count", "coat": "count", "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
                "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag",
                # Only spellings of the same physical unit belong here.
                "ea": "piece", "pcs": "piece", "square foot": "sq_ft", "linear foot": "ft",
                "cubic_yard": "cu_yd", "cubic yard": "cu_yd", "cubic yards": "cu_yd",
                # Container aliases share a name, but conversions still need the package size.
                "bucket": "pail", "buckets": "pail", "pails": "pail",
                "cartridge": "tube", "cartridges": "tube", "tubes": "tube", "cans": "can",
                "lbs": "lb", "pound": "lb", "pounds": "lb", "gal": "gallon"}


def normalize_unit(unit):
    text = unit.strip().lower()
    return UNIT_ALIASES.get(text, text)


# Fallback unit prices when no store or planner price is available.
ROUGH_UNIT_PRICES = {
    "piece": 25, "unit": 25, "item": 25, "ft": 3, "board_ft": 6, "sq_ft": 5,
    "sheet": 40, "tile": 5, "gallon": 45, "quart": 20, "bottle": 15, "tube": 10,
    "bag": 15, "box": 30, "bundle": 30, "pack": 20, "roll": 50, "set": 60, "kit": 60,
    "pail": 60, "panel": 50, "lb": 3, "ton": 2200, "cu_yd": 150,
    "cu_ft": 6,
}
DEFAULT_ROUGH_PRICE = 25


def guess_unit_price(unit):
    """Return a rough price (a Decimal) for one unit of a material."""
    price = ROUGH_UNIT_PRICES.get(normalize_unit(unit), DEFAULT_ROUGH_PRICE)
    return Decimal(price).quantize(Decimal("0.01"))


def get_manufacturers_by_category():
    """Return {category: [manufacturers]} for active products; a maker appears once per category."""
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT p.category, m.id AS manufacturer_id, m.name
            FROM Manufacturer m
            JOIN Manufacturer_products mp ON mp.manid = m.id
            JOIN Product p ON p.id = mp.productId
            WHERE p.isActive = 1
            ORDER BY m.name
        """)
        rows = cursor.fetchall()

    groups = {}
    for row in rows:
        groups.setdefault(row["category"], []).append(
            {"manufacturer_id": row["manufacturer_id"], "name": row["name"]})
    return groups


def get_manufacturer(manufacturer_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT id AS manufacturer_id, name FROM Manufacturer WHERE id = %s",
                       (manufacturer_id,))
        return cursor.fetchone()


def search_products(search=None, category_url_name=None, page=1, manufacturer_id=None, sort=None, per_page=DEFAULT_PAGE_SIZE, subcategory=None):
    sql = """
        SELECT p.id AS product_id, p.name AS product_name, p.details, p.description,
               p.sku, p.sale_unit AS unit, p.category, p.subCategory AS subcategory,
               p.content_quantity, p.content_unit,
               p.price AS unit_price, p.stockQty AS available_quantity,
               (SELECT m.name FROM Manufacturer_products mp
                JOIN Manufacturer m ON m.id = mp.manid
                WHERE mp.productId = p.id
                ORDER BY m.name LIMIT 1) AS manufacturer_name
    """
    filters = " FROM Product p WHERE p.isActive = 1"
    # Keep user input in SQL parameters.
    values = []

    if manufacturer_id is not None:
        filters += " AND EXISTS (SELECT 1 FROM Manufacturer_products mp WHERE mp.productId = p.id AND mp.manid = %s)"
        values.append(manufacturer_id)

    if search:
        for word in product_specs.normalize_search(search).split():
            if word == 'x': continue
            pattern = "%" + word + "%"
            filters += " AND (p.search_text LIKE %s OR p.sku LIKE %s)"
            values.extend([pattern, pattern])

    if category_url_name:
        filters += " AND p.category = %s"
        values.append(category_url_name)
        if subcategory:
            filters += " AND p.subCategory = %s"
            values.append(subcategory)
    else:
        filters += " AND p.category <> %s"
        values.append("heavy-machinery")

    with database_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total" + filters, values)
        total = cursor.fetchone()["total"]
        total_pages = max(1, (total + per_page - 1) // per_page)
        if page == 0 and not (search or category_url_name or manufacturer_id or sort):
            placeholders = ", ".join(["%s"] * len(FEATURED_PRODUCT_IDS))
            cursor.execute(sql + f" FROM Product p WHERE p.isActive = 1 AND p.id IN ({placeholders})"
                           f" ORDER BY FIELD(p.id, {placeholders})", FEATURED_PRODUCT_IDS * 2)
            return cursor.fetchall(), total_pages
        selected_sort = sort if sort in CATALOG_SORTS else (
            "price_desc" if category_url_name == "heavy-machinery" else "name_asc")
        order_by = CATALOG_SORTS[selected_sort][1]
        rank_values = []
        if search and sort not in CATALOG_SORTS:
            priority, rank_values = name_match_order(search)
            order_by = priority + order_by
        cursor.execute(sql + filters + " ORDER BY " + order_by + " LIMIT %s OFFSET %s",
                       values + rank_values + [per_page, max(0, page - 1) * per_page])
        products = cursor.fetchall()

    return products, total_pages


def get_subcategories(category):
    if not category:
        return []
    with database_cursor() as cursor:
        cursor.execute('SELECT DISTINCT subCategory AS name FROM Product WHERE category = %s AND isActive = 1 ORDER BY subCategory', (category,))
        return [row['name'] for row in cursor.fetchall()]


def get_catalog_classifications():
    """Return {category: [subcategories]} for active products, for the auditor."""
    with database_cursor() as cursor:
        cursor.execute("SELECT DISTINCT category, subCategory FROM Product WHERE isActive = 1 ORDER BY category, subCategory")
        rows = cursor.fetchall()
    classifications = {}
    for row in rows:
        classifications.setdefault(row["category"], []).append(row["subCategory"])
    return classifications


# Give the matcher product facts and purchase sizes.
PLANNER_PRODUCT_FIELDS = """
    p.id AS product_id, p.name AS product_name, p.category, p.subCategory AS subcategory,
    p.details, p.description, p.specs, p.sale_unit, p.content_quantity, p.content_unit
"""


# Catalog bookkeeping the matcher doesn't need. Leaving it out keeps the matcher's
# request under the AI providers' tokens-per-minute limits.
BOOKKEEPING_SPECS = ("source_url", "source_price", "catalog_origin", "price_basis")


def candidate_from_row(row):
    """Prepare a candidate for the matcher: convert Decimals and leave out empty or bookkeeping fields."""
    product = product_specs.product_from_row(row)
    if product["content_quantity"] is not None:
        product["content_quantity"] = float(product["content_quantity"])
    specs = {key: value for key, value in product["specs"].items() if key not in BOOKKEEPING_SPECS}
    # source_title is usually the same text as buying_specs (it often holds vehicle fitment).
    if specs.get("source_title") == specs.get("buying_specs"):
        specs.pop("source_title", None)
    product["specs"] = specs
    return {key: value for key, value in product.items() if value not in (None, "", {})}


def get_machinery_catalog():
    with database_cursor() as cursor:
        cursor.execute("SELECT " + PLANNER_PRODUCT_FIELDS
                       + " FROM Product p WHERE p.isActive = 1 AND p.category = %s ORDER BY p.id",
                       ("heavy-machinery",))
        return [candidate_from_row(row) for row in cursor.fetchall()]


SEARCH_DEPTH = 60
CANDIDATES_PER_MATERIAL = 10
RRF_OFFSET = 20


def search_ids_by_text(cursor, query, automotive):
    """Rank active materials by the existing MySQL FULLTEXT index."""
    cursor.execute("""
        SELECT id AS product_id, MATCH(search_text) AGAINST (%s) AS relevance
        FROM Product
        WHERE isActive = 1 AND category <> 'heavy-machinery'
            AND (%s IS NULL OR (category = 'automotive') = %s)
            AND MATCH(search_text) AGAINST (%s)
        ORDER BY relevance DESC, id
        LIMIT %s
    """, (query, automotive, automotive, query, SEARCH_DEPTH))
    return [row["product_id"] for row in cursor.fetchall()]


def combine_rankings(text_ids, vector_ids):
    """Combine rankings without comparing MySQL scores to vector similarities."""
    scores = {}
    for ranking in (text_ids, vector_ids):
        for rank, product_id in enumerate(ranking, start=1):
            scores[product_id] = scores.get(product_id, 0) + 1 / (RRF_OFFSET + rank)
    # Equal scores preserve input order, starting with the FULLTEXT list.
    return sorted(scores, key=scores.get, reverse=True)


def load_candidates(cursor, product_ids, automotive):
    """Load active material candidates by ID, using the caller's cursor."""
    if not product_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(product_ids))
    sql = f"""SELECT {PLANNER_PRODUCT_FIELDS} FROM Product p
        WHERE p.isActive = 1 AND p.category <> 'heavy-machinery'
            AND (%s IS NULL OR (p.category = 'automotive') = %s)
            AND p.id IN ({placeholders})
    """
    cursor.execute(sql, [automotive, automotive, *product_ids])
    return {row["product_id"]: row for row in cursor.fetchall()}


def material_query(material):
    """Search context: name, specification and a stated purchase unit."""
    query = material["material_name"] + ". " + material["specification"]
    # Units help distinguish products like bagged mix and ready-mix, without filtering out
    # other sale units that could be converted.
    unit = normalize_unit(material.get("unit") or "")
    if unit in product_specs.PACKAGE_UNITS or unit in {"gallon", "quart", "lb", "cu_yd", "sq_ft"}:
        query += ". " + unit.replace("_", " ")
    return query


def find_candidates(cursor, ranked_ids, automotive=None):
    """Keep the first ten active products in fused rank order. The matcher picks among them."""
    rows = load_candidates(cursor, ranked_ids, automotive)
    candidates = []
    for product_id in ranked_ids:
        if product_id in rows:
            candidates.append(candidate_from_row(rows[product_id]))
        if len(candidates) == CANDIDATES_PER_MATERIAL:
            break
    return candidates


def get_material_candidates(materials):
    """Build a shortlist of candidates for each material.

    Run vector searches before opening the shared SQL connection, since they use the CPU.
    Reusing one connection keeps large plans faster.
    """
    if not materials:
        return []
    queries = [material_query(material) for material in materials]
    vector_rankings = vector_search.search_product_ids(queries, SEARCH_DEPTH)

    groups = []
    with database_cursor() as cursor:
        cursor.execute("SELECT DISTINCT category FROM Product WHERE isActive = 1")
        categories = {row["category"] for row in cursor.fetchall()}
        for index, material in enumerate(materials):
            # Building categories overlap, but vehicle parts are a separate catalog domain.
            category = material.get("category")
            automotive = category == "automotive" if category in categories else None
            text_ids = search_ids_by_text(cursor, product_specs.normalize_search(queries[index]), automotive)
            ranking = combine_rankings(text_ids, vector_rankings[index])
            candidates = find_candidates(cursor, ranking, automotive)
            groups.append({"material_index": index, "candidates": candidates})
    return groups


def get_products_by_ids(product_ids):
    """Store details for showing and buying products, by ID (active products only)."""
    product_ids = sorted(set(product_ids))
    if not product_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(product_ids))
    sql = f"""
        SELECT p.id AS product_id, p.name AS product_name, p.sale_unit AS unit, p.category,
               p.price AS unit_price, p.stockQty AS available_quantity,
               p.content_quantity, p.content_unit, p.specs, p.details, p.description
        FROM Product p
        WHERE p.isActive = 1 AND p.id IN ({placeholders})
    """
    with database_cursor() as cursor:
        cursor.execute(sql, product_ids)
        rows = cursor.fetchall()
    products = {}
    for row in rows:
        products[row["product_id"]] = product_specs.product_from_row(row)
    return products
