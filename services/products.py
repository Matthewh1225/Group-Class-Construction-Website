"Catalog searches work; the remaining helpers are not written yet."
import logging

from mysql.connector import Error

from utils.database import database_cursor

logger = logging.getLogger(__name__)

PAGE_SIZE = 12


def get_manufacturers():
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT m.Id AS manufacturer_id, m.name,
                   EXISTS (SELECT 1 FROM Manufacturer_products mp
                           JOIN Product p ON p.Id = mp.productId
                           WHERE mp.manId = m.Id AND p.isActive = 1
                             AND p.category = 'heavy-machinery') AS has_machinery
            FROM Manufacturer m
            ORDER BY m.name
        """)
        return cursor.fetchall()


def get_manufacturer(manufacturer_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT Id AS manufacturer_id, name FROM Manufacturer WHERE Id = %s",
                       (manufacturer_id,))
        return cursor.fetchone()


def search_products(search=None, category_url_name=None, page=1, manufacturer_id=None):
    "Return (products, has_next_page), sorted by name."
    sql = """
        SELECT p.Id AS product_id, p.name AS product_name, p.details AS specification,
               p.sku, p.unit, p.category,
               p.packQuantity AS pack_quantity, p.purchaseIncrement AS purchase_increment,
               p.price AS unit_price, p.itemQty AS available_quantity,
               (SELECT m.name FROM Manufacturer_products mp
                JOIN Manufacturer m ON m.Id = mp.manId
                WHERE mp.productId = p.Id
                ORDER BY m.name LIMIT 1) AS manufacturer_name
        FROM Product p
        WHERE p.isActive = 1
    """
    # Keep user input in SQL parameters.
    values = []

    if manufacturer_id is not None:
        sql += " AND EXISTS (SELECT 1 FROM Manufacturer_products mp WHERE mp.productId = p.Id AND mp.manId = %s)"
        values.append(manufacturer_id)

    if search:
        pattern = "%" + search + "%"
        sql = sql + " AND (p.name LIKE %s OR p.keywords LIKE %s OR p.sku LIKE %s OR p.details LIKE %s)"
        values.extend([pattern, pattern, pattern, pattern])

    if category_url_name:
        sql = sql + " AND p.category = %s"
        values.append(category_url_name)
    else:
        sql = sql + " AND (p.category IS NULL OR p.category <> %s)"
        values.append("heavy-machinery")

    # One extra product tells us whether another page exists.
    sql = sql + " ORDER BY p.name LIMIT %s OFFSET %s"
    values.append(PAGE_SIZE + 1)
    values.append((page - 1) * PAGE_SIZE)

    with database_cursor() as cursor:
        cursor.execute(sql, values)
        products = cursor.fetchall()

    has_next = len(products) > PAGE_SIZE
    return products[:PAGE_SIZE], has_next


def get_planner_catalog():
    "Return active products and specifications for the planner."

    sql = """
        SELECT p.Id AS product_id, p.name AS product_name, p.unit,
               p.details AS specification
        FROM Product p
        WHERE p.isActive = 1
        ORDER BY p.Id
        LIMIT 500
    """
    try:
        with database_cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    except Error:
        logger.exception("The product catalog could not be read for the planner.")
        return []


def get_products_by_ids(product_ids):
    "Return current product details by ID, or {} if unavailable."
    # Read current store data instead of saving prices in the AI plan.
    product_ids = sorted(set(product_ids))
    if not product_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(product_ids))
    sql = f"""
        SELECT p.Id AS product_id, p.name AS product_name, p.unit,
               p.purchaseIncrement AS purchase_increment,
               p.price AS unit_price, p.itemQty AS available_quantity
        FROM Product p
        WHERE p.isActive = 1 AND p.Id IN ({placeholders})
    """
    try:
        with database_cursor() as cursor:
            cursor.execute(sql, product_ids)
            rows = cursor.fetchall()
    except Error:
        logger.exception("Product details could not be read for a plan.")
        return {}
    products = {}
    for row in rows:
        products[row["product_id"]] = row
    return products


def get_categories():
    "Include each category's subcategories."
    pass

def get_category_by_url_name(url_name):
    "Find a category by its URL name, or return None."
    pass

def get_product_stock(product_id):
    "Include price, stock, reserved amounts and available amounts."
    pass

def get_product_details(product_id):
    "Include specifications, suppliers and image details."
    pass

def create_product(product_data):
    "Check admin access before creating a product."
    pass

def update_product(product_id, product_data):
    "Check admin access before changing a product."
    pass

def archive_product(product_id):
    "Hide the product but keep its order history."
    pass
