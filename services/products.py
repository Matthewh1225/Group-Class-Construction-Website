"Product catalog services. Searching and listing work; the other functions are placeholders."
import logging

from mysql.connector import Error

from utils.database import database_cursor

logger = logging.getLogger(__name__)

PAGE_SIZE = 12


def search_products(search=None, category_url_name=None, page=1):
    "Return (products, has_next_page) for one page of active products, sorted by name, with price and stock."
    # A product's manufacturer comes from the Manufacturer_products link table
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
    # What the user typed goes in the values list, never into the SQL text itself.
    values = []

    if search:
        pattern = "%" + search + "%"
        sql = sql + " AND (p.name LIKE %s OR p.keywords LIKE %s OR p.sku LIKE %s OR p.details LIKE %s)"
        values.extend([pattern, pattern, pattern, pattern])

    if category_url_name:
        sql = sql + " AND p.category = %s"
        values.append(category_url_name)

    # Ask for one more product than fits on the page: if it comes back, there is a next page.
    sql = sql + " ORDER BY p.name LIMIT %s OFFSET %s"
    values.append(PAGE_SIZE + 1)
    values.append((page - 1) * PAGE_SIZE)

    with database_cursor() as cursor:
        cursor.execute(sql, values)
        products = cursor.fetchall()

    has_next = len(products) > PAGE_SIZE
    return products[:PAGE_SIZE], has_next


def get_planner_catalog():
    "Return [{product_id, product_name, unit}] for every active product; the AI planner may only pick these IDs."

    sql = """
        SELECT p.Id AS product_id, p.name AS product_name, p.unit
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
    "Return {product_id: product} with the name, unit, price and stock of each active product in the list."
    # Used by the plan pages, so names, prices and stock always come from the database.
    # Returns {} when the list is empty or the catalog cannot be read.
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
    "Return active categories, each with its list of subcategories."
    pass

def get_category_by_url_name(url_name):
    "Return the category whose icon_key matches a page url_name such as 'hvac', or None."
    pass

def get_product_stock(product_id):
    "Return price, stock_quantity, reserved_quantity and the amount still available to buy."
    pass

def get_product_details(product_id):
    "Return product specifications, suppliers, and image metadata."
    pass

def create_product(product_data):
    "Create a catalog product after an administrator is authorized."
    pass

def update_product(product_id, product_data):
    "Update catalog details after an administrator is authorized."
    pass

def archive_product(product_id):
    "Deactivate a product while retaining order history."
    pass
