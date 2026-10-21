import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from mysql.connector import Error

from services.cart import (add_cart_item, calculate_cart_subtotal, get_cart_items,
                           read_quantity, remove_cart_item, update_cart_quantity)
from services.checkout import calculate_order_total
from utils.database import database_cursor, database_settings


class CartValidationTests(unittest.TestCase):
    def test_whole_number_quantities(self):
        for quantity in (1, "2", "2.000", Decimal("3")):
            self.assertEqual(read_quantity(quantity), int(Decimal(str(quantity))))
        for quantity in (None, "", "two", True, 0, -1, "1.5", "NaN", "Infinity", "2147483648"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                read_quantity(quantity)

    def test_cart_totals(self):
        items = [{"error": "", "total_cents": 3990}, {"error": "", "total_cents": 425}]
        self.assertEqual(calculate_order_total(items), {
            "subtotal_cents": 4415, "shipping_cents": 0, "tax_cents": 0, "total_cents": 4415,
        })
        self.assertEqual(calculate_order_total([]), {})
        self.assertEqual(calculate_order_total([{"error": "Out of stock", "total_cents": 3990}]), {})
        self.assertEqual(calculate_order_total([{"error": "", "total_cents": None}]), {})


@unittest.skipUnless(os.getenv("RUN_CART_DB_TESTS") == "1", "Set RUN_CART_DB_TESTS=1 to use the local test database.")
class CartDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        from utils.passwords import hash_password
        from utils.rate_limits import limiter

        cls.app = app
        cls.old_config = {key: app.config[key] for key in ("TESTING", "SECRET_KEY")}
        app.config.update(TESTING=True, SECRET_KEY="cart-tests")
        cls.context = app.app_context()
        cls.context.push()
        cls.addClassCleanup(cls.context.pop)
        cls.addClassCleanup(app.config.update, cls.old_config)
        settings = database_settings()
        if settings["host"] not in ("localhost", "127.0.0.1") or settings["database"] != "Construction_db_test":
            raise RuntimeError("Cart database tests require localhost / Construction_db_test.")
        cls.old_limiter = limiter.enabled
        limiter.enabled = False
        cls.addClassCleanup(setattr, limiter, "enabled", cls.old_limiter)
        cls.users = []
        cls.products = []
        cls.addClassCleanup(cls.remove_test_data)
        prefix = "cart_test_" + uuid.uuid4().hex[:10]
        password = hash_password("CartTest123!")
        with database_cursor() as cursor:
            for suffix in ("a", "b"):
                name = prefix + suffix
                cursor.execute("INSERT INTO `User` (username, email, password) VALUES (%s, %s, %s)",
                               (name, name + "@example.test", password))
                cls.users.append(cursor.lastrowid)
            for suffix, price, step in (("single", "19.95", "1"), ("bulk", "4.25", "5")):
                name = prefix + suffix
                cursor.execute("""
                    INSERT INTO Product (name, sku, unit, price, itemQty, purchaseIncrement, category)
                    VALUES (%s, %s, 'piece', %s, 100, %s, 'tools')
                """, (name, name, price, step))
                cls.products.append(cursor.lastrowid)

    @classmethod
    def remove_test_data(cls):
        with database_cursor() as cursor:
            for user_id in cls.users:
                cursor.execute("DELETE FROM `User` WHERE Id = %s", (user_id,))
            for product_id in cls.products:
                cursor.execute("DELETE FROM Product WHERE Id = %s", (product_id,))

    def setUp(self):
        self.user, self.other_user = self.users
        self.product, self.bulk = self.products
        with database_cursor() as cursor:
            cursor.execute("DELETE FROM Cart_item WHERE user_id IN (%s, %s)", tuple(self.users))
            cursor.execute("""
                UPDATE Product SET price = 19.95, itemQty = 100, isActive = 1, purchaseIncrement = 1
                WHERE Id = %s
            """, (self.product,))
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id=self.user, csrf_token="cart-csrf", permission_level="user")

    def post(self, path, **data):
        return self.client.post(path, data={"csrf_token": "cart-csrf", **data})

    def test_add_reopen_repeat_update_and_remove(self):
        add_cart_item(self.user, self.product, "2")
        add_cart_item(self.user, self.product, "3")
        items = get_cart_items(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 5)
        self.assertEqual(items[0]["total_cents"], 9975)
        self.assertEqual(calculate_cart_subtotal(self.user), Decimal("99.75"))
        update_cart_quantity(self.user, self.product, "4")
        update_cart_quantity(self.user, self.product, "4")
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 4)
        self.assertTrue(remove_cart_item(self.user, self.product))
        self.assertFalse(remove_cart_item(self.user, self.product))
        self.assertEqual(get_cart_items(self.user), [])

    def test_invalid_products_quantities_and_stock(self):
        for quantity in (None, "", "0", "-1", "0.5", "NaN", "101"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                add_cart_item(self.user, self.product, quantity)
        with self.assertRaises(ValueError):
            add_cart_item(self.user, 2147483647, "1")
        add_cart_item(self.user, self.product, "99")
        with self.assertRaises(ValueError):
            add_cart_item(self.user, self.product, "2")
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 99)
        with self.assertRaises(ValueError):
            update_cart_quantity(self.user, self.product, "1.5")
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 99)

    def test_pack_sizes_and_unavailable_products(self):
        with self.assertRaises(ValueError):
            add_cart_item(self.user, self.bulk, "1")
        add_cart_item(self.user, self.bulk, "5")
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 5)
        for change in ("isActive = 0", "price = NULL", "itemQty = 0"):
            with database_cursor() as cursor:
                cursor.execute("UPDATE Product SET isActive = 1, price = 19.95, itemQty = 100 WHERE Id = %s",
                               (self.product,))
                cursor.execute("UPDATE Product SET " + change + " WHERE Id = %s", (self.product,))
            with self.subTest(change=change), self.assertRaises(ValueError):
                add_cart_item(self.user, self.product, "1")

    def test_current_prices_and_availability(self):
        add_cart_item(self.user, self.product, "2")
        with database_cursor() as cursor:
            cursor.execute("UPDATE Product SET name = 'Updated cart product', price = 21.23 WHERE Id = %s",
                           (self.product,))
        items = get_cart_items(self.user)
        self.assertEqual(items[0]["name"], "Updated cart product")
        self.assertEqual(items[0]["unit_price_cents"], 2123)
        self.assertEqual(calculate_order_total(items)["total_cents"], 4246)
        with database_cursor() as cursor:
            cursor.execute("UPDATE Product SET itemQty = 1 WHERE Id = %s", (self.product,))
        items = get_cart_items(self.user)
        self.assertTrue(items[0]["error"])
        self.assertEqual(calculate_order_total(items), {})
        page = self.client.get("/cart")
        self.assertIn(b"Only 1 piece", page.data)
        self.assertIn(b"Resolve cart items to continue", page.data)

    def test_users_cannot_change_each_others_carts(self):
        add_cart_item(self.other_user, self.product, "2")
        self.assertEqual(get_cart_items(self.user), [])
        with self.assertRaises(ValueError):
            update_cart_quantity(self.user, self.product, "3")
        self.assertFalse(remove_cart_item(self.user, self.product))
        self.assertEqual(get_cart_items(self.other_user)[0]["quantity"], 2)

    def test_table_rejects_duplicates_and_nonpositive_quantities(self):
        add_cart_item(self.user, self.product, "1")
        with self.assertRaises(Error), database_cursor() as cursor:
            cursor.execute("INSERT INTO Cart_item VALUES (%s, %s, 1)", (self.user, self.product))
        with self.assertRaises(Error), database_cursor() as cursor:
            cursor.execute("INSERT INTO Cart_item VALUES (%s, %s, 0)", (self.user, self.bulk))

    def test_concurrent_additions_keep_both_quantities(self):
        def add():
            with self.app.app_context():
                add_cart_item(self.user, self.product, "1")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(add), executor.submit(add)]
            for future in futures:
                future.result()
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 2)

    def test_cart_routes_and_validation(self):
        response = self.post("/cart/add", product_id=self.product, quantity="2", manufacturer="7", category="tools")
        self.assertEqual(response.status_code, 303)
        self.assertIn("manufacturer=7", response.location)
        self.assertIn(b"$39.90", self.client.get("/cart").data)
        response = self.post("/cart/update", product_id=self.product, quantity="3")
        self.assertEqual(response.status_code, 303)
        self.assertIn(b"$59.85", self.client.get("/cart").data)
        self.post("/cart/update", product_id=self.product, quantity="0")
        self.assertEqual(get_cart_items(self.user)[0]["quantity"], 3)
        self.post("/cart/remove", product_id=self.product)
        self.assertIn(b"Your cart is empty", self.client.get("/cart").data)
        self.assertEqual(self.client.post("/cart/add", data={"product_id": self.product, "quantity": "1"}).status_code, 400)
        self.assertEqual(self.app.test_client().get("/cart").status_code, 302)

    def test_planner_add_all_and_single_material(self):
        materials = [{"material_name": "Test part", "specification": "", "quantity": amount,
                      "unit": "piece", "notes": "Test allowance", "product_id": self.product}
                     for amount in (2.2, 1.1)]
        materials.append({**materials[0], "product_id": None})
        job = {"result": {"materials": materials}}
        with patch("routes.planner.get_job", return_value=job):
            response = self.post("/planner/jobs/test-cart-job/cart")
            self.assertEqual(response.status_code, 303)
            self.assertEqual(get_cart_items(self.user)[0]["quantity"], 4)
            self.assertIn(b"$79.80", self.client.get("/cart").data)
            self.post("/planner/jobs/test-cart-job/cart", material="0")
            self.assertEqual(get_cart_items(self.user)[0]["quantity"], 7)
        with patch("routes.planner.get_job", return_value=None):
            self.assertEqual(self.post("/planner/jobs/not-owned/cart").status_code, 404)

    def test_unfinished_checkout_does_not_confirm_an_order(self):
        add_cart_item(self.user, self.product, "1")
        response = self.post("/checkout")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Placing orders is not available yet", response.data)


if __name__ == "__main__":
    unittest.main()
