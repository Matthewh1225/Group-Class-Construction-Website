import json
import logging
from decimal import Decimal

from services.checkout import add_shipping_and_tax
from services.crews import estimate_crew_cost
from services.emails import send_order_email
from services.products import guess_unit_price
from utils.database import database_cursor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    logger.addHandler(logging.StreamHandler())


def create_order(user_id, checkout_data):
    """Save the order, update the cart and stock, and email a receipt if requested.

    Returns the new order id. Raises ValueError if the cart can't be ordered.
    """
    address = checkout_data["street_address"]
    if checkout_data["apartment"]:
        address += ", " + checkout_data["apartment"]
    address += ", " + checkout_data["city"] + ", " + checkout_data["state"] + " " + checkout_data["zip_code"]

    # Everything in this block is saved together, or not at all
    with database_cursor() as cursor:
        # FOR UPDATE locks the product rows so two buyers cannot take the same stock
        cursor.execute(
            """
            SELECT p.id AS product_id, p.name, p.price, p.stockQty, ci.itemQty
            FROM Cart_item ci
            JOIN Product p ON p.id = ci.productId
            WHERE ci.userId = %s
            FOR UPDATE
            """,
            (user_id,),
        )
        items = cursor.fetchall()

        # Pre-orders don't use store stock, so there is nothing to check or subtract
        cursor.execute(
            "SELECT id, name, unit, quantity, unitPrice FROM Preorder_item "
            "WHERE userId = %s AND orderId IS NULL FOR UPDATE",
            (user_id,),
        )
        preorders = cursor.fetchall()

        # Older pre-orders were saved without a price: guess one and save it with the order
        for preorder in preorders:
            if preorder["unitPrice"] is None:
                preorder["unitPrice"] = guess_unit_price(preorder["unit"])
                cursor.execute(
                    "UPDATE Preorder_item SET unitPrice = %s WHERE id = %s",
                    (preorder["unitPrice"], preorder["id"]),
                )

        # Crews in the cart: price each one the same way the cart page does
        cursor.execute("SELECT crew FROM crew_cart WHERE owner = %s FOR UPDATE", (user_id,))
        crews = []
        for row in cursor.fetchall():
            crews.append(estimate_crew_cost(json.loads(row["crew"])))

        if not items and not preorders and not crews:
            raise ValueError("Your cart is empty.")

        # Add up line totals in cents, rounded the same way as the cart page
        subtotal_cents = 0
        for item in items:
            if item["itemQty"] > item["stockQty"]:
                raise ValueError("Not enough stock of " + item["name"] + ".")
            subtotal_cents += int(round(item["price"] * 100)) * item["itemQty"]
        for preorder in preorders:
            subtotal_cents += int(round(preorder["unitPrice"] * preorder["quantity"] * 100))
        for crew in crews:
            subtotal_cents += crew["price_cents"]

        # Same shipping and tax as the cart page, so the order total matches
        totals = add_shipping_and_tax(subtotal_cents)
        total = Decimal(totals["total_cents"]) / 100

        cursor.execute(
            "INSERT INTO `Order` (userId, dateCreated, totalCost, orderStatus, shippingAddress) "
            "VALUES (%s, CURDATE(), %s, 'pending', %s)",
            (user_id, total, address),
        )
        order_id = cursor.lastrowid

        for item in items:
            cursor.execute(
                "INSERT INTO Order_item (orderId, productId, itemQty, unitPrice) VALUES (%s, %s, %s, %s)",
                (order_id, item["product_id"], item["itemQty"], item["price"]),
            )
            cursor.execute(
                "UPDATE Product SET stockQty = stockQty - %s WHERE id = %s",
                (item["itemQty"], item["product_id"]),
            )

        # Save each crew with the order so the receipt and order history can show it
        for crew in crews:
            cursor.execute(
                "INSERT INTO Order_crew (orderId, label, workers, days, priceCents) VALUES (%s, %s, %s, %s, %s)",
                (order_id, crew["label"], crew["workers"], crew["days"], crew["price_cents"]),
            )

        cursor.execute("DELETE FROM Cart_item WHERE userId = %s", (user_id,))
        # Crews are paid for in the order total, so take them out of the cart
        cursor.execute("DELETE FROM crew_cart WHERE owner = %s", (user_id,))

        # Attach the pre-orders to this order, which takes them out of the cart
        cursor.execute(
            "UPDATE Preorder_item SET orderId = %s WHERE userId = %s AND orderId IS NULL",
            (order_id, user_id),
        )

    # The order is already saved, so an email problem must not undo it.
    if checkout_data.get("email_receipt") is True:
        logger.info("Receipt requested for order %s; preparing Resend request", order_id)
        try:
            with database_cursor() as cursor:
                cursor.execute("SELECT email FROM User WHERE id = %s", (user_id,))
                account = cursor.fetchone()
            if not account or not account.get("email"):
                raise ValueError("The ordering account has no receipt email address.")
            email_id = send_order_email(account["email"], checkout_data["first_name"], order_id,
                             items, preorders, crews, totals, address)
            logger.info("Resend accepted receipt for order %s; email_id=%s", order_id, email_id)
        except Exception as error:
            logger.error("Receipt failed for order %s (%s): %s", order_id, type(error).__name__, error)
    else:
        logger.info("Receipt skipped for order %s: checkbox not selected", order_id)

    return order_id


def make_order_dict(row):
    """Turn an Order row into the dictionary the order pages use."""
    total_cents = int(round(row["totalCost"] * 100))
    return {
        "id": row["id"],
        "number": "#" + str(row["id"]),
        "date": row["dateCreated"],
        "placed_at": row["dateCreated"],
        "status": row["orderStatus"],
        "total_cents": total_cents,
        "total": "${:,.2f}".format(total_cents / 100),
        "shipping": row["shippingAddress"],
    }


def add_receipt_totals(order, items):
    """Add subtotal, shipping and tax to an order so the receipt can list them."""
    subtotal_cents = sum(item["total_cents"] for item in items)
    totals = add_shipping_and_tax(subtotal_cents)
    order["subtotal_cents"] = totals["subtotal_cents"]
    order["shipping_cents"] = totals["shipping_cents"]
    order["tax_cents"] = totals["tax_cents"]


def get_user_orders(user_id):
    """Get this user's orders, newest first."""
    with database_cursor() as cursor:
        cursor.execute(
            "SELECT id, dateCreated, totalCost, orderStatus, shippingAddress "
            "FROM `Order` WHERE userId = %s ORDER BY id DESC",
            (user_id,),
        )
        return [make_order_dict(row) for row in cursor.fetchall()]


def get_order(order_id, user_id):
    """Get one order, or None if it doesn't exist or belongs to someone else."""
    with database_cursor() as cursor:
        cursor.execute(
            "SELECT id, dateCreated, totalCost, orderStatus, shippingAddress "
            "FROM `Order` WHERE id = %s AND userId = %s",
            (order_id, user_id),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return make_order_dict(row)


def get_order_items(order_id, user_id):
    """Get the store products and pre-order materials on one of this user's orders."""
    items = []
    with database_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.name, oi.itemQty, oi.unitPrice
            FROM Order_item oi
            JOIN `Order` o ON o.id = oi.orderId
            JOIN Product p ON p.id = oi.productId
            WHERE oi.orderId = %s AND o.userId = %s
            """,
            (order_id, user_id),
        )
        product_rows = cursor.fetchall()

        cursor.execute(
            "SELECT name, quantity, unitPrice FROM Preorder_item WHERE orderId = %s AND userId = %s",
            (order_id, user_id),
        )
        preorder_rows = cursor.fetchall()

    for row in product_rows:
        unit_cents = int(round(row["unitPrice"] * 100))
        items.append(make_item_dict(row["name"], row["itemQty"], unit_cents, unit_cents * row["itemQty"]))
    for row in preorder_rows:
        unit_cents = int(round(row["unitPrice"] * 100))
        total_cents = int(round(row["unitPrice"] * row["quantity"] * 100))
        items.append(make_item_dict(row["name"], row["quantity"], unit_cents, total_cents))

    with database_cursor() as cursor:
        cursor.execute(
            "SELECT oc.label, oc.workers, oc.days, oc.priceCents FROM Order_crew oc "
            "JOIN `Order` o ON o.id = oc.orderId WHERE oc.orderId = %s AND o.userId = %s",
            (order_id, user_id),
        )
        crew_rows = cursor.fetchall()
    for row in crew_rows:
        item = make_item_dict(row["label"] + " (crew, " + str(row["workers"]) + " workers, " + row["days"] + ")",
                              1, row["priceCents"], row["priceCents"])
        items.append(item)
    return items


def make_item_dict(name, quantity, unit_cents, total_cents):
    """One line on an order page. Has both cents and display text for the two templates."""
    return {
        "name": name,
        "quantity": quantity,
        "unit_price_cents": unit_cents,
        "total_cents": total_cents,
        "unit_price": "${:,.2f}".format(unit_cents / 100),
        "total": "${:,.2f}".format(total_cents / 100),
    }
