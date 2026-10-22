"""Order history with ownership checks and prices saved at purchase time."""

from utils.database import database_cursor

# Column names match what the order pages show.
ORDER_COLUMNS = """id, id AS number, dateCreated AS placed_at, dateCreated AS date,
                   orderStatus AS status, CONCAT('$', FORMAT(totalCost, 2)) AS total,
                   CAST(totalCost * 100 AS SIGNED) AS total_cents, shippingAddress AS shipping"""


def create_order(user_id, checkout_data):
    """TODO: save the order, its items and a payment in one transaction. Until then checkout always fails."""
    raise ValueError("Placing orders is not available yet.")


def get_user_orders(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT " + ORDER_COLUMNS + " FROM `Order` WHERE userId = %s ORDER BY dateCreated DESC, id DESC",
                       (user_id,))
        return cursor.fetchall()


# Returns None if the order is missing or belongs to someone else.
def get_order_by_id(order_id, user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT " + ORDER_COLUMNS + " FROM `Order` WHERE id = %s AND userId = %s",
                       (order_id, user_id))
        return cursor.fetchone()


def get_order_items(order_id, user_id):
    with database_cursor() as cursor:
        cursor.execute("""SELECT p.name, i.itemQty AS quantity,
                                 CONCAT('$', FORMAT(i.unitPrice, 2)) AS unit_price,
                                 CONCAT('$', FORMAT(i.unitPrice * i.itemQty, 2)) AS total,
                                 CAST(i.unitPrice * i.itemQty * 100 AS SIGNED) AS total_cents
                          FROM Order_item i
                          JOIN `Order` o ON o.id = i.orderId
                          JOIN Product p ON p.id = i.productId
                          WHERE o.id = %s AND o.userId = %s ORDER BY i.productId""",
                       (order_id, user_id))
        return cursor.fetchall()
