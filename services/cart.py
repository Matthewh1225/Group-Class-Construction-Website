import hashlib
import json

from services.crews import estimate_crew_cost, parse_crew
from utils.database import database_cursor


def get_cart(user_id):
    # TODO: Get cart items with current prices and totals.
    sql = """
        SELECT p.id as product_Id, p.name as name, p.unit_price_cents as price, oi.itemQty as qty, oi.itemQty * p.unti_price_cents as total_cents
        FROM cart c
        JOIN order_item oi ON oi.orderId = c.id
        JOIN product p ON p.id = oi.productId
        WHERE c.userId = %s AND c.orderStatus = 'open'
        ORDER BY p.name
    """
    with database_cursor() as cursor:
            cursor.execute(sql, (user_id,))
            items =  cursor.fetchall()
    return {items}


def add_item(user_id, product_id, quantity):
    # TODO: Add the product and check the combined quantity.
    with database_cursor() as cursor:

        # Make sure the product is in stock
        cursor.execute("SELECT stockQuantity FROM product WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if product is None:
            raise ValueError("That product does not exist.")

        # Open cart or create one 
        cursor.execute(
            "SELECT id FROM cart WHERE userId = %s AND orderStatus = 'open' LIMIT 1",
            (user_id,),
        )
        cart = cursor.fetchone()
        if cart is None:
            cursor.execute(
                "INSERT INTO cart (dateCreated, totalCost, orderStatus, userId) "
                "VALUES (CURDATE(), 0, 'open', %s)",
                (user_id,),
            )
            cart_id = cursor.lastrowid
        else:
            cart_id = cart["id"]

        # Combined quantity = what's already in the cart + the new amount/ if qty exceeds stock raise error
        cursor.execute(
            "SELECT itemQty FROM order_item WHERE orderId = %s AND productId = %s",
            (cart_id, product_id),
        )
        existing = cursor.fetchone()
        combined = (existing["itemQty"] if existing else 0) + quantity

        if combined > product["stockQuantity"]:
            raise ValueError("Not enough stock for that quantity.")

        # Add the item, or update the quantity if it's already in the cart
        cursor.execute(
            """
            INSERT INTO order_item (orderId, productId, itemQty)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE itemQty = %s
            """,
            (cart_id, product_id, quantity, combined),
        )

    return combined
    


def change_quantity(user_id, product_id, quantity):
    # TODO: Check quantity and stock, then update the cart item.
    pass


def remove_item(user_id, product_id):
    # TODO: Remove the product from this user's cart.
    pass


def add_materials_to_cart(user_id, materials):
    # TODO: Add matched materials; report added, skipped, and failed items.
    pass


def add_crew(user_id, crew_json):
    crew = parse_crew(crew_json)
    crew_json = json.dumps(crew, sort_keys=True, allow_nan=False)
    crew_hash = hashlib.sha256(crew_json.encode()).hexdigest()
    with database_cursor() as cursor:
        cursor.execute(
            """INSERT INTO crew_cart (owner, crew, crew_hash) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
            (user_id, crew_json, crew_hash),
        )
    return crew["label"]


def get_cart_crews(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT id, crew FROM crew_cart WHERE owner = %s ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
    crews = []
    for row in rows:
        crew = json.loads(row["crew"])
        estimate = estimate_crew_cost(crew)
        crews.append({"id": row["id"], "estimate": estimate})
    return crews


def remove_crew(user_id, crew_id):
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM crew_cart WHERE id = %s AND owner = %s", (crew_id, user_id))
        return cursor.rowcount == 1
