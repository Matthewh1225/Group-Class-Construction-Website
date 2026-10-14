import ast
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from flask import Flask, render_template, session
from mysql.connector import Error, IntegrityError

import routes.dashboard as dashboard_routes


class AdminDashboardTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / "pages"))
        self.app.config.update(TESTING=True, SECRET_KEY="admin-test")
        self.app.register_blueprint(dashboard_routes.dashboard_bp)
        for endpoint in ["home", "reviews", "manufacturers", "auth.login",
                         "auth.logout", "products.products", "planner.planner", "planner.planning_history", "cart"]:
            self.app.add_url_rule("/" + endpoint, endpoint, lambda: "")
        self.users = [
            {"id": 1, "username": "Admin", "email": "admin@example.test",
             "permission_level": "admin", "created_at": "2026-10-01 12:00:00"},
            {"id": 2, "username": "Student", "email": "student@example.test",
             "permission_level": "user", "created_at": None},
        ]
        self.current_user = self.users[0]
        test = self

        class Cursor:
            def execute(self, *_args, **_kwargs):
                pass

            def fetchone(self):
                return test.current_user

            def fetchall(self):
                return test.users

        @contextmanager
        def fake_cursor():
            yield Cursor()

        self.database_patch = patch.object(dashboard_routes, "database_cursor", fake_cursor)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def test_render_counts_and_current_user(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("User Management", html)
        self.assertIn("<strong>2</strong>", html)
        self.assertEqual(html.count("<strong>1</strong>"), 2)
        self.assertIn('class="admin-you">You', html)
        self.assertNotIn('action="/dashboard/users/1/delete"', html)
        self.assertIn('action="/dashboard/users/2/delete"', html)

    def test_missing_account_clears_session_and_redirects(self):
        self.current_user = None
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/auth.login"))
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_database_outage_blocks_actions_without_clearing_login(self):
        with patch.object(dashboard_routes, "database_cursor", side_effect=Error("Test outage")), patch.object(dashboard_routes, "create_user") as create, patch.object(dashboard_routes, "delete_user_record") as delete, self.assertLogs(self.app.logger, level="ERROR"):
            self.assertEqual(self.client.get("/dashboard").status_code, 503)
            self.assertEqual(self.client.post("/dashboard").status_code, 503)
            self.assertEqual(self.client.post("/dashboard/users/2/delete").status_code, 503)
            create.assert_not_called()
            delete.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 1)

    def test_admin_user_list_database_failure_has_unavailable_response(self):
        account_lookup = dashboard_routes.database_cursor()
        with patch.object(dashboard_routes, "database_cursor", side_effect=[account_lookup, Error("Test outage")]), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_data(as_text=True), "Dashboard is temporarily unavailable.")

    def test_regular_user_cannot_create_or_delete_accounts(self):
        self.current_user = self.users[1]
        with patch.object(dashboard_routes, "create_user") as create, patch.object(dashboard_routes, "delete_user_record") as delete:
            self.assertEqual(self.client.post("/dashboard").status_code, 403)
            self.assertEqual(self.client.post("/dashboard/users/2/delete").status_code, 403)
            create.assert_not_called()
            delete.assert_not_called()

    def test_regular_user_keeps_user_dashboard(self):
        self.current_user = self.users[1]
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Welcome back", html)
        self.assertIn("My Projects", html)
        self.assertNotIn('id="admin-workspace"', html)
        self.assertEqual(self.client.get("/dashboard/settings").status_code, 200)

    def test_logged_out_requests_do_not_mutate_accounts(self):
        with self.client.session_transaction() as session:
            session.clear()
        with patch.object(dashboard_routes, "create_user") as create, patch.object(dashboard_routes, "delete_user_record") as delete:
            self.assertEqual(self.client.get("/dashboard").status_code, 302)
            self.assertEqual(self.client.post("/dashboard").status_code, 302)
            self.assertEqual(self.client.post("/dashboard/users/2/delete").status_code, 403)
            create.assert_not_called()
            delete.assert_not_called()

    def test_account_creation_uses_existing_operation(self):
        data = {"username": "New user", "email": "new@example.test", "password": "Ab1!", "confirm_password": "Ab1!", "permission_level": "user"}
        with patch.object(dashboard_routes, "create_user") as create:
            response = self.client.post("/dashboard", data=data)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(dict(create.call_args.args[0]), data)
            self.assertEqual(create.call_args.args[1], "user")
            html = self.client.get("/dashboard").get_data(as_text=True)
            self.assertIn("User created successfully.", html)

    def test_duplicate_account_has_error_feedback(self):
        with patch.object(dashboard_routes, "create_user", side_effect=IntegrityError()):
            response = self.client.post("/dashboard", data={"username": "Student"}, follow_redirects=True)
            self.assertIn("That username or email is already in use.", response.get_data(as_text=True))
            self.assertNotIn("User created successfully.", response.get_data(as_text=True))

    def test_self_deletion_is_blocked(self):
        with patch.object(dashboard_routes, "delete_user_record") as delete:
            response = self.client.post("/dashboard/users/1/delete", follow_redirects=True)
            delete.assert_not_called()
            self.assertIn("You cannot delete your own account.", response.get_data(as_text=True))

    def test_deletion_uses_selected_id(self):
        with patch.object(dashboard_routes, "delete_user_record", return_value=True) as delete:
            response = self.client.post("/dashboard/users/2/delete", follow_redirects=True)
            delete.assert_called_once_with(2)
            self.assertIn("User deleted successfully.", response.get_data(as_text=True))

    def test_deletion_failure_has_error_feedback(self):
        with patch.object(dashboard_routes, "delete_user_record", side_effect=Error()):
            response = self.client.post("/dashboard/users/2/delete", follow_redirects=True)
            self.assertIn("The user could not be deleted.", response.get_data(as_text=True))

    def test_user_content_is_escaped(self):
        self.users[1]["username"] = '<img src=x onerror="alert(1)">'
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn('<img src=x onerror="alert(1)">', html)
        self.assertIn("&lt;img", html)

    def test_new_admin_services_are_stubs(self):
        path = Path(__file__).resolve().parents[1] / "services" / "admin.py"
        functions = [node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(len(functions), 4)
        for function in functions:
            self.assertIsNotNone(ast.get_docstring(function))
            self.assertEqual(len(function.body), 2)
            self.assertIsInstance(function.body[1], ast.Pass)

    def test_dashboard_pages_use_only_dashboard_navigation(self):
        self.current_user = self.users[1]
        pages = {
            "/dashboard": "Overview",
            "/dashboard/projects": "My Projects",
            "/dashboard/projects/2": "My Projects",
            "/dashboard/material-lists": "Material Lists",
            "/dashboard/projects/2/materials": "Material Lists",
            "/dashboard/orders": "Orders",
            "/dashboard/orders/2": "Orders",
            "/dashboard/settings": "Settings",
        }
        for path, section in pages.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertNotIn('class="navbar"', html)
                self.assertNotIn("js/navbar.js", html)
                self.assertIn('id="dashboard-sidebar"', html)
                self.assertIn(f'id="dashboard-header-section">{section}</span>', html)
                self.assertEqual(html.count('aria-current="page"'), 1)
                self.assertIn("Back to Store", html)
                self.assertIn('action="/auth.logout"', html)

    def test_admin_has_compact_header_and_admin_sidebar(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn('class="navbar"', html)
        self.assertIn('data-admin-nav="users"', html)
        self.assertIn('id="dashboard-header-section">Users</span>', html)
        self.assertIn('action="/auth.logout"', html)

    def test_storefront_retains_original_navigation(self):
        with self.app.test_request_context("/home"):
            html = render_template("home.html")
            self.assertIn('class="navbar"', html)
            self.assertIn("js/navbar.js", html)
            self.assertNotIn('id="dashboard-sidebar"', html)

    def test_header_can_use_existing_cart_context(self):
        with self.app.test_request_context("/dashboard"):
            session["user_id"] = 1
            html = render_template(
                "dashboard/overview.html", username="Admin", recent_projects=[],
                project_count=None, material_list_count=None,
                cart_url="/cart-test", cart_count=0,
            )
            self.assertIn('href="/cart-test" aria-label="Shopping cart"', html)
            self.assertIn('class="dashboard-cart-count">0</span>', html)


if __name__ == "__main__":
    unittest.main()
