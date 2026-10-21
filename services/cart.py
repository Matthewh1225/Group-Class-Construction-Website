"""Saved cart items and current product details."""

from decimal import Decimal, InvalidOperation

from utils.database import database_cursor

MAX_QUANTITY = 2_147_483_647  # Largest value the SQL INT quantity column can store.
CENTS_PER_DOLLAR = 100


def read_quantity(text):
    """Cart quantities must be whole numbers."""
    try:
        quantity = Decimal(str(text))
    except InvalidOperation:
        raise ValueError("Enter a positive whole-number quantity.")
    if not quantity.is_finite() or quantity < 1 or quantity > MAX_QUANTITY:
        raise ValueError(f"Enter a whole-number quantity between 1 and {MAX_QUANTITY:,}.")
    whole_quantity = int(quantity)
    if quantity != whole_quantity:
        raise ValueError("Enter a positive whole-number quantity.")
    return whole_quantity


def get_cart_product(cursor, product_id):
    # Keep this product locked until the cart change is saved.
    cursor.execute("""
        SELECT name, unit, price AS unit_price, itemQty AS available_quantity,
               isActive AS is_active, purchaseIncrement AS purchase_increment
        FROM Product WHERE Id = %s FOR UPDATE
    """, (product_id,))
    return cursor.fetchone()


def check_cart_product(product, quantity):
    if product is None or not product["is_active"]:
        raise ValueError("This product is no longer available.")
    price = product["unit_price"]
    if price is None or price < 0:
        raise ValueError("This product does not have a valid price.")
    increment = product["purchase_increment"]
    if increment <= 0 or quantity % increment != 0:
        raise ValueError(f"Order this product in multiples of {increment} {product['unit']}.")
    stock = product["available_quantity"]
    if stock is None:
        stock = 0
    if quantity > stock:
        raise ValueError(f"Only {stock} {product['unit']} are currently available.")


def get_cart_items(user_id):
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT c.product_id, c.quantity, p.name, p.unit, p.price AS unit_price,
                   p.itemQty AS available_quantity, p.isActive AS is_active,
                   p.purchaseIncrement AS purchase_increment
            FROM Cart_item c
            JOIN Product p ON p.Id = c.product_id
            WHERE c.user_id = %s
            ORDER BY p.name, p.Id
        """, (user_id,))
        items = cursor.fetchall()
    for item in items:
        item["error"] = ""
        try:
            check_cart_product(item, item["quantity"])
        except ValueError as error:
            item["error"] = str(error)
        price = item["unit_price"]
        item["unit_price_cents"] = None
        item["total_cents"] = None
        if price is not None:
            item["unit_price_cents"] = int(price * CENTS_PER_DOLLAR)
            item["total_cents"] = item["unit_price_cents"] * item["quantity"]
    return items


def add_cart_item(user_id, product_id, quantity):
    quantity = read_quantity(quantity)
    with database_cursor() as cursor:
        product = get_cart_product(cursor, product_id)
        cursor.execute("SELECT quantity FROM Cart_item WHERE user_id = %s AND product_id = %s FOR UPDATE",
                       (user_id, product_id))
        existing = cursor.fetchone()
        if existing:
            quantity += existing["quantity"]
        check_cart_product(product, quantity)
        if existing:
            cursor.execute("UPDATE Cart_item SET quantity = %s WHERE user_id = %s AND product_id = %s",
                           (quantity, user_id, product_id))
        else:
            cursor.execute("INSERT INTO Cart_item (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                           (user_id, product_id, quantity))
    return product["name"]


def update_cart_quantity(user_id, product_id, quantity):
    quantity = read_quantity(quantity)
    with database_cursor() as cursor:
        product = get_cart_product(cursor, product_id)
        check_cart_product(product, quantity)
        cursor.execute("SELECT quantity FROM Cart_item WHERE user_id = %s AND product_id = %s FOR UPDATE",
                       (user_id, product_id))
        if cursor.fetchone() is None:
            raise ValueError("This product is not in your cart.")
        cursor.execute("UPDATE Cart_item SET quantity = %s WHERE user_id = %s AND product_id = %s",
                       (quantity, user_id, product_id))


def remove_cart_item(user_id, product_id):
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM Cart_item WHERE user_id = %s AND product_id = %s",
                       (user_id, product_id))
        return cursor.rowcount > 0


def calculate_cart_subtotal(user_id):
    items = get_cart_items(user_id)
    subtotal = Decimal("0.00")
    for item in items:
        if item["error"]:
            raise ValueError(item["error"])
        subtotal += Decimal(item["total_cents"]) / CENTS_PER_DOLLAR
    return subtotal


def add_material_list_to_cart(user_id, material_list_id):
    "Use the user's materials and round amounts to store pack sizes."
    pass


def clear_cart(user_id):
    "Checkout clears the cart as part of saving the order."
    pass
