import hashlib
import json

from services.crews import estimate_crew_cost, parse_crew
from utils.database import database_cursor

def get_cart(user_id):
    # TODO: Get the user's cart items with current prices, totals
    pass


def add_item(user_id, product_id, quantity):
    # TODO: Add the product, checking the total quantity if it's already in the cart.
    pass


def change_quantity(user_id, product_id, quantity):
    # TODO: Update an item in the user's cart after checking the quantity and stock.
    pass


def remove_item(user_id, product_id):
    # TODO: Remove this product from the user's cart
    pass


def add_materials_to_cart(user_id, materials):
    # TODO: Add matching planner materials to the cart and report what was added, skipped, or failed.
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
    return [{"id": row["id"], "estimate": estimate_crew_cost(json.loads(row["crew"]))} for row in rows]


def remove_crew(user_id, crew_id):
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM crew_cart WHERE id = %s AND owner = %s", (crew_id, user_id))
        return cursor.rowcount == 1
