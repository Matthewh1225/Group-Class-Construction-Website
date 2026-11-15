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
    """Add a product to the user's cart and return the product name."""
    # The form sends quantity as text, and the planner sends a Decimal
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Enter a whole number for the quantity.")
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    with database_cursor() as cursor:
        cursor.execute(
            "SELECT name, stockQty FROM Product WHERE id = %s AND isActive = 1",
            (product_id,),
        )
        product = cursor.fetchone()
        if product is None:
            raise ValueError("That product does not exist.")

        # What the user already has in the cart counts toward the stock limit
        cursor.execute(
            "SELECT itemQty FROM Cart_item WHERE userId = %s AND productId = %s",
            (user_id, product_id),
        )
        existing = cursor.fetchone()
        combined = quantity
        if existing:
            combined += existing["itemQty"]

        if combined > product["stockQty"]:
            raise ValueError("Not enough stock of " + product["name"] + " for that quantity.")

        cursor.execute(
            """
            INSERT INTO Cart_item (userId, productId, itemQty)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE itemQty = %s
            """,
            (user_id, product_id, quantity, combined),
        )

    return product["name"]


def change_quantity(user_id, product_id, quantity):
    # TODO: Check quantity and stock, then update the cart item.
    pass


def remove_item(user_id, product_id):
    # TODO: Remove the product from this user's cart.
    pass


def add_materials_to_cart(user_id, materials):
    """Add planner materials to the cart.

    Returns {"added": [product names], "skipped": count, "failed": [messages]}.
    """
    added = []
    skipped = 0
    failed = []

    for material in materials:
        # Skip materials we do not sell, cannot match by unit, or have no stock for
        if not material.get("can_add"):
            skipped += 1
            continue
        try:
            name = add_item(user_id, material["product"]["product_id"], material["buy_quantity"])
        except ValueError as error:
            failed.append(str(error).rstrip("."))
        else:
            added.append(name)

    return {"added": added, "skipped": skipped, "failed": failed}


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
