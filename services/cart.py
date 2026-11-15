import hashlib
import json

from services.crews import estimate_crew_cost, parse_crew
from utils.database import database_cursor


def get_cart(user_id):
    """Return the user's cart items with current prices (in cents) and line totals."""
    sql = """
        SELECT p.id AS product_id, p.name AS name, p.unit AS unit,
               ci.itemQty AS quantity, p.stockQty AS stock,
               ROUND(p.price * 100) AS unit_price_cents,
               ROUND(p.price * 100) * ci.itemQty AS total_cents
        FROM Cart_item ci
        JOIN Product p ON p.id = ci.productId
        WHERE ci.userId = %s
        ORDER BY p.name
    """
    with database_cursor() as cursor:
        cursor.execute(sql, (user_id,))
        items = cursor.fetchall()

    for item in items:
        item["unit_price_cents"] = int(item["unit_price_cents"])
        item["total_cents"] = int(item["total_cents"])
        if item["quantity"] > item["stock"]:
            item["error"] = "Only " + str(item["stock"]) + " in stock. Lower the quantity."
    return items


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
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Enter a whole number for the quantity.")
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    with database_cursor() as cursor:
        cursor.execute("SELECT stockQty FROM Product WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if product is None:
            raise ValueError("That product does not exist.")
        if quantity > product["stockQty"]:
            raise ValueError("Not enough stock for that quantity.")
        cursor.execute(
            "UPDATE Cart_item SET itemQty = %s WHERE userId = %s AND productId = %s",
            (quantity, user_id, product_id),
        )


def remove_item(user_id, product_id):
    with database_cursor() as cursor:
        cursor.execute(
            "DELETE FROM Cart_item WHERE userId = %s AND productId = %s",
            (user_id, product_id),
        )


def add_preorder_item(user_id, preorder):
    """Put a pre-order item in the cart. Adding the same item again adds to its quantity."""
    with database_cursor() as cursor:
        # Same name, unit and product already in the cart? Then just add to it
        cursor.execute(
            """
            SELECT id FROM Preorder_item
            WHERE userId = %s AND orderId IS NULL AND name = %s AND unit = %s
              AND productId <=> %s
            """,
            (user_id, preorder["name"], preorder["unit"], preorder["product_id"]),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE Preorder_item SET quantity = quantity + %s, unitPrice = %s WHERE id = %s",
                (preorder["quantity"], preorder["unit_price"], existing["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO Preorder_item (userId, productId, name, unit, quantity, unitPrice)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, preorder["product_id"], preorder["name"], preorder["unit"],
                 preorder["quantity"], preorder["unit_price"]),
            )
    return preorder["name"]


def tidy_quantity(quantity):
    """Show 3.00 as 3 and 2.50 as 2.5."""
    if quantity == int(quantity):
        return int(quantity)
    return quantity.normalize()


def get_cart_preorders(user_id):
    """Return the pre-order items in the user's cart (not yet ordered)."""
    with database_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, productId AS product_id, name, unit, quantity, unitPrice AS unit_price
            FROM Preorder_item
            WHERE userId = %s AND orderId IS NULL
            ORDER BY name
            """,
            (user_id,),
        )
        items = cursor.fetchall()

    for item in items:
        item["preorder"] = True
        if item["unit_price"] is None:
            item["unit_price_cents"] = None
            item["total_cents"] = None
        else:
            item["unit_price_cents"] = int(round(item["unit_price"] * 100))
            item["total_cents"] = int(round(item["unit_price"] * item["quantity"] * 100))
        item["quantity"] = tidy_quantity(item["quantity"])
    return items


def remove_preorder(user_id, preorder_id):
    with database_cursor() as cursor:
        cursor.execute(
            "DELETE FROM Preorder_item WHERE id = %s AND userId = %s AND orderId IS NULL",
            (preorder_id, user_id),
        )


def add_materials_to_cart(user_id, materials):
    """Add planner materials to the cart. Anything we can't sell right now becomes a pre-order.

    Returns {"added": [names], "preordered": [names], "failed": [messages]}.
    """
    added = []
    preordered = []
    failed = []

    for material in materials:
        try:
            if material["can_add"]:
                added.append(add_item(user_id, material["product"]["product_id"], material["buy_quantity"]))
            else:
                preordered.append(add_preorder_item(user_id, material["preorder"]))
        except ValueError as error:
            failed.append(str(error).rstrip("."))

    return {"added": added, "preordered": preordered, "failed": failed}


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
