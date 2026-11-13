from services import vector_search
from utils.database import database_cursor

PAGE_SIZE = 12
MIN_SIMILARITY = 0.35

CATALOG_SYNONYMS = {
    "gypsum board": "drywall",
    "wallboard": "drywall gypsum board",
    "drawer runners": "drawer slides",
    "cupboard": "cabinet",
    "abrasive paper": "sandpaper sanding sheets",
    "carcass backing": "cabinet backs plywood",
}

UNIT_ALIASES = {"linear_ft": "ft", "linear feet": "ft", "each": "piece", "feet": "ft", "foot": "ft", "inches": "in", "inch": "in", "meters": "m", "metres": "m", "square feet": "sq_ft", "sq ft": "sq_ft",
                "square meters": "sq_m", "sq m": "sq_m", "layers": "count", "layer": "count", "coats": "count", "coat": "count", "gallons": "gallon", "sheets": "sheet", "pieces": "piece",
                "rolls": "roll", "screws": "screw", "boxes": "box", "bags": "bag"}


def normalize_unit(unit):
    text = unit.strip().lower()
    return UNIT_ALIASES.get(text, text)


def get_all_manufacturers():
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT m.id AS manufacturer_id, m.name,
                   EXISTS (SELECT 1 FROM Manufacturer_products mp
                           JOIN Product p ON p.id = mp.productId
                           WHERE mp.manid = m.id AND p.isActive = 1
                             AND p.category = 'heavy-machinery') AS has_machinery
            FROM Manufacturer m
            ORDER BY m.name
        """)
        return cursor.fetchall()


def get_manufacturer(manufacturer_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT id AS manufacturer_id, name FROM Manufacturer WHERE id = %s",
                       (manufacturer_id,))
        return cursor.fetchone()


def search_products(search=None, category_url_name=None, page=1, manufacturer_id=None):
    # Return products and page count with the same filters.
    sql = """
        SELECT p.id AS product_id, p.name AS product_name, p.details AS specification,
               p.sku, p.unit, p.category,
               p.itemQty AS pack_quantity,
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
        # All words must occur
        for word in search.split():
            pattern = "%" + word + "%"
            filters += " AND (p.name LIKE %s OR p.keywords LIKE %s OR p.sku LIKE %s OR p.details LIKE %s)"
            values.extend([pattern, pattern, pattern, pattern])

    if category_url_name:
        filters += " AND p.category = %s"
        values.append(category_url_name)
    else:
        filters += " AND p.category <> %s"
        values.append("heavy-machinery")

    with database_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total" + filters, values)
        total = cursor.fetchone()["total"]
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        cursor.execute(sql + filters + " ORDER BY p.name LIMIT %s OFFSET %s",
                       values + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
        products = cursor.fetchall()

    return products, total_pages

def get_catalog_classifications():
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT category, subCategory AS subcategory
            FROM Product ORDER BY category, subCategory
        """)
        rows = cursor.fetchall()
    classifications = {}
    for row in rows:
        classifications.setdefault(row["category"], []).append(row["subcategory"])
    return classifications


# Only the Matcher receives products.
PLANNER_PRODUCT_FIELDS = """
    p.id AS product_id, p.name AS product_name, p.unit, p.details AS specification,
    p.itemQty AS pack_quantity, p.category, p.subCategory AS subcategory,
    p.dimensions, p.materials AS material_type
"""


def get_machinery_catalog():
    with database_cursor() as cursor:
        cursor.execute("SELECT " + PLANNER_PRODUCT_FIELDS
                       + " FROM Product p WHERE p.isActive = 1 AND p.category = %s ORDER BY p.id",
                       ("heavy-machinery",))
        return cursor.fetchall()


def search_products_by_meaning(query, limit=10, skip_category=None):
    # Return None if vector search isn't ready.
    ranked = vector_search.search_product_ids(query, limit * 3)
    if ranked is None:
        return None
    if not ranked:
        return []

    ids = []
    for product_id, score in ranked:
        ids.append(product_id)

    placeholders = ", ".join(["%s"] * len(ids))
    sql = ("SELECT " + PLANNER_PRODUCT_FIELDS
           + " FROM Product p WHERE p.isActive = 1 AND p.id IN (" + placeholders + ")")
    values = list(ids)
    if skip_category is not None:
        sql += " AND p.category <> %s"
        values.append(skip_category)
    with database_cursor() as cursor:
        cursor.execute(sql, values)
        rows = cursor.fetchall()

    # Put the database rows back in search order.
    rows_by_id = {}
    for row in rows:
        rows_by_id[row["product_id"]] = row
    products = []
    for product_id, score in ranked:
        if product_id in rows_by_id:
            product = rows_by_id[product_id]
            product["similarity"] = round(score, 3)
            products.append(product)
        if len(products) == limit:
            break
    return products


def get_material_candidates(materials):
    if not materials:
        return []

    # Use keyword search if vector search isn't ready.
    if not vector_search.load_vector_search():
        return get_material_candidates_by_keywords(materials)

    groups = []
    for index, material in enumerate(materials):
        query = material["material_name"] + ". " + material["specification"]
        products = search_products_by_meaning(query, limit=10, skip_category="heavy-machinery")
        candidates = []
        for product in products:
            # Skip products with low similarity.
            if product["similarity"] < MIN_SIMILARITY:
                continue
            # Leave the search score out of the Matcher input.
            del product["similarity"]
            candidates.append(product)
        groups.append({"material_index": index, "candidates": candidates})
    return groups


def get_material_candidates_by_keywords(materials):
    # Use MySQL keyword search when vector search isn't ready.
    if not materials:
        return []

    classifications = get_catalog_classifications()
    match = "MATCH(p.name, p.details, p.keywords, p.dimensions, p.materials)"
    groups = []
    with database_cursor() as cursor:
        for index, material in enumerate(materials):
            name = material["material_name"]
            search_name = name
            for phrase, synonym in CATALOG_SYNONYMS.items():
                if phrase in name.lower():
                    search_name += " " + synonym
            search_text = search_name + " " + material["specification"]

            category = material.get("category")
            subcategory = material.get("subcategory")
            scopes = []
            if category in classifications:
                if subcategory in classifications[category]:
                    scopes.append((category, subcategory))
                scopes.append((category, None))
            scopes.append((None, None))

            candidates = []
            seen = set()
            for category, subcategory in scopes:
                sql = ("SELECT " + PLANNER_PRODUCT_FIELDS + ", " + match
                       + " AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance"
                       + " FROM Product p WHERE p.isActive = 1 AND p.category <> %s"
                       + " AND " + match + " AGAINST (%s IN NATURAL LANGUAGE MODE) > 0")
                # Require a name match, not just matching details.
                values = [search_text, "heavy-machinery", search_name]
                if category is not None:
                    sql += " AND p.category = %s"
                    values.append(category)
                if subcategory is not None:
                    sql += " AND p.subCategory = %s"
                    values.append(subcategory)
                sql += " HAVING relevance > 0 ORDER BY relevance DESC, p.id LIMIT 10"
                cursor.execute(sql, values)
                for product in cursor.fetchall():
                    if product["product_id"] not in seen:
                        seen.add(product["product_id"])
                        del product["relevance"]
                        candidates.append(product)
                    if len(candidates) == 10:
                        break
                if len(candidates) == 10:
                    break
            groups.append({"material_index": index, "candidates": candidates})
    return groups


def get_products_by_ids(product_ids):
    # Read current prices and stock from the store.
    product_ids = sorted(set(product_ids))
    if not product_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(product_ids))
    sql = f"""
        SELECT p.id AS product_id, p.name AS product_name, p.unit, p.category,
               p.price AS unit_price, p.stockQty AS available_quantity
        FROM Product p
        WHERE p.isActive = 1 AND p.id IN ({placeholders})
    """
    with database_cursor() as cursor:
        cursor.execute(sql, product_ids)
        rows = cursor.fetchall()
    products = {}
    for row in rows:
        products[row["product_id"]] = row
    return products
