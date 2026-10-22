"""Password checks, plus live Aiven tests that run only when RUN_AIVEN_DB_TESTS=1.

The live tests create their own test records and delete only those.
"""

import os
import unittest
import uuid

from argon2 import PasswordHasher, extract_parameters
from argon2.low_level import Type
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor, database_settings
from utils.passwords import check_password, hash_password
from utils.users import create_user


class DatabaseUnitTests(unittest.TestCase):
    def test_argon2id_verification(self):
        new_hash = hash_password("Fixture123!")
        self.assertEqual(extract_parameters(new_hash).type, Type.ID)
        self.assertTrue(check_password(new_hash, "Fixture123!"))
        self.assertFalse(check_password(new_hash, "Wrong123!"))
        self.assertFalse(check_password("invalid", "Fixture123!"))
        self.assertFalse(check_password(new_hash.rsplit("$", 1)[0], "Fixture123!"))

    def test_rejects_other_argon2_variants(self):
        for variant in (Type.I, Type.D):
            with self.subTest(variant=variant):
                encoded = PasswordHasher(type=variant).hash("Fixture123!")
                self.assertFalse(check_password(encoded, "Fixture123!"))

    def test_full_unicode_password_is_verified(self):
        password = "é" * 50 + "123!"
        encoded = hash_password(password)
        self.assertTrue(check_password(encoded, password))
        self.assertFalse(check_password(encoded, password[:-1] + "?"))


@unittest.skipUnless(os.getenv("RUN_AIVEN_DB_TESTS") == "1", "Opt in to primary database fixture tests.")
class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        from utils.rate_limits import limiter
        cls.app = app
        old_config = {key: app.config[key] for key in ("TESTING", "SECRET_KEY")}
        app.config.update(TESTING=True, SECRET_KEY="database-fixture-tests")
        cls.addClassCleanup(app.config.update, old_config)
        cls.addClassCleanup(setattr, limiter, "enabled", limiter.enabled)
        limiter.enabled = False
        if not database_settings()["host"].endswith(".aivencloud.com"):
            raise RuntimeError("Integration tests require the configured Aiven database.")
        cls.prefix = "erd_fixture_" + uuid.uuid4().hex[:12]
        cls.users = []
        cls.product = None
        cls.addClassCleanup(cls.cleanup)
        cls.emails = []
        for role in ("admin", "user", "user"):
            email = f"{cls.prefix}_{len(cls.users)}@example.test"
            cls.emails.append(email)
            cls.users.append(create_user(cls.form(email), role))
        cls.admin, cls.customer, cls.other = cls.users
        with database_cursor() as cursor:
            cursor.execute("""INSERT INTO Product
                (name, subCategory, category, price, stockQty, itemQty, unit, sku)
                VALUES (%s, 'Hand tools', 'tools', 19.95, 50, 10, 'box', %s)""",
                (cls.prefix, cls.prefix))
            cls.product = cursor.lastrowid
            cursor.execute("""INSERT INTO `Order` (userId, dateCreated, totalCost, orderStatus, shippingAddress)
                VALUES (%s, CURDATE(), 39.90, 'paid', 'Test shipping address')""", (cls.customer,))
            cls.order = cursor.lastrowid
            cursor.execute("INSERT INTO Order_item (orderId, productId, itemQty, unitPrice) VALUES (%s, %s, 2, 19.95)",
                           (cls.order, cls.product))
            cursor.execute("""INSERT INTO Payments (dateCharged, userId, payStatus, cardLast4, orderId, amount)
                VALUES (CURDATE(), %s, 'paid', '4242', %s, 39.90)""", (cls.customer, cls.order))

    @staticmethod
    def form(email):
        return dict(firstName="Fixture", lastName="Account", email=email,
                    password="Fixture123!", confirm_password="Fixture123!")

    @classmethod
    def cleanup(cls):
        with database_cursor() as cursor:
            for user_id in cls.users:
                cursor.execute("DELETE FROM `User` WHERE id = %s", (user_id,))
            if cls.product is not None:
                cursor.execute("DELETE FROM Product WHERE id = %s", (cls.product,))

    def client_for(self, user_id):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=user_id, csrf_token="fixture-csrf")
        return client

    def login(self, email, password="Fixture123!"):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["csrf_token"] = "fixture-csrf"
        response = client.post("/login", json={"email": email, "password": password},
                               headers={"X-CSRF-Token": "fixture-csrf"})
        return client, response

    def test_registration_login_and_duplicate_email(self):
        email = self.prefix + "_registration@example.test"
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["csrf_token"] = "fixture-csrf"
        response = client.post("/register", json=self.form(email), headers={"X-CSRF-Token": "fixture-csrf"})
        with database_cursor() as cursor:
            cursor.execute("SELECT id, passkey FROM `User` WHERE email = %s", (email,))
            row = cursor.fetchone()
            if row:
                self.users.append(row["id"])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(extract_parameters(row["passkey"]).type, Type.ID)
        self.assertEqual(client.get("/dashboard").status_code, 200)
        _, response = self.login(email)
        self.assertEqual(response.status_code, 200)
        _, response = self.login(email, "wrong123!")
        self.assertEqual(response.status_code, 401)
        with self.assertRaises(IntegrityError):
            create_user(self.form(email))

    def test_login_preserves_argon2id_hash(self):
        encoded = PasswordHasher(time_cost=2, type=Type.ID).hash("Fixture123!")
        with database_cursor() as cursor:
            cursor.execute("UPDATE `User` SET passkey = %s WHERE id = %s",
                           (encoded, self.other))
        _, response = self.login(self.emails[2])
        self.assertEqual(response.status_code, 200)
        with database_cursor() as cursor:
            cursor.execute("SELECT passkey FROM `User` WHERE id = %s", (self.other,))
            self.assertEqual(cursor.fetchone()["passkey"], encoded)

    def test_admin_creation_disabling_and_role_checks(self):
        admin = self.client_for(self.admin)
        self.assertEqual(admin.get("/dashboard").status_code, 200)
        email = self.prefix + "_admin_created@example.test"
        response = admin.post("/dashboard", data={**self.form(email), "permission_level": "admin",
                                                  "csrf_token": "fixture-csrf"})
        with database_cursor() as cursor:
            cursor.execute("SELECT id, permissions, passkey FROM `User` WHERE email = %s", (email,))
            row = cursor.fetchone()
            if row:
                self.users.append(row["id"])
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(row)
        self.assertEqual(row["permissions"], "admin")
        self.assertEqual(extract_parameters(row["passkey"]).type, Type.ID)
        with database_cursor() as cursor:
            cursor.execute("SELECT 1 FROM Customer WHERE userId = %s", (row["id"],))
            self.assertIsNotNone(cursor.fetchone())
        try:
            response = admin.post(f"/dashboard/users/{self.other}/status",
                                  data={"status": "disabled", "csrf_token": "fixture-csrf"})
            self.assertEqual(response.status_code, 302)
            _, response = self.login(self.emails[2])
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client_for(self.other).get("/cart").status_code, 302)
        finally:
            with database_cursor() as cursor:
                cursor.execute("UPDATE Customer SET accountStatus = 'active' WHERE userId = %s", (self.other,))
        response = self.client_for(self.customer).post("/dashboard", data={"csrf_token": "fixture-csrf"})
        self.assertEqual(response.status_code, 403)

    def test_order_history_prices_and_ownership(self):
        from services.orders import get_order_by_id, get_order_items
        client = self.client_for(self.customer)
        for path in ("/dashboard/orders", f"/dashboard/orders/{self.order}", f"/order-confirmation/{self.order}"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"39.90", response.data)
        with database_cursor() as cursor:
            cursor.execute("UPDATE Product SET price = 99.99 WHERE id = %s", (self.product,))
        self.assertEqual(get_order_items(self.order, self.customer)[0]["unit_price"], "$19.95")
        self.assertIsNone(get_order_by_id(self.order, self.other))
        self.assertEqual(get_order_items(self.order, self.other), [])
        self.assertEqual(self.client_for(self.other).get(f"/dashboard/orders/{self.order}").status_code, 404)
        response = self.client_for(self.other).get(f"/order-confirmation/{self.order}")
        self.assertNotIn(b"39.90", response.data)

    def test_catalog_manufacturers_and_planner(self):
        from services.products import get_manufacturers, get_planner_catalog, get_products_by_ids, search_products
        self.assertTrue(get_manufacturers())
        products, _ = search_products(search=self.prefix)
        self.assertEqual(products[0]["pack_quantity"], 10)
        self.assertEqual(products[0]["available_quantity"], 50)
        self.assertIn(self.product, get_products_by_ids([self.product]))
        self.assertIn(self.product, {row["product_id"] for row in get_planner_catalog()})
        client = self.app.test_client()
        for path in ("/products", "/products?category=tools", "/heavy-machinery", "/manufacturers"):
            self.assertEqual(client.get(path).status_code, 200)

    def test_pro_expiry_uses_customer_profile(self):
        from services.subscriptions import get_user_subscription, has_active_pro
        with database_cursor() as cursor:
            cursor.execute("UPDATE Customer SET proDate = DATE_ADD(CURDATE(), INTERVAL 1 DAY) WHERE userId = %s",
                           (self.admin,))
        self.assertTrue(has_active_pro(self.admin))
        self.assertEqual(get_user_subscription(self.admin)["status"], "active")
        with database_cursor() as cursor:
            cursor.execute("UPDATE Customer SET proDate = DATE_SUB(CURDATE(), INTERVAL 1 DAY) WHERE userId = %s",
                           (self.admin,))
        self.assertFalse(has_active_pro(self.admin))

    def test_schema_constraints_and_no_raw_card_number(self):
        with database_cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM Payments")
            self.assertNotIn("cardNumber", {row["Field"] for row in cursor.fetchall()})
        for update in ("stockQty = -1", "itemQty = 0", "price = -1"):
            with self.assertRaises(Error), database_cursor() as cursor:
                cursor.execute("UPDATE Product SET " + update + " WHERE id = %s", (self.product,))


if __name__ == "__main__":
    unittest.main()
