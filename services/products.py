"Product catalog services. Searching and listing work; the other functions are placeholders."
# Tables: categories, products, product_inventory, manufacturers, product_suppliers.

from utils.database import database_cursor

PAGE_SIZE = 12


def search_products(search=None, category_url_name=None, page=1):
    "Return (products, has_next_page) for one page of active products, sorted by name, with price and stock."
    sql = """
        SELECT p.product_id, p.product_name, p.specification, p.sku, p.unit,
               p.pack_quantity, p.purchase_increment,
               c.category_name, m.manufacturer_name,
               i.unit_price, i.currency, i.is_available,
               i.stock_quantity - i.reserved_quantity AS available_quantity
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN manufacturers m ON m.manufacturer_id = p.manufacturer_id
        LEFT JOIN product_inventory i ON i.product_id = p.product_id
        WHERE p.is_active = 1 AND c.is_active = 1
    """
    # What the user typed goes in the values list, never into the SQL text itself.
    values = []

    if search:
        # "%" before and after means "contains"
        pattern = "%" + search + "%"
        sql = sql + " AND (p.product_name LIKE %s OR p.keywords LIKE %s OR p.sku LIKE %s OR p.specification LIKE %s)"
        values.extend([pattern, pattern, pattern, pattern])

    if category_url_name:
        sql = sql + " AND c.icon_key = %s"
        values.append(category_url_name)

    # Ask for one more product than fits on the page: if it comes back, there is a next page.
    sql = sql + " ORDER BY p.product_name LIMIT %s OFFSET %s"
    values.append(PAGE_SIZE + 1)
    values.append((page - 1) * PAGE_SIZE)

    with database_cursor() as cursor:
        cursor.execute(sql, values)
        products = cursor.fetchall()

    has_next = len(products) > PAGE_SIZE
    return products[:PAGE_SIZE], has_next


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
