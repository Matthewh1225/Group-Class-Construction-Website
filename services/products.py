import re

from utils.database import database_cursor

PAGE_SIZE = 12


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
    "Return (products, total_pages) using the same filters for both."
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
        pattern = "%" + search + "%"
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

# Only the Matcher receives inventory. Search every active product, not the first 400.
def get_planner_catalog(machinery=False, materials=None):

    sql = """
        SELECT p.id AS product_id, p.name AS product_name, p.unit, p.details AS specification,
               p.itemQty AS pack_quantity, p.keywords, p.category, p.subCategory AS subcategory
        FROM Product p
        WHERE p.isActive = 1
    """
    if machinery:
        sql += " AND p.category = %s"
    else:
        sql += " AND p.category <> %s"
    sql += " ORDER BY p.id"
    with database_cursor() as cursor:
        cursor.execute(sql, ("heavy-machinery",))
        products = cursor.fetchall()
    if materials is not None and not machinery:
        selected = {}
        for material in materials:
            name_words = catalog_words(material["material_name"])
            spec_words = catalog_words(material["specification"])
            ranked = []
            for product in products:
                product_words = catalog_words(product["product_name"])
                search_words = catalog_words((product["keywords"] or "") + " " + product["subcategory"])
                name_matches = len(name_words & product_words)
                keyword_matches = len(name_words & search_words)
                if not name_matches and not keyword_matches:
                    continue
                spec_matches = len(spec_words & catalog_words(product["specification"] or ""))
                score = 5 * name_matches + keyword_matches + 2 * spec_matches
                ranked.append((score, product))
            ranked.sort(key=lambda entry: (-entry[0], entry[1]["product_id"]))
            for score, product in ranked[:12]:
                selected[product["product_id"]] = product
        products = list(selected.values())
    for product in products:
        del product["keywords"]
    return products


def catalog_words(text):
    words = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in {"a", "an", "the", "for", "of", "and", "with", "in", "x", "ft", "required"}:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return words


def get_products_by_ids(product_ids):
    # Read current store data instead of saving prices in the AI plan.
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
