import ast
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from flask import render_template

from app import app


class Controls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.buttons = []
        self.inputs = []
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "button":
            self.buttons.append(attributes)
        elif tag == "input":
            self.inputs.append(attributes)
        elif tag == "a":
            self.links.append(attributes)


class CartCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.dict(app.config, TESTING=True, SECRET_KEY="cart-test")
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.client = app.test_client()
        # These rendering routes must never query or mutate the live database.
        self.database_patch = patch("mysql.connector.connect", side_effect=AssertionError("Unexpected database access"))
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

    def render(self, template, **context):
        with app.test_request_context("/cart"):
            return render_template(template, **context)

    def test_three_pages_render_for_guests_without_database_access(self):
        for path, heading in [
            ("/cart", "Your cart is empty."),
            ("/checkout", "Secure payment processing is not connected yet."),
            ("/order-confirmation", "Order confirmation is not available yet."),
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn(heading, html)
                self.assertIn('class="navbar"', html)
                self.assertNotIn("under_construction.png", html)
                self.assertIn("checkout.css", html)

    def test_empty_cart_hides_checkout_action_and_quantity_controls(self):
        html = self.client.get("/cart").get_data(as_text=True)
        self.assertIn('href="/products"', html)
        self.assertNotIn("Proceed to Checkout", html)
        self.assertNotIn('class="shopping-quantity"', html)
        self.assertNotIn("Estimated total", html)
        self.assertFalse(any(link.get("href") == "/checkout" for link in Controls(html).links))

    def test_prices_quantities_and_totals_use_integer_cents(self):
        # Test fixtures exercise the prepared data contract, never customer records.
        items = [
            {"product_id": 1, "name": "Test material A", "quantity": 3,
             "unit_price_cents": 1999, "brand": "Test brand"},
            {"product_id": 2, "name": "Test material B", "quantity": 2,
             "unit_price_cents": 425, "image_url": "/static/images/logo.png"},
        ]
        for template in ["cart/cart.html", "cart/checkout.html"]:
            html = self.render(template, cart_items=items)
            self.assertIn("$59.97", html)
            self.assertIn("$8.50", html)
            self.assertEqual(html.count("$68.47"), 2)
            self.assertIn("Excludes shipping and tax", html)
            self.assertIn("Calculated at checkout", html)
            self.assertIn("Test material A", html)
        html = self.render("cart/cart.html", cart_items=items)
        controls = Controls(html)
        quantities = [field for field in controls.inputs if field.get("type") == "number"]
        self.assertEqual([field["value"] for field in quantities], ["3", "2"])
        self.assertTrue(all("disabled" in field and field["min"] == "1" for field in quantities))
        actions = [button for button in controls.buttons if button.get("aria-describedby") == "cart-controls-note" or "quantity for" in button.get("aria-label", "")]
        self.assertEqual(len(actions), 6)
        self.assertTrue(all("disabled" in button for button in actions))

    def test_missing_price_is_not_zero_and_blocks_complete_estimate(self):
        html = self.render("cart/cart.html", cart_items=[
            {"name": "Unpriced material", "quantity": 1, "unit_price_cents": None},
            {"name": "Priced material", "quantity": 1, "unit_price_cents": 1000},
        ])
        self.assertIn("A complete estimate cannot be shown", html)
        self.assertEqual(html.count("Unavailable"), 4)
        self.assertNotIn("$0.00", html)
        self.assertIn("$10.00", html)
        zero_html = self.render("cart/cart.html", cart_items=[
            {"name": "Zero-priced material", "quantity": 1, "unit_price_cents": 0},
        ])
        self.assertIn("$0.00", zero_html)
        self.assertNotIn("A complete estimate cannot be shown", zero_html)

    def test_product_fields_are_escaped_and_optional_links_are_supported(self):
        html = self.render("cart/cart.html", cart_items=[
            {"name": '<script>alert("x")</script>', "brand": "<b>Brand</b>",
             "quantity": 1, "unit_price_cents": 100, "detail_url": "/existing-product/1"},
        ])
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertNotIn("<b>Brand</b>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('href="/existing-product/1"', html)
        self.assertIn('use href="#shop-box"', html)

    def test_payment_does_not_collect_card_details_or_enable_purchase(self):
        html = self.client.get("/checkout").get_data(as_text=True)
        controls = Controls(html)
        self.assertEqual({field["name"] for field in controls.inputs}, {
            "first_name", "last_name", "email", "phone", "street_address", "apartment", "city", "zip_code",
        })
        place_order = [button for button in controls.buttons if button.get("aria-describedby") == "place-order-note"]
        self.assertEqual(len(place_order), 1)
        self.assertIn("disabled", place_order[0])
        self.assertIn('id="payment-provider-container"', html)
        self.assertIn('id="checkout-validation-status"', html)

    def test_checkout_post_is_unavailable_and_preserves_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["username"] = "Test user"
        response = self.client.post("/checkout", data={"email": "test@example.test"})
        self.assertEqual(response.status_code, 501)
        self.assertNotIn("redirect_url", response.json)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 7)
        self.assertEqual(self.client.get("/checkout").status_code, 200)

    def test_confirmation_ignores_unverified_url_parameters(self):
        html = self.client.get("/order-confirmation?order_id=7&paid=true&verified_order=true&number=FAKE-7").get_data(as_text=True)
        self.assertIn("Order confirmation is not available yet.", html)
        self.assertNotIn("<h1>Order confirmed</h1>", html)
        self.assertNotIn("FAKE-7", html)
        self.assertIn('href="/dashboard/orders"', html)
        self.assertIn('href="/dashboard"', html)

    def test_account_email_prefill_uses_existing_session_only(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 7
            session["email"] = "test@example.test"
        html = self.client.get("/checkout").get_data(as_text=True)
        self.assertIn('value="test@example.test"', html)

    def test_cart_navigation_and_existing_guest_pages(self):
        for path in ["/home", "/products", "/login", "/register", "/reviews", "/manufacturers", "/planner"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('class="nav-cart" href="/cart"', response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/dashboard/orders").status_code, 302)

    def test_new_business_functions_have_only_docstrings_and_pass(self):
        root = Path(__file__).resolve().parents[1] / "services"
        expected = {
            "cart.py": {"get_cart_items", "update_cart_quantity", "remove_cart_item", "calculate_cart_subtotal"},
            "checkout.py": {"validate_checkout_data", "calculate_order_total"},
            "payment.py": {"create_payment_session", "verify_payment"},
            "orders.py": {"create_order", "get_order_confirmation"},
        }
        for filename, names in expected.items():
            functions = {node.name: node for node in ast.parse((root / filename).read_text()).body if isinstance(node, ast.FunctionDef)}
            for name in names:
                with self.subTest(function=name):
                    function = functions[name]
                    self.assertIsNotNone(ast.get_docstring(function))
                    self.assertEqual(len(function.body), 2)
                    self.assertIsInstance(function.body[1], ast.Pass)


if __name__ == "__main__":
    unittest.main()
