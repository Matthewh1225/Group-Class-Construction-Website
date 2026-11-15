from services.emails import send_order_email
from utils.database import database_cursor


def create_order(user_id, checkout_data):
    """Save the order, take items out of stock, empty the cart, and email the customer.

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
            "SELECT name, unit, quantity, unitPrice FROM Preorder_item "
            "WHERE userId = %s AND orderId IS NULL FOR UPDATE",
            (user_id,),
        )
        preorders = cursor.fetchall()

        if not items and not preorders:
            raise ValueError("Your cart is empty.")

        total = 0
        for item in items:
            if item["itemQty"] > item["stockQty"]:
                raise ValueError("Not enough stock of " + item["name"] + ".")
            total += item["price"] * item["itemQty"]
        for preorder in preorders:
            # Price TBD pre-orders are not part of the total yet
            if preorder["unitPrice"] is not None:
                total += preorder["unitPrice"] * preorder["quantity"]
        total = round(total, 2)

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

        cursor.execute("DELETE FROM Cart_item WHERE userId = %s", (user_id,))

        # Attach the pre-orders to this order, which takes them out of the cart
        cursor.execute(
            "UPDATE Preorder_item SET orderId = %s WHERE userId = %s AND orderId IS NULL",
            (order_id, user_id),
        )

    # The order is already saved, so an email problem must not undo it
    try:
        send_order_email(checkout_data["email"], checkout_data["first_name"], order_id,
                         items, preorders, total, address)
    except Exception as error:
        print("Could not send order email:", error)

    return order_id


def get_user_orders(user_id):
  # TODO: Get this user's orders with dates, statuses, and totals.
  pass


def get_order(order_id, user_id):
   # TODO: Get order details after checking the owner.
   pass


def get_order_items(order_id, user_id):
   # TODO: Get this user's order items, quantities, and prices paid.
   pass
