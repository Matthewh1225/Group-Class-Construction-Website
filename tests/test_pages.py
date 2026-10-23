"""Page tests that use mocks, so they never open the MySQL database."""

import json
import re
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import url_for
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from werkzeug.routing import BuildError

from planning.project_forms import PROJECT_TEMPLATES, build_project
from utils.passwords import hash_password
from utils.users import check_login, full_name, get_account, looks_like_email


class PageTestCase(unittest.TestCase):
    def setUp(self):
        from app import app
        self.app = app
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        database = patch("planning.jobs.database_path", return_value=Path(folder.name) / "jobs.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        old_config = {key: app.config[key] for key in ("TESTING", "SECRET_KEY")}
        app.config.update(TESTING=True, SECRET_KEY="page-tests")
        self.addCleanup(app.config.update, old_config)
        # Several tests post to rate-limited routes.
        from utils.rate_limits import limiter
        self.addCleanup(setattr, limiter, "enabled", limiter.enabled)
        limiter.enabled = False

    def log_in(self, permissions):
        """Return a client signed in as user 1. The account lookup that runs before every request is mocked."""
        account = {"firstName": "Test", "lastName": "Person", "permissions": permissions,
                   "accountStatus": "active"}
        patcher = patch("routes.auth.get_account", return_value=account)
        patcher.start()
        self.addCleanup(patcher.stop)

        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, csrf_token="page-csrf")
        return client

    def signed_out_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["csrf_token"] = "page-csrf"
        return client


class AdminUserListTests(PageTestCase):
    def test_counts_use_permissions_returned_by_the_user_query(self):
        users = []
        for user_id, role in ((1, "admin"), (2, "user"), (3, "admin")):
            users.append({"id": user_id, "display_name": "Test", "email": "test@example.test",
                          "permissions": role, "dateCreated": None, "accountStatus": "active"})
        client = self.log_in("admin")
        with patch("routes.dashboard.get_all_users", return_value=users):
            html = client.get("/dashboard").get_data(as_text=True)
        for label, count in (("Total Users", 3), ("Administrators", 2), ("Regular Users", 1)):
            self.assertRegex(html, re.escape(label) + r'</span>\s*<strong>' + str(count) + '</strong>')

    def test_failed_query_shows_one_error_and_no_user_table(self):
        client = self.log_in("admin")
        with patch("routes.dashboard.get_all_users", side_effect=Error("Database down")):
            with self.assertLogs(self.app.logger, level="ERROR") as logs:
                html = client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Unable to load the admin user list", logs.output[0])
        self.assertEqual(html.count("The user list is temporarily unavailable"), 1)
        self.assertNotIn("Some account data could not be refreshed", html)
        self.assertNotIn("data-open-add-user", html)
        self.assertNotIn('id="user-list"', html)

    def test_empty_list_is_not_reported_as_an_error(self):
        client = self.log_in("admin")
        with patch("routes.dashboard.get_all_users", return_value=[]):
            html = client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn("temporarily unavailable", html)
        self.assertIn("No users found", html)
        self.assertIn("data-open-add-user", html)

    def test_users_from_the_query_are_listed(self):
        user = {"id": 7, "display_name": "Ada Lovelace", "email": "ada@example.test",
                "permissions": "user", "dateCreated": None, "accountStatus": "active"}
        client = self.log_in("admin")
        with patch("routes.dashboard.get_all_users", return_value=[user]):
            html = client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Ada Lovelace", html)
        self.assertIn("ada@example.test", html)

    def test_regular_users_do_not_run_the_admin_query(self):
        client = self.log_in("user")
        with patch("routes.dashboard.get_all_users") as get_all_users:
            response = client.get("/dashboard")
        get_all_users.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/dashboard/settings"))


class DashboardDisplayTests(PageTestCase):
    def test_subscription_period_labels_keep_the_existing_meaning(self):
        client = self.log_in("user")
        for status, label in (("active", "Current period ends"), ("expired", "Access ends"),
                              ("cancelled", "Access ends")):
            subscription = {"plan_name": "Pro", "status": status, "current_period_end": "2027-01-01"}
            with self.subTest(status=status), \
                    patch("routes.subscription.get_user_subscription", return_value=subscription):
                html = client.get("/dashboard/subscription").get_data(as_text=True)
            self.assertIn("<dt>" + label + "</dt>", html)
            self.assertIn("2027-01-01", html)

    def test_project_status_labels_keep_original_filter_values(self):
        client = self.log_in("user")
        with patch("routes.dashboard.get_project_list", return_value=[]) as get_projects, \
                patch("routes.dashboard.count_projects", return_value=1):
            html = client.get("/dashboard/projects?status=Review+Needed").get_data(as_text=True)
        self.assertEqual(get_projects.call_args.kwargs["status"], "Review Needed")
        self.assertIn('value="Review Needed" selected>Partial result</option>', html)


class FrontendDisplayTests(PageTestCase):
    def test_manufacturers_link_to_the_correct_catalog(self):
        manufacturers = [
            {"manufacturer_id": 1, "name": "Materials", "has_machinery": False},
            {"manufacturer_id": 2, "name": "Equipment", "has_machinery": True},
        ]
        with patch("app.get_all_manufacturers", return_value=manufacturers):
            html = self.app.test_client().get("/manufacturers").get_data(as_text=True)
        self.assertIn('href="/products?manufacturer=1"', html)
        self.assertIn('href="/heavy-machinery?manufacturer=2"', html)

    def test_crew_page_shares_rates_and_initial_values_with_javascript(self):
        from services.crews import CREW_RATES, HOURS_PER_DAY
        crew = {"label": "Test crew", "days": [2, 3],
                "members": [{"role": "carpenter", "workers": 2, "days": [2, 3]}]}
        client = self.log_in("user")
        with patch("routes.crews.get_job", return_value={"result": {"crew": crew}}):
            html = client.get("/crews?job_id=test").get_data(as_text=True)
        match = re.search(r'<script id="crew-data" type="application/json">(.*?)</script>', html, re.S)
        data = json.loads(match.group(1))
        self.assertEqual(data, {"rates": CREW_RATES, "hoursPerDay": HOURS_PER_DAY, "savedCrew": crew})


class CatalogRouteTests(PageTestCase):
    def test_planner_product_lookup_failure_uses_the_database_error_page(self):
        from planning import jobs
        from tests.test_planner import RESULT

        client = self.log_in("user")
        job = jobs.submit_job(1, "catalog-error-job", {"project_type": "custom"})
        claimed = jobs.claim_job("test-worker")
        claimed["status"] = "complete"
        claimed["result"] = RESULT
        jobs.save_job(claimed, "test-worker")
        with patch("services.products.database_cursor", side_effect=Error("Test database failure")), \
                self.assertLogs(self.app.logger, level="ERROR"):
            response = client.get("/planner/jobs/" + job["id"])
        self.assertEqual(response.status_code, 503)
        self.assertIn("Service unavailable.", response.get_data(as_text=True))

    def test_product_availability_and_image_fallback_on_both_pages(self):
        for path, category in (("/products", "tools"), ("/heavy-machinery", "heavy-machinery")):
            for price, stock, label, can_buy in ((None, 5, "Unavailable", False),
                    (9, None, "Out of stock", False), (9, 0, "Out of stock", False),
                    (0, 5, "In stock", True), (9, 0.5, "In stock", False)):
                with self.subTest(path=path, price=price, stock=stock):
                    product = {"product_id": 1, "product_name": "Test product", "category": category,
                               "unit": "piece", "pack_quantity": 1, "unit_price": price,
                               "available_quantity": stock}
                    with patch("routes.products.search_products", return_value=([product], 1)):
                        html = self.app.test_client().get(path).get_data(as_text=True)
                    self.assertEqual(product["can_buy"], can_buy)
                    self.assertEqual(product["availability_label"], label)
                    self.assertEqual('class="product-cart-form"' in html, can_buy)
                    self.assertIn('data-fallback-src="/static/images/categories/placeholder.png"', html)
                    self.assertNotIn("onerror=", html)
                    self.assertIn('src="/static/js/products.js"', html)

    def test_both_pages_read_the_page_number_the_same_way(self):
        for path in ("/products", "/heavy-machinery"):
            for page_text, expected in (("", 1), ("abc", 1), ("0", 1), ("-5", 1), ("1", 1), ("3", 3)):
                with self.subTest(path=path, page=page_text), \
                        patch("routes.products.search_products", return_value=([], 36)) as search:
                    response = self.app.test_client().get(f"{path}?page={page_text}")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(search.call_args.kwargs["page"], expected)

    def test_each_page_searches_its_own_category(self):
        cases = (("/products", None), ("/products?category=tools", "tools"),
                 ("/products?category=not-a-category", None), ("/heavy-machinery", "heavy-machinery"))
        for path, expected in cases:
            with self.subTest(path=path), \
                    patch("routes.products.search_products", return_value=([], 36)) as search:
                self.app.test_client().get(path)
                self.assertEqual(search.call_args.kwargs["category_url_name"], expected)

    def test_search_text_is_trimmed_and_limited(self):
        with patch("routes.products.search_products", return_value=([], 36)) as search:
            self.app.test_client().get("/products?q=%20%20saw%20" + "x" * 300)
        self.assertEqual(len(search.call_args.kwargs["search"]), 200)
        self.assertTrue(search.call_args.kwargs["search"].startswith("saw"))

    def test_bad_manufacturer_ids_are_not_found_on_both_pages(self):
        for path in ("/products", "/heavy-machinery"):
            for manufacturer in ("0", "-2", "abc", ""):
                with self.subTest(path=path, manufacturer=manufacturer):
                    response = self.app.test_client().get(f"{path}?manufacturer={manufacturer}")
                    self.assertEqual(response.status_code, 404)
            with self.subTest(path=path, manufacturer="unknown"), \
                    patch("routes.products.get_manufacturer", return_value=None):
                self.assertEqual(self.app.test_client().get(f"{path}?manufacturer=5").status_code, 404)

    def test_database_error_still_shows_the_page_with_a_notice(self):
        for path, notice in (("/products", "Products are temporarily unavailable"),
                             ("/heavy-machinery", "Heavy machinery is temporarily unavailable")):
            with self.subTest(path=path), patch("routes.products.search_products", side_effect=Error("down")):
                with self.assertLogs(self.app.logger, level="ERROR") as logs:
                    response = self.app.test_client().get(path)
                self.assertIn("Product search failed", logs.output[0])
                self.assertEqual(response.status_code, 200)
                self.assertIn(notice, response.get_data(as_text=True))

    def test_product_page_adds_a_category_name_to_each_product(self):
        product = {"product_id": 1, "product_name": "Hammer", "category": "tools", "specification": None,
                   "sku": "H-1", "unit": "piece", "pack_quantity": 1, "unit_price": 9,
                   "available_quantity": 5, "manufacturer_name": None}
        with patch("routes.products.search_products", return_value=([dict(product)], 36)):
            html = self.app.test_client().get("/products").get_data(as_text=True)
        self.assertIn("Tools", html)
        self.assertIn("Page 1 of 36", html)
        machine = {**product, "product_name": "Crane", "category": "heavy-machinery"}
        with patch("routes.products.search_products", return_value=([machine], 1)):
            html = self.app.test_client().get("/heavy-machinery").get_data(as_text=True)
        self.assertIn("Heavy Machinery", html)
        self.assertIn("Page 1 of 1", html)

    def test_page_count_uses_the_same_filters_as_the_product_query(self):
        from services.products import search_products

        with patch("services.products.database_cursor") as database:
            cursor = database.return_value.__enter__.return_value
            cursor.fetchone.return_value = {"total": 425}
            cursor.fetchall.return_value = []
            products, total_pages = search_products(search="wood", category_url_name="lumber",
                                                   manufacturer_id=2, page=36)
        self.assertEqual(total_pages, 36)
        count_call, products_call = cursor.execute.call_args_list
        self.assertEqual(count_call.args[1], products_call.args[1][:-2])
        self.assertEqual(products_call.args[1][-2:], [12, 420])
        self.assertIn("p.category = %s", count_call.args[0])
        self.assertIn("mp.manid = %s", count_call.args[0])
        self.assertIn("p.details LIKE %s", count_call.args[0])

    def test_page_past_the_last_page_is_not_displayed(self):
        with patch("routes.products.search_products", return_value=([], 2)):
            response = self.app.test_client().get("/products?page=3")
        self.assertEqual(response.status_code, 404)


class ShoppingBlueprintTests(PageTestCase):
    def test_urls_and_endpoint_names(self):
        expected = {
            "shopping.show_cart": "/cart",
            "shopping.add_to_cart": "/cart/add",
            "shopping.update_cart": "/cart/update",
            "shopping.remove_from_cart": "/cart/remove",
            "shopping.checkout": "/checkout",
            "shopping.order_confirmation": "/order-confirmation",
        }
        with self.app.test_request_context():
            for endpoint, path in expected.items():
                self.assertEqual(url_for(endpoint), path)
            self.assertEqual(url_for("shopping.order_confirmation", order_id=5), "/order-confirmation/5")
            # The names from before the Blueprint and before the cart rename no longer exist.
            old_names = ("cart", "cart_add", "cart_update", "cart_remove", "checkout", "order_confirmation",
                         "shopping.cart", "shopping.cart_add", "shopping.cart_update", "shopping.cart_remove")
            for old_name in old_names:
                with self.assertRaises(BuildError):
                    url_for(old_name)

    def test_http_methods(self):
        methods = {}
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint.startswith("shopping."):
                methods[rule.rule] = rule.methods - {"HEAD", "OPTIONS"}
        self.assertEqual(methods["/cart"], {"GET"})
        for path in ("/cart/add", "/cart/update", "/cart/remove"):
            self.assertEqual(methods[path], {"POST"})
        self.assertEqual(methods["/checkout"], {"GET", "POST"})
        self.assertEqual(methods["/order-confirmation"], {"GET"})
        self.assertEqual(methods["/order-confirmation/<int:order_id>"], {"GET"})

    def test_signed_out_visitors_are_sent_to_log_in(self):
        for path in ("/cart", "/checkout", "/order-confirmation", "/order-confirmation/1"):
            with self.subTest(path=path):
                response = self.app.test_client().get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith("/login"))

    def test_pages_render_for_a_signed_in_user(self):
        client = self.log_in("user")
        with patch("routes.shopping.get_cart", return_value=[]):
            for path in ("/cart", "/checkout", "/order-confirmation"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 200)
        with patch("routes.shopping.get_order", return_value=None):
            self.assertEqual(client.get("/order-confirmation/9").status_code, 200)

    def test_navigation_marks_the_checkout_page_as_part_of_the_cart(self):
        client = self.log_in("user")
        with patch("routes.shopping.get_cart", return_value=[]):
            html = client.get("/checkout").get_data(as_text=True)
        self.assertIn('class="nav-cart" href="/cart" aria-current="page"', html)

    def test_unfinished_checkout_shows_the_unavailable_message(self):
        client = self.log_in("user")
        with patch("routes.shopping.get_cart", return_value=[]):
            response = client.post("/checkout", data={"csrf_token": "page-csrf"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Placing orders is not available yet", response.get_data(as_text=True))

    def test_cart_changes_need_a_csrf_token(self):
        client = self.log_in("user")
        for path in ("/cart/add", "/cart/update", "/cart/remove"):
            self.assertEqual(client.post(path, data={"product_id": 1}).status_code, 400)


class SubscriptionCheckoutTests(PageTestCase):
    form = {"plan": "yearly", "csrf_token": "page-csrf"}

    def test_display_data_is_shared_with_javascript_and_uses_configured_prices(self):
        from services.subscriptions import PRO_PLANS
        plans = {key: dict(value) for key, value in PRO_PLANS.items()}
        plans["yearly"]["amount_cents"] = 18000
        with patch("routes.subscription.PRO_PLANS", plans):
            html = self.log_in("user").get("/subscription/checkout?plan=yearly").get_data(as_text=True)
        match = re.search(r'<script id="pro-plan-data" type="application/json">(.*?)</script>', html, re.S)
        shared = json.loads(match.group(1))
        self.assertEqual(shared["yearly"]["monthly_equivalent"], "Equivalent to $15.00/month, billed yearly.")
        self.assertEqual(shared["yearly"]["savings_cents"], 5988)
        self.assertIn("$15.00/month equivalent", html)
        self.assertIn("$59.88", html)
        self.assertNotIn('class="sub-included"', html)

    def test_checkout_requires_login(self):
        response = self.app.test_client().get("/subscription/checkout")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_plan_prices_and_yearly_savings_are_exact(self):
        from services.subscriptions import PRO_PLANS
        self.assertEqual({key: plan["amount_cents"] for key, plan in PRO_PLANS.items()},
                         {"monthly": 1999, "yearly": 19200, "lifetime": 100000000})
        self.assertEqual(PRO_PLANS["yearly"]["amount_cents"] / 12, 1600)
        self.assertEqual(PRO_PLANS["monthly"]["amount_cents"] * 12 - PRO_PLANS["yearly"]["amount_cents"], 4788)
        client = self.log_in("user")
        for key, amount in (("monthly", "$19.99"), ("yearly", "$192.00"), ("lifetime", "$1,000,000.00")):
            with self.subTest(plan=key):
                html = client.get("/subscription/checkout?plan=" + key).get_data(as_text=True)
                self.assertIn(f'data-plan="{key}"', html)
                self.assertRegex(html, rf'id="summary-total">\s*{re.escape(amount)}')
        self.assertIn("Save about 20%", html)
        self.assertIn("$47.88", html)

    def test_valid_submissions_only_reach_the_payment_stub(self):
        from services.subscriptions import process_subscription_payment
        client = self.log_in("user")
        with patch("services.subscriptions.database_cursor") as database, \
                patch("routes.subscription.process_subscription_payment", wraps=process_subscription_payment) as payment, \
                patch("services.subscriptions.create_subscription") as create, \
                patch("services.subscriptions.activate_pro") as activate:
            for key in ("monthly", "yearly", "lifetime"):
                with self.subTest(plan=key):
                    response = client.post("/subscription/checkout", data={**self.form, "plan": key})
                    self.assertEqual(response.status_code, 503)
                    payment.assert_called_with(1, key)
                    html = response.get_data(as_text=True)
                    self.assertIn("Payment processing is not implemented.", html)
                    self.assertIn("Pro access was not changed.", html)
                    self.assertIn(f'data-plan="{key}"', html)
            database.assert_not_called()
            create.assert_not_called()
            activate.assert_not_called()

    def test_invalid_or_missing_plan_does_not_reach_the_payment_stub(self):
        client = self.log_in("user")
        with patch("routes.subscription.process_subscription_payment") as payment:
            for value in ("unknown", ""):
                with self.subTest(plan=value):
                    response = client.post("/subscription/checkout", data={**self.form, "plan": value})
                    self.assertEqual(response.status_code, 400)
            response = client.post("/subscription/checkout", data={"csrf_token": "page-csrf"})
            self.assertEqual(response.status_code, 400)
            payment.assert_not_called()

    def test_checkout_still_requires_csrf(self):
        client = self.log_in("user")
        with patch("routes.subscription.process_subscription_payment") as payment:
            response = client.post("/subscription/checkout", data={**self.form, "csrf_token": ""})
        self.assertEqual(response.status_code, 400)
        payment.assert_not_called()

    def test_card_fields_are_displayed_but_excluded_from_the_request(self):
        html = self.log_in("user").get("/subscription/checkout").get_data(as_text=True)
        start = html.index('id="pro-checkout-form"')
        form = html[start:html.index("</form>", start)]
        names = set(re.findall(r'name="([^"]+)"', form))
        self.assertEqual(names, {"csrf_token", "plan"})
        for field_id in ("card-first-name", "card-last-name", "card-number", "card-expiry", "card-code"):
            self.assertIn(f'id="{field_id}"', form)
        # The single "Name on card" box is now a first name box and a last name box.
        self.assertNotIn('id="card-name"', form)
        self.assertNotIn("Name on card", form)
        self.assertIn('pattern="[0-9]{3}"', form)
        self.assertIn('pattern="(0[1-9]|1[0-2]) ?/ ?[0-9]{2}"', form)
        self.assertNotIn("Billing information", html)
        self.assertNotIn("Coming soon", html)
        self.assertNotIn("PREVIEW", html)
        self.assertNotIn("Available when payments launch.", html)
        self.assertNotIn("Saved methods", html)
        self.assertNotIn("Save payment method", html)


class LoginTests(PageTestCase):
    def post_login(self, body):
        client = self.signed_out_client()
        return client.post("/login", json=body, headers={"X-CSRF-Token": "page-csrf"})

    def test_bad_requests_are_rejected_before_any_lookup(self):
        with patch("routes.auth.check_login") as check:
            self.assertEqual(self.post_login([1, 2]).status_code, 400)
            self.assertEqual(self.post_login({"email": 5, "password": "x"}).status_code, 400)
            self.assertEqual(self.post_login({"email": "a@b.co", "password": ["x"]}).status_code, 400)
            too_long = self.post_login({"email": "a@b.co", "password": "x" * 129})
            self.assertEqual(too_long.status_code, 401)
        check.assert_not_called()

    def test_email_is_trimmed_before_the_lookup(self):
        with patch("routes.auth.check_login", return_value=None) as check:
            self.post_login({"email": "  a@b.co  ", "password": "Secret123"})
        check.assert_called_once_with("a@b.co", "Secret123")

    def test_wrong_email_or_password_gets_the_generic_message(self):
        with patch("routes.auth.check_login", return_value=None):
            response = self.post_login({"email": "a@b.co", "password": "Wrong123"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Invalid email or password."})

    def test_disabled_account_is_reported_only_after_the_login_check_passes(self):
        user = {"id": 4, "firstName": "Dee", "lastName": "Sabled", "permissions": "user",
                "accountStatus": "disabled", "passkey": "x"}
        with patch("routes.auth.check_login", return_value=user):
            response = self.post_login({"email": "a@b.co", "password": "Right123"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "This account is disabled."})

    def test_good_login_starts_a_session(self):
        user = {"id": 4, "firstName": "Ann", "lastName": "Admin", "permissions": "admin",
                "accountStatus": "active", "passkey": "x"}
        client = self.signed_out_client()
        with patch("routes.auth.check_login", return_value=user):
            response = client.post("/login", json={"email": "a@b.co", "password": "Right123"},
                                   headers={"X-CSRF-Token": "page-csrf"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"redirect_url": "/dashboard"})
        with client.session_transaction() as session:
            self.assertEqual(session["user_id"], 4)
            self.assertEqual(session["display_name"], "Ann Admin")
            self.assertEqual(session["permission_level"], "admin")

    def test_database_error_is_a_503_not_a_login_failure(self):
        with patch("routes.auth.check_login", side_effect=Error("down")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.post_login({"email": "a@b.co", "password": "Right123"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "Login unavailable."})


class SignedInUserHookTests(PageTestCase):
    def signed_in_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=3, csrf_token="page-csrf", display_name="Old Name", permission_level="user")
        return client

    def test_name_and_role_are_refreshed_from_the_account(self):
        account = {"firstName": "New", "lastName": "Name", "permissions": "admin", "accountStatus": "active"}
        client = self.signed_in_client()
        with patch("routes.auth.get_account", return_value=account) as lookup:
            with patch("routes.dashboard.get_all_users", return_value=[]):
                client.get("/dashboard")
        lookup.assert_called_with(3)
        with client.session_transaction() as session:
            self.assertEqual(session["display_name"], "New Name")
            self.assertEqual(session["permission_level"], "admin")

    def test_disabled_or_deleted_accounts_are_signed_out(self):
        disabled = {"firstName": "A", "lastName": "B", "permissions": "user", "accountStatus": "disabled"}
        for account in (disabled, None):
            client = self.signed_in_client()
            with patch("routes.auth.get_account", return_value=account):
                response = client.get("/cart")
            self.assertEqual(response.status_code, 302)
            with client.session_transaction() as session:
                self.assertNotIn("user_id", session)

    def test_signed_out_visitors_and_static_files_do_not_query_accounts(self):
        with patch("routes.auth.get_account") as lookup:
            self.app.test_client().get("/home")
            self.signed_in_client().get("/static/base.css")
        lookup.assert_not_called()


class UserLookupTests(unittest.TestCase):
    """check_login and get_account with a pretend database cursor."""

    def pretend_database(self, row):
        cursor = MagicMock()
        cursor.fetchone.return_value = row
        patcher = patch("utils.users.database_cursor")
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.return_value.__enter__.return_value = cursor
        return cursor

    def test_check_login_needs_both_email_and_password(self):
        row = {"id": 1, "firstName": "A", "lastName": "B", "permissions": "user",
               "accountStatus": "active", "passkey": hash_password("Right123")}
        self.pretend_database(row)
        self.assertEqual(check_login("a@b.co", "Right123"), row)
        self.assertIsNone(check_login("a@b.co", "Wrong123"))
        self.pretend_database(None)
        self.assertIsNone(check_login("nobody@b.co", "Right123"))

    def test_check_login_hides_a_disabled_account_from_a_wrong_password(self):
        row = {"id": 1, "firstName": "A", "lastName": "B", "permissions": "user",
               "accountStatus": "disabled", "passkey": hash_password("Right123")}
        self.pretend_database(row)
        self.assertIsNone(check_login("a@b.co", "Wrong123"))
        # The right password returns the account, so the route can say it is disabled.
        self.assertEqual(check_login("a@b.co", "Right123")["accountStatus"], "disabled")

    def test_queries_use_parameters(self):
        cursor = self.pretend_database(None)
        check_login("x' OR '1'='1", "pw")
        get_account(7)
        first, second = cursor.execute.call_args_list
        self.assertEqual(first.args[1], ("x' OR '1'='1",))
        self.assertEqual(second.args[1], (7,))
        self.assertNotIn("OR '1'", first.args[0])


# A complete Bathroom Remodel form, as the browser would send it.
BATHROOM_FORM = {
    "lengthFt": "8", "widthFt": "5.5", "heightFt": "8",
    "newShower": "yes", "newToilet": "yes", "vanity": "double sink",
    "flooring": "porcelain tile", "wallTile": "shower or tub area only", "drywall": "patch and repair",
    "painting": "yes",
    "plumbing": "move or add lines", "electrical": "lighting and exhaust fan",
    "userInput": "Small hall bathroom with a window",
}


class BuildProjectTests(unittest.TestCase):
    def test_custom_project(self):
        form = MultiDict({"projectMode": "custom", "projectSize": "large", "userInput": "A pergola"})
        project = build_project(form)
        self.assertEqual(project["project_type"], "custom")
        self.assertEqual(project["description"], "A pergola")
        self.assertEqual(project["project_mode"], "custom")
        self.assertEqual(project["project_size"], "large")
        self.assertIsNone(project["project_template"])

    def test_template_project_takes_its_size_from_the_template(self):
        form = MultiDict({"projectMode": "template", "projectTemplate": "bathroom_remodel", "projectSize": "small",
                          **BATHROOM_FORM})
        project = build_project(form)
        self.assertEqual(project["project_type"], "bathroom_remodel")
        self.assertEqual(project["project_size"], "medium")
        self.assertEqual(project["project_template"], "bathroom_remodel")

    def test_bad_forms_are_rejected_with_a_message(self):
        bad_forms = (
            ({}, "Choose a template or custom project."),
            ({"projectMode": "other"}, "Choose a template or custom project."),
            ({"projectMode": "template", "projectTemplate": "castle"}, "Choose a valid project template."),
            ({"projectMode": "custom", "projectSize": "huge", "userInput": "x"}, "Choose a valid project size."),
            ({"projectMode": "custom", "projectSize": "small", "userInput": "  "}, "Describe your project first."),
        )
        for fields, message in bad_forms:
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                build_project(MultiDict(fields))

    def test_the_planner_route_uses_this_function(self):
        import routes.planner
        self.assertIs(routes.planner.build_project, build_project)


class TemplateFormTests(PageTestCase):
    forms = {
        "birdhouse": {"widthInches": "6.25", "depthInches": "6", "heightInches": "8"},
        "shed": {"lengthFt": "12", "widthFt": "10"},
        "bathroom_remodel": {"lengthFt": "8", "widthFt": "5.5"},
        "residential_building": {"footprintSqFt": "1200", "bedrooms": "3", "bathrooms": "2"},
        "commercial_building": {"footprintSqFt": "2400", "rooms": "6"},
    }

    def test_every_template_submits_with_just_its_essential_fields(self):
        client = self.log_in("user")
        for template_id, fields in self.forms.items():
            with self.subTest(template=template_id):
                response = client.get(f"/planner?projectMode=template&projectTemplate={template_id}")
                self.assertEqual(response.status_code, 200)
                with patch("routes.planner.submit_job", return_value={"id": "test-job"}) as submit:
                    response = client.post("/planner/jobs", data={
                        "projectMode": "template", "projectTemplate": template_id,
                        "csrf_token": "page-csrf", "submissionKey": "template-key-1", **fields,
                    })
                self.assertEqual(response.status_code, 303)
                user_id, key, project, tier = submit.call_args.args
                self.assertEqual((user_id, key, tier), (1, "template-key-1", "fast"))
                self.assertEqual(project["project_type"], template_id)
                self.assertEqual(project["project_template"], template_id)
                self.assertEqual(project["project_size"], PROJECT_TEMPLATES[template_id]["size"])
                self.assertIsNone(project["description"])
                json.dumps(project, allow_nan=False)

    def test_missing_or_blank_optional_numbers_use_the_displayed_defaults(self):
        cases = (("birdhouse", "entranceHoleInches", "entrance_hole_diameter_inches", 1.5),
                 ("shed", "heightFt", "height_ft", 8),
                 ("bathroom_remodel", "heightFt", "height_ft", 8),
                 ("residential_building", "floors", "floors", 1),
                 ("commercial_building", "floors", "floors", 1))
        for template_id, name, key, expected in cases:
            for value in (None, ""):
                with self.subTest(template=template_id, value=value):
                    fields = dict(self.forms[template_id])
                    if value is not None:
                        fields[name] = value
                    project = build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id, **fields}))
                    self.assertEqual(project.get("dimensions", project).get(key, project.get(key)), expected)

    def test_bad_numbers_and_missing_dimensions_are_still_rejected(self):
        for template_id, fields in self.forms.items():
            for name in fields:
                for value in ("", "abc", "nan", "inf", "-1"):
                    with self.subTest(template=template_id, field=name, value=value), self.assertRaises(ValueError):
                        build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id,
                                                 **fields, name: value}))
        for template_id in ("residential_building", "commercial_building"):
            with self.subTest(template=template_id), self.assertRaisesRegex(ValueError, "whole number"):
                build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id,
                                         **self.forms[template_id], "floors": "1.5"}))

    def test_optional_choices_and_notes_reach_the_project_data(self):
        cases = {
            "birdhouse": ({"perch": "yes", "color": "blue", "entranceHoleInches": "2"},
                          {"perch": True, "color": "blue", "entrance_hole_diameter_inches": 2}),
            "shed": ({"ramp": "yes", "window": "yes", "ac": "yes", "lighting": "yes", "heightFt": "9"},
                     {"ramp": True, "window": True, "air_conditioning": True, "lighting": True}),
            "bathroom_remodel": ({"newBathtub": "yes", "painting": "yes", "finishing": "yes"},
                                 {"new_bathtub": True, "painting": True, "finishing_trim_and_accessories": True}),
            "residential_building": ({"floors": "2", "bedrooms": "4", "bathrooms": "3"},
                                     {"floors": 2, "bedrooms": 4, "bathrooms": 3}),
            "commercial_building": ({"floors": "3", "rooms": "9", "elevator": "yes"},
                                    {"floors": 3, "rooms": 9, "elevator": True}),
        }
        for template_id, (options, expected) in cases.items():
            with self.subTest(template=template_id):
                project = build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id,
                                                 **self.forms[template_id], **options, "userInput": "  Use cedar  "}))
                for key, value in expected.items():
                    self.assertEqual(project[key], value)
                self.assertEqual(project["description"], "Use cedar")

    def test_unchecked_extras_do_not_add_work(self):
        cases = {"birdhouse": ("perch",), "shed": ("ramp", "window", "air_conditioning", "lighting"),
                 "bathroom_remodel": ("new_shower", "new_bathtub", "new_toilet", "painting", "finishing_trim_and_accessories"),
                 "commercial_building": ("elevator",)}
        for template_id, keys in cases.items():
            project = build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id, **self.forms[template_id]}))
            for key in keys:
                with self.subTest(template=template_id, field=key):
                    self.assertIs(project[key], False)

    def test_all_templates_pass_their_project_data_through_the_ai_workflow(self):
        from planning import workflow
        material = {"material_name": "Wood board", "specification": "Cedar", "quantity": 2,
                    "unit": "piece", "notes": "Two boards for this test estimate.", "product_id": None}
        crew = {"days": [1, 2], "members": [{"role": "general", "workers": 1, "days": [1, 2]}]}
        requests = []

        def fake_ai(model, prompt, reasoning, instructions, schema, tokens):
            requests.append(json.loads(prompt)["project"])
            if schema["title"] == "Specification":
                return json.dumps({"details": ["Use the project measurements"], "questions": []})
            if schema["title"] == "DraftEstimate":
                return json.dumps({"materials": [material]})
            return json.dumps({"summary": "Test estimate", "notes": [], "materials": [material], "crew": crew})

        for template_id, fields in self.forms.items():
            with self.subTest(template=template_id):
                requests.clear()
                project = build_project(MultiDict({"projectMode": "template", "projectTemplate": template_id, **fields}))
                job = {"tier": "fast", "owner": "1", "project": project, "answers": [],
                       "stages": {"interpreter": "pending", "planner": "pending", "auditor": "pending"}}
                with patch.object(workflow, "ask_model", side_effect=fake_ai), patch.object(workflow, "get_planner_catalog", return_value=[]):
                    workflow.run_workflow(job, lambda saved: None)
                self.assertEqual(requests, [project, project, project])
                self.assertEqual(job["status"], "complete")
                self.assertEqual(job["result"]["materials"][0]["quantity"], 2)
                self.assertEqual(job["result"]["crew"]["members"][0]["role"], "general")

    def test_every_template_retains_typed_fields_on_a_validation_error(self):
        client = self.log_in("user")
        for template_id, fields in self.forms.items():
            name = next(iter(fields))
            with self.subTest(template=template_id), patch("routes.planner.submit_job") as submit:
                response = client.post("/planner/jobs", data={
                    "projectMode": "template", "projectTemplate": template_id, **fields,
                    name: "0", "userInput": "Keep my notes", "csrf_token": "page-csrf",
                })
                self.assertEqual(response.status_code, 400)
                submit.assert_not_called()
                html = response.get_data(as_text=True)
                start = html.index(f'id="{template_id}-questions-step"')
                section = html[start:html.index("</section>", start)]
                self.assertNotIn("hidden>", section[:section.index("<form")])
                self.assertIn('value="0"', section)
                self.assertIn("Keep my notes", section)


class BathroomRemodelTests(PageTestCase):
    def test_form_becomes_project_data_for_the_planner(self):
        project = build_project(MultiDict({"projectMode": "template", "projectTemplate": "bathroom_remodel",
                                           **BATHROOM_FORM}))
        self.assertEqual(project["project_type"], "bathroom_remodel")
        self.assertEqual(project["dimensions"], {"length_ft": 8.0, "width_ft": 5.5, "height_ft": 8.0})
        self.assertEqual(project["floor_area_sq_ft"], 44.0)
        self.assertEqual(project["new_shower"], True)
        self.assertEqual(project["new_bathtub"], False)
        self.assertEqual(project["new_toilet"], True)
        self.assertEqual(project["vanity"], "double sink")
        self.assertEqual(project["flooring"], "porcelain tile")
        self.assertEqual(project["wall_tile"], "shower or tub area only")
        self.assertEqual(project["drywall"], "patch and repair")
        self.assertEqual(project["waterproofing"], True)
        self.assertEqual(project["painting"], True)
        self.assertEqual(project["finishing_trim_and_accessories"], False)
        self.assertEqual(project["plumbing"], "move or add lines")
        self.assertEqual(project["electrical"], "lighting and exhaust fan")
        self.assertEqual(project["description"], "Small hall bathroom with a window")
        self.assertEqual(project["project_mode"], "template")

    def test_description_is_optional(self):
        form = dict(BATHROOM_FORM, userInput="  ")
        project = build_project(MultiDict({"projectMode": "template", "projectTemplate": "bathroom_remodel", **form}))
        self.assertIsNone(project["description"])

    def test_waterproofing_follows_the_wet_area_work(self):
        self.assertFalse(self.build(newShower="no", newBathtub="no", wallTile="none")["waterproofing"])
        for changes in ({"newShower": "yes"}, {"newBathtub": "yes"}, {"wallTile": "all walls"}):
            with self.subTest(changes=changes):
                fields = {"newShower": "no", "newBathtub": "no", "wallTile": "none", **changes}
                self.assertTrue(self.build(**fields)["waterproofing"])

    def build(self, **changes):
        form = dict(BATHROOM_FORM, **changes)
        return build_project(MultiDict({"projectMode": "template", "projectTemplate": "bathroom_remodel", **form}))

    def test_sizes_must_be_numbers_that_are_big_enough(self):
        bad_sizes = (("lengthFt", "", "valid number for length"), ("lengthFt", "abc", "valid number for length"),
                     ("lengthFt", "2", "Length must be at least 3"), ("widthFt", "2.5", "Width must be at least 3"),
                     ("widthFt", "nan", "valid number for width"), ("heightFt", "5", "Ceiling height must be at least 6"),
                     ("heightFt", "inf", "valid number for ceiling height"))
        for field, value, message in bad_sizes:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, message):
                self.build(**{field: value})
        self.assertEqual(self.build(lengthFt="3", widthFt="3", heightFt="6")["floor_area_sq_ft"], 9.0)

    def test_choices_have_defaults_but_unknown_values_are_rejected(self):
        for field in ("newShower", "newBathtub", "newToilet", "vanity", "flooring", "wallTile", "drywall",
                      "painting", "finishing", "plumbing", "electrical"):
            with self.subTest(field=field, problem="missing"):
                form = dict(BATHROOM_FORM)
                form.pop(field, None)
                build_project(MultiDict({"projectMode": "template", "projectTemplate": "bathroom_remodel", **form}))
            with self.subTest(field=field, problem="invented"), self.assertRaisesRegex(ValueError, "Choose a valid option"):
                self.build(**{field: "marble throne"})

    def test_the_form_page_offers_exactly_the_choices_the_backend_accepts(self):
        html = self.app.test_client().get("/planner?projectMode=template&projectTemplate=bathroom_remodel").get_data(as_text=True)
        start = html.index('id="bathroom_remodel-questions-step"')
        form = html[start:html.index("</section>", start)]
        # Every field the page sends must be one the backend reads, and every option must be accepted.
        names = set(re.findall(r'name="(\w+)"', form))
        self.assertEqual(names, {"projectMode", "projectTemplate", "lengthFt", "widthFt", "heightFt", "newShower",
                                 "newBathtub", "newToilet", "vanity", "flooring", "wallTile", "drywall",
                                 "painting", "finishing", "plumbing", "electrical", "userInput",
                                 "csrf_token", "submissionKey", "planType"})
        for select_name in ("vanity", "flooring", "wallTile", "drywall", "plumbing", "electrical"):
            block = form[form.index(f'name="{select_name}"'):]
            block = block[:block.index("</select>")]
            for option in re.findall(r'<option value="([^"]*)"', block):
                with self.subTest(select=select_name, option=option):
                    self.build(**{select_name: option})
        for checkbox_name in ("newShower", "newBathtub", "newToilet", "painting", "finishing"):
            values = re.findall(rf'type="checkbox" name="{checkbox_name}" value="(\w+)"', form)
            self.assertEqual(values, ["yes"])

    def test_every_template_has_a_card_and_matching_form(self):
        self.assertEqual(list(PROJECT_TEMPLATES),
                         ["birdhouse", "shed", "bathroom_remodel", "residential_building", "commercial_building"])
        self.assertEqual(PROJECT_TEMPLATES["bathroom_remodel"]["title"], "Bathroom Remodel")
        self.assertEqual(PROJECT_TEMPLATES["bathroom_remodel"]["size"], "medium")
        html = self.app.test_client().get("/planner").get_data(as_text=True)
        self.assertIn('data-template="bathroom_remodel"', html)
        self.assertIn("<strong>Bathroom Remodel</strong>", html)
        self.assertIn("Medium project", html)
        cards = re.findall(r'data-template="(\w+)"', html)
        self.assertEqual(cards, list(PROJECT_TEMPLATES))
        # planner.js opens "<template>-questions-step", so every template needs that section.
        for key in PROJECT_TEMPLATES:
            self.assertIn(f'id="{key}-questions-step"', html)

    def test_the_page_keeps_what_the_user_typed_after_an_error(self):
        client = self.log_in("user")
        form = dict(BATHROOM_FORM, lengthFt="2", flooring="vinyl plank", newShower="no", userInput="Keep this text")
        response = client.post("/planner/jobs", data={"csrf_token": "page-csrf", "submissionKey": "k" * 12,
                                                      "planType": "fast", "projectMode": "template",
                                                      "projectTemplate": "bathroom_remodel", **form})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Length must be at least 3.", html)
        self.assertRegex(html, r'<option value="vinyl plank"\s+selected')
        self.assertNotRegex(html, r'name="newShower" value="yes"\s+checked')
        self.assertIn("Keep this text", html)
        self.assertIn('value="2"', html)
        # The form is still the open step.
        self.assertNotRegex(html, r'<section\s+id="bathroom_remodel-questions-step"[^>]*hidden')

    def test_submitting_queues_the_job_with_the_bathroom_project(self):
        client = self.log_in("user")
        with patch("routes.planner.submit_job", return_value={"id": "bath-job"}) as submit:
            response = client.post("/planner/jobs", data={"csrf_token": "page-csrf", "submissionKey": "k" * 12,
                                                          "planType": "standard", "projectMode": "template",
                                                          "projectTemplate": "bathroom_remodel", **BATHROOM_FORM})
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith("/planner/jobs/bath-job"))
        user_id, key, project, tier = submit.call_args.args
        self.assertEqual((user_id, tier), (1, "standard"))
        self.assertEqual(project["project_type"], "bathroom_remodel")
        self.assertEqual(project["project_size"], "medium")

    def test_the_planner_receives_the_bathroom_choices_and_asks_for_the_trades(self):
        from planning import ai_config, workflow
        project = self.build()
        job = {"tier": "fast", "owner": "1", "project": project, "answers": [],
               "stages": {"interpreter": "pending", "planner": "pending", "auditor": "pending"}}
        sent = {}
        crew = {"days": [4, 6], "members": [{"role": "plumber", "workers": 1, "days": [1, 2]},
                                            {"role": "electrician", "workers": 1, "days": [1, 1]},
                                            {"role": "drywall", "workers": 1, "days": [1, 2]},
                                            {"role": "mason", "workers": 1, "days": [2, 3]},
                                            {"role": "painter", "workers": 1, "days": [1, 1]}]}
        material = {"material_name": "Porcelain floor tile", "specification": "12 x 24 in", "quantity": 48,
                    "unit": "sq_ft", "notes": "44 sq ft plus 10% waste, rounded up.", "product_id": None}

        def fake_ai(model, prompt, reasoning, instructions, schema, tokens):
            request = json.loads(prompt)
            sent[schema["title"]] = request
            if schema["title"] == "Specification":
                return json.dumps({"details": ["Hall bathroom"], "questions": []})
            if schema["title"] == "DraftEstimate":
                return json.dumps({"materials": [material]})
            return json.dumps({"summary": "Bathroom remodel", "notes": [], "materials": [material], "crew": crew})

        with patch.object(workflow, "ask_model", side_effect=fake_ai):
            with patch.object(workflow, "get_planner_catalog", return_value=[]):
                workflow.run_workflow(job, lambda saved: None)
        self.assertEqual(job["status"], "complete")
        # The AI is given every bathroom choice, in words it can read.
        for step in ("Specification", "DraftEstimate", "AuditedEstimate"):
            self.assertEqual(sent[step]["project"], project)
        self.assertEqual(sent["Specification"]["project"]["plumbing"], "move or add lines")
        self.assertEqual(sent["Specification"]["project"]["floor_area_sq_ft"], 44.0)
        # The auditor can choose any of the trades a remodel needs.
        roles = set(sent["AuditedEstimate"]["available_crew_roles"])
        self.assertTrue({"plumber", "electrician", "drywall", "mason", "painter", "carpenter"} <= roles)
        self.assertEqual({member["role"] for member in job["result"]["crew"]["members"]},
                         {"plumber", "electrician", "drywall", "mason", "painter"})

    def test_a_queued_bathroom_job_is_stored_and_shown_with_its_title(self):
        import tempfile
        from pathlib import Path
        from planning import jobs
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(jobs, "database_path", return_value=Path(folder) / "jobs.sqlite3"):
                project = self.build()
                job = jobs.submit_job("7", "bathroom-key-1", project, "fast")
                stored = jobs.get_job(job["id"], "7")
        self.assertEqual(stored["status"], "queued")
        self.assertEqual(stored["project"], project)
        client = self.log_in("user")
        page_job = dict(stored, owner="1", stages={}, result=None, questions=[], answers=[], error=None)
        with patch("routes.planner.get_job", return_value=page_job):
            with patch("routes.planner.get_project_saved_from_job", return_value=None):
                html = client.get("/planner/jobs/" + job["id"]).get_data(as_text=True)
        self.assertIn("Bathroom Remodel plan", html)
        for label in ("Floor area sq ft", "Plumbing", "Electrical", "Wall tile", "New shower"):
            self.assertIn(label, html)


class PlannerAddToCartTests(PageTestCase):
    def material(self, product_id, name, quantity, can_add=True):
        row = {"material_name": name, "quantity": quantity, "can_add": can_add, "product": None}
        if can_add:
            row["product"] = {"product_id": product_id, "product_name": name}
        return row

    def test_partial_success_is_reported_in_three_lists(self):
        from services.cart import add_materials_to_cart
        rows = [self.material(1, "Nails", 2.2), self.material(1, "Nails", 1.1),
                self.material(2, "Boards", 5), self.material(3, "Glue", 1),
                self.material(None, "Paint", 1, can_add=False), self.material(None, "Tape", 1, can_add=False)]

        def fake_add_item(user_id, product_id, quantity):
            if product_id == 2:
                raise ValueError("Only 3 piece are currently available.")
            return {1: "Nails", 3: "Glue"}[product_id]

        with patch("services.cart.add_item", side_effect=fake_add_item) as add_item:
            result = add_materials_to_cart(9, rows)
        self.assertEqual(result, {"added": ["Nails", "Glue"],
                                  "failed": ["Boards (Only 3 piece are currently available.)"],
                                  "skipped": 2})
        # Two Nails rows are merged, then rounded up once: 2.2 + 1.1 = 3.3 -> 4.
        calls = [call.args for call in add_item.call_args_list]
        self.assertEqual(calls, [(9, 1, 4), (9, 2, 5), (9, 3, 1)])
        for call in calls:
            self.assertIsInstance(call[2], int)

    def post_to_the_route(self, materials, result, form=None):
        client = self.log_in("user")
        job = {"result": {"materials": []}}
        with patch("routes.planner.get_job", return_value=job):
            with patch("routes.planner.get_plan_materials", return_value=materials):
                with patch("routes.planner.add_materials_to_cart", return_value=result) as service:
                    data = {"csrf_token": "page-csrf"}
                    data.update(form or {})
                    response = client.post("/planner/jobs/abc/cart", data=data)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/planner/jobs/abc", response.location)
        with client.session_transaction() as session:
            return service, session["_flashes"]

    def test_route_turns_the_results_into_flash_messages(self):
        rows = [self.material(1, "Nails", 1), self.material(2, "Boards", 1)]
        result = {"added": ["Nails"], "failed": ["Boards (Out of stock)"], "skipped": 2}
        service, flashes = self.post_to_the_route(rows, result)
        self.assertEqual(service.call_args.args, (1, rows))
        self.assertEqual(flashes[0], ("success", "Added Nails to your cart."))
        self.assertEqual(flashes[1], ("error", "Could not add to your cart: Boards (Out of stock)."))
        self.assertEqual(flashes[2][0], "info")
        self.assertIn("2 materials were not added", flashes[2][1])

    def test_several_products_are_counted(self):
        result = {"added": ["A", "B", "C"], "failed": [], "skipped": 1}
        _, flashes = self.post_to_the_route([self.material(1, "A", 1)], result)
        self.assertEqual(flashes[0], ("success", "Added 3 products to your cart."))
        self.assertIn("1 material was not added", flashes[1][1])

    def test_one_chosen_material_is_sent_on_its_own(self):
        rows = [self.material(1, "Nails", 1), self.material(2, "Boards", 1)]
        result = {"added": ["Boards"], "failed": [], "skipped": 0}
        service, _ = self.post_to_the_route(rows, result, form={"material": "1"})
        self.assertEqual(service.call_args.args[1], [rows[1]])

    def test_a_material_number_that_does_not_exist_adds_nothing(self):
        result = {"added": [], "failed": [], "skipped": 0}
        service, flashes = self.post_to_the_route([self.material(1, "Nails", 1)], result, form={"material": "7"})
        self.assertEqual(service.call_args.args[1], [])
        self.assertEqual(flashes, [("error", "There was nothing to add to your cart.")])

    def test_someone_elses_plan_is_not_found_and_nothing_is_added(self):
        client = self.log_in("user")
        with patch("routes.planner.get_job", return_value=None):
            with patch("routes.planner.add_materials_to_cart") as service:
                response = client.post("/planner/jobs/abc/cart", data={"csrf_token": "page-csrf"})
        self.assertEqual(response.status_code, 404)
        service.assert_not_called()


class ProjectListFilterTests(PageTestCase):
    def test_search_and_status_go_to_the_service_and_the_total_ignores_them(self):
        client = self.log_in("user")
        project = {"id": "deck-job", "saved_project_id": 5, "saved_name": "Deck",
                   "project": {"description": "Deck", "project_type": "custom"},
                   "tier": "fast", "status": "complete", "result": {"materials": []}, "updated": 1}
        with patch("routes.dashboard.get_project_list", return_value=[project]) as projects:
            with patch("routes.dashboard.count_projects", return_value=12) as count:
                html = client.get("/dashboard/projects?q=%20deck%20&status=Ready").get_data(as_text=True)
        projects.assert_called_once_with(1, search="deck", status="Ready")
        count.assert_called_once_with(1)
        self.assertIn("Deck", html)
        self.assertNotIn("No projects match this search", html)

    def test_an_unknown_status_is_ignored_but_still_shown_as_typed(self):
        client = self.log_in("user")
        with patch("routes.dashboard.get_project_list", return_value=[]) as projects:
            with patch("routes.dashboard.count_projects", return_value=2):
                html = client.get("/dashboard/projects?status=Nonsense").get_data(as_text=True)
        projects.assert_called_once_with(1, search="", status="")
        self.assertIn("No projects match this search", html)

    def test_no_match_is_different_from_no_projects(self):
        client = self.log_in("user")
        with patch("routes.dashboard.get_project_list", return_value=[]):
            with patch("routes.dashboard.count_projects", return_value=4):
                with_projects = client.get("/dashboard/projects?q=zzz").get_data(as_text=True)
        with patch("routes.dashboard.get_project_list", return_value=[]):
            with patch("routes.dashboard.count_projects", return_value=0):
                without_projects = client.get("/dashboard/projects").get_data(as_text=True)
        self.assertIn("No projects match this search", with_projects)
        self.assertIn("No saved projects yet", without_projects)
        self.assertNotIn("No projects match this search", without_projects)

    def test_unavailable_service_still_shows_the_unavailable_page(self):
        client = self.log_in("user")
        with patch("routes.dashboard.get_project_list", return_value=None):
            response = client.get("/dashboard/projects?q=deck")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Projects unavailable.", response.get_data(as_text=True))

    def test_a_signed_out_visitor_is_sent_to_log_in(self):
        response = self.app.test_client().get("/dashboard/projects")
        self.assertEqual(response.status_code, 302)


class UserHelperTests(unittest.TestCase):
    def test_email_check(self):
        for good in ("a@b.co", "first.last@example.com", "x@y.z.org"):
            with self.subTest(email=good):
                self.assertTrue(looks_like_email(good))
        for bad in ("", "plain", "@example.com", "a@", "a@example", "a@b@c.com", "a b@example.com",
                    "a@exa mple.com", "a@@b.com"):
            with self.subTest(email=bad):
                self.assertFalse(looks_like_email(bad))

    def test_full_name(self):
        self.assertEqual(full_name("Ada", "Lovelace"), "Ada Lovelace")
        self.assertEqual(full_name("Madonna", ""), "Madonna")
        self.assertEqual(full_name(" Ada", "Lovelace "), "Ada Lovelace")


if __name__ == "__main__":
    unittest.main()
