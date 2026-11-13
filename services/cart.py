import hashlib
import json

from services.crews import estimate_crew_cost, parse_crew
from utils.database import database_cursor

def get_cart(user_id):
    # TODO: Get cart items with current prices and totals.
    pass


def add_item(user_id, product_id, quantity):
    # TODO: Add the product and check the combined quantity.
    pass


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
