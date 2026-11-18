import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext

from services.crews import estimate_crew_cost, parse_crew
from services.products import guess_unit_price
from utils.database import database_cursor


def get_cart(user_id, cursor=None):
    """Return the user's cart items with current prices (in cents) and line totals."""
    sql = """
        SELECT p.id AS product_id, p.name AS name, p.sale_unit AS unit, p.isActive,
               ci.itemQty AS quantity, p.stockQty AS stock,
               ci.itemQty + COALESCE((SELECT SUM(pre.quantity) FROM Preorder_item pre
                   WHERE pre.userId = ci.userId AND pre.productId = p.id AND pre.orderId IS NULL
                     AND pre.unit = p.sale_unit AND pre.quantity = FLOOR(pre.quantity)), 0) AS requested_quantity,
               p.price AS unit_price
        FROM Cart_item ci
        JOIN Product p ON p.id = ci.productId
        WHERE ci.userId = %s
        ORDER BY p.name
    """
    if cursor is None:
        with database_cursor(lock_name=f"cart_{user_id}") as cursor:
            reconcile_stock(cursor, user_id)
            return get_cart(user_id, cursor)
    cursor.execute(sql, (user_id,))
    items = cursor.fetchall()

    for item in items:
        with localcontext() as context:
            context.prec = 80
            item["unit_price_cents"] = int(item.pop("unit_price") * 100)
        item["quantity"] = int(item["quantity"])
        item["stock"] = int(item["stock"])
        item["requested_quantity"] = int(item["requested_quantity"])
        item["total_cents"] = item["unit_price_cents"] * item["quantity"]
        if not item["isActive"]:
            item["error"] = "This product is no longer available. Remove it from your cart."
    return items


def get_cart_contents(user_id):
    """Read both portions from the same stock snapshot."""
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        reconcile_stock(cursor, user_id)
        return get_cart(user_id, cursor), get_cart_preorders(user_id, cursor)


def count_cart_lines(user_id):
    """Number of lines in the cart (products, preorders and crews), for the nav badge."""
    with database_cursor() as cursor:
        cursor.execute("""
            SELECT (SELECT COUNT(*) FROM Cart_item WHERE userId = %s)
                 + (SELECT COUNT(*) FROM Preorder_item WHERE userId = %s AND orderId IS NULL)
                 + (SELECT COUNT(*) FROM crew_cart WHERE owner = %s) AS total
        """, (user_id, user_id, user_id))
        return int(cursor.fetchone()["total"])


def whole_quantity(value):
    """Accept positive whole sale units without truncating a decimal request."""
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a whole number for the quantity.")
    if not quantity.is_finite() or quantity != quantity.to_integral_value() or quantity < 1:
        raise ValueError("Enter a positive whole number for the quantity.")
    # Preorder_item.quantity is DECIMAL(12,2).
    if quantity > 9999999999:
        raise ValueError("Quantity is too large.")
    return int(quantity)


def reconcile_stock(cursor, user_id):
    """Split catalog requests using current stock while holding product row locks.

    The caller holds this user's cart lock. Catalog preorders use the product's
    ID and sale unit. Custom requests retain their separate quantities/prices.
    """
    # Resolve this cart's IDs first. OR-ed subqueries made MySQL scan and lock
    # the Product index, holding up other carts and catalog updates.
    cursor.execute("""
        SELECT productId FROM Cart_item WHERE userId = %s
        UNION
        SELECT productId FROM Preorder_item
        WHERE userId = %s AND orderId IS NULL AND productId IS NOT NULL
        ORDER BY productId
    """, (user_id, user_id))
    product_ids = [row["productId"] for row in cursor.fetchall()]
    if not product_ids:
        return
    placeholders = ", ".join(["%s"] * len(product_ids))
    cursor.execute(f"""
        SELECT id, name, sale_unit, price, stockQty, isActive FROM Product
        WHERE id IN ({placeholders}) ORDER BY id FOR UPDATE
    """, product_ids)
    products = cursor.fetchall()
    cursor.execute("SELECT productId, itemQty FROM Cart_item WHERE userId = %s FOR UPDATE", (user_id,))
    quantities = {row["productId"]: int(row["itemQty"]) for row in cursor.fetchall()}
    cursor.execute("""
        SELECT id, productId, name, unit, quantity, unitPrice FROM Preorder_item
        WHERE userId = %s AND orderId IS NULL ORDER BY id FOR UPDATE
    """, (user_id,))
    preorders = cursor.fetchall()
    for product in products:
        matches = [row for row in preorders if row["productId"] == product["id"]
                   and row["unit"] == product["sale_unit"]
                   and row["quantity"] == int(row["quantity"])]
        requested = quantities.get(product["id"], 0) + sum(int(row["quantity"]) for row in matches)
        if not requested:
            continue
        whole_quantity(requested)
        # Deactivated products stay visible for removal and cannot be ordered.
        if not product["isActive"]:
            continue
        available = min(requested, max(0, int(product["stockQty"])))
        remaining = requested - available
        if available != quantities.get(product["id"], 0):
            if available:
                cursor.execute("""
                    INSERT INTO Cart_item (userId, productId, itemQty) VALUES (%s,%s,%s)
                    ON DUPLICATE KEY UPDATE itemQty = %s
                """, (user_id, product["id"], available, available))
            else:
                cursor.execute("DELETE FROM Cart_item WHERE userId = %s AND productId = %s",
                               (user_id, product["id"]))
        if remaining:
            if matches:
                first = matches[0]
                if (first["quantity"] != remaining or first["unitPrice"] != product["price"]
                        or first["name"] != product["name"]):
                    cursor.execute("UPDATE Preorder_item SET quantity = %s, unitPrice = %s, name = %s WHERE id = %s",
                                   (remaining, product["price"], product["name"], first["id"]))
            else:
                cursor.execute("""
                    INSERT INTO Preorder_item (userId,productId,name,unit,quantity,unitPrice)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (user_id, product["id"], product["name"], product["sale_unit"], remaining, product["price"]))
        obsolete = matches
        if remaining:
            obsolete = matches[1:]
        for row in obsolete:
            cursor.execute("DELETE FROM Preorder_item WHERE id = %s", (row["id"],))


def add_catalog_quantity(cursor, user_id, product_id, quantity):
    cursor.execute("SELECT name FROM Product WHERE id = %s AND isActive = 1 FOR UPDATE", (product_id,))
    product = cursor.fetchone()
    if product is None:
        raise ValueError("That product does not exist.")
    cursor.execute("""
        INSERT INTO Cart_item (userId, productId, itemQty) VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE itemQty = itemQty + %s
    """, (user_id, product_id, quantity, quantity))
    reconcile_stock(cursor, user_id)
    return product["name"]


def add_item(user_id, product_id, quantity):
    """Add the full request, splitting available units and the preorder remainder."""
    quantity = whole_quantity(quantity)
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        return add_catalog_quantity(cursor, user_id, product_id, quantity)


def change_quantity(user_id, product_id, quantity):
    """Set the total requested quantity, including the catalog preorder remainder."""
    quantity = whole_quantity(quantity)
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute("SELECT name, sale_unit FROM Product WHERE id = %s AND isActive = 1 FOR UPDATE", (product_id,))
        product = cursor.fetchone()
        if product is None:
            raise ValueError("That product does not exist.")
        cursor.execute("""
            DELETE FROM Preorder_item WHERE userId = %s AND productId = %s
            AND orderId IS NULL AND unit = %s AND quantity = FLOOR(quantity)
        """, (user_id, product_id, product["sale_unit"]))
        cursor.execute("DELETE FROM Cart_item WHERE userId = %s AND productId = %s", (user_id, product_id))
        add_catalog_quantity(cursor, user_id, product_id, quantity)


def remove_item(user_id, product_id):
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute("""
            DELETE FROM Preorder_item WHERE userId = %s AND productId = %s AND orderId IS NULL
            AND unit = (SELECT sale_unit FROM Product WHERE id = %s)
            AND quantity = FLOOR(quantity)
        """, (user_id, product_id, product_id))
        cursor.execute(
            "DELETE FROM Cart_item WHERE userId = %s AND productId = %s",
            (user_id, product_id),
        )


def clear_cart(user_id):
    """Remove this user's cart items, unplaced preorders, and crews."""
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute("DELETE FROM Cart_item WHERE userId = %s", (user_id,))
        cursor.execute("DELETE FROM Preorder_item WHERE userId = %s AND orderId IS NULL", (user_id,))
        cursor.execute("DELETE FROM crew_cart WHERE owner = %s", (user_id,))


def add_preorder_item(user_id, preorder):
    """Put a pre-order item in the cart. Adding the same item again adds to its quantity."""
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        if preorder["product_id"] is not None:
            cursor.execute("SELECT name, sale_unit FROM Product WHERE id = %s AND isActive = 1",
                           (preorder["product_id"],))
            product = cursor.fetchone()
            if product and product["sale_unit"] == preorder["unit"]:
                return add_catalog_quantity(cursor, user_id, preorder["product_id"],
                                            whole_quantity(preorder["quantity"]))
        # Custom sourcing requests retain their stated unit and estimated price.
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


def get_cart_preorders(user_id, cursor=None):
    """Return the pre-order items in the user's cart (not yet ordered)."""
    if cursor is None:
        with database_cursor(lock_name=f"cart_{user_id}") as cursor:
            reconcile_stock(cursor, user_id)
            return get_cart_preorders(user_id, cursor)
    cursor.execute(
        """
        SELECT pre.id, pre.productId AS product_id, pre.name, pre.unit, pre.quantity, pre.unitPrice AS unit_price,
               (p.id IS NOT NULL AND pre.unit = p.sale_unit AND pre.quantity = FLOOR(pre.quantity)) AS catalog_item,
               p.isActive

        FROM Preorder_item pre LEFT JOIN Product p ON p.id = pre.productId
        WHERE pre.userId = %s AND pre.orderId IS NULL
        ORDER BY pre.name
        """,
        (user_id,),
    )
    items = cursor.fetchall()

    for item in items:
        item["preorder"] = True
        if item["product_id"] is not None and item["isActive"] == 0:
            item["error"] = "This product is no longer available. Remove it from your cart."
        # Older pre-orders were saved without a price, so guess one from the unit
        if item["unit_price"] is None:
            item["unit_price"] = guess_unit_price(item["unit"])
        item["unit_price_cents"] = int(round(item["unit_price"] * 100))
        item["total_cents"] = int(round(item["unit_price"] * item["quantity"] * 100))
        # Show 3.00 as 3 and 2.50 as 2.5.
        quantity = item["quantity"]
        item["quantity"] = int(quantity) if quantity == int(quantity) else quantity.normalize()
    return items


def remove_preorder(user_id, preorder_id):
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute(
            "DELETE FROM Preorder_item WHERE id = %s AND userId = %s AND orderId IS NULL",
            (preorder_id, user_id),
        )


def add_materials_to_cart(user_id, materials, action_type=None):
    """Add converted catalog quantities atomically, or preserve custom sourcing requests."""
    added = []
    preordered = []
    failed = []

    for material in materials:
        try:
            if action_type == "add_in_stock":
                if material.get("has_partial_stock"):
                    added.append(add_item(user_id, material["product"]["product_id"], material["in_stock_quantity"]))
                elif material.get("can_add"):
                    added.append(add_item(user_id, material["product"]["product_id"], material["buy_quantity"]))
            elif action_type == "preorder_remaining":
                if material.get("has_partial_stock") and material.get("remaining_preorder"):
                    preordered.append(add_preorder_item(user_id, material["remaining_preorder"]))
                elif material.get("preorder"):
                    preordered.append(add_preorder_item(user_id, material["preorder"]))
            else:
                if material.get("buy_quantity") is not None:
                    name = add_item(user_id, material["product"]["product_id"], material["buy_quantity"])
                    added.append(name)
                elif material.get("preorder"):
                    preordered.append(add_preorder_item(user_id, material["preorder"]))
                else:
                    raise ValueError("Choose the purchase quantity from the product page.")
        except ValueError as error:
            failed.append(str(error).rstrip("."))

    return {"added": added, "preordered": preordered, "failed": failed}


def add_crew(user_id, crew_json):
    crew = parse_crew(crew_json)
    crew_json = json.dumps(crew, sort_keys=True, allow_nan=False)
    crew_hash = hashlib.sha256(crew_json.encode()).hexdigest()
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute(
            """INSERT INTO crew_cart (owner, crew, crew_hash) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
            (user_id, crew_json, crew_hash),
        )
    return crew["label"]


def get_cart_crews(user_id):
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute("SELECT id, crew FROM crew_cart WHERE owner = %s ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
    crews = []
    for row in rows:
        crew = json.loads(row["crew"])
        estimate = estimate_crew_cost(crew)
        # name and total_cents let crews sit in the order summary next to products
        crews.append({"id": row["id"], "crew": True, "name": estimate["label"],
                      "estimate": estimate, "total_cents": estimate["price_cents"]})
    return crews


def remove_crew(user_id, crew_id):
    with database_cursor(lock_name=f"cart_{user_id}") as cursor:
        cursor.execute("DELETE FROM crew_cart WHERE id = %s AND owner = %s", (crew_id, user_id))
        return cursor.rowcount == 1
