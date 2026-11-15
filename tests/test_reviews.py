import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from mysql.connector import Error

from routes.reviews import reviews
from services.reviews import validate_review
from utils.csrf import check_csrf, csrf_token


class ReviewValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = {"review_type": "general", "rating": "5", "title": "Great experience",
                     "body": "The materials arrived on time."}

    def test_all_five_star_ratings_are_accepted(self):
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                self.assertEqual(validate_review(dict(self.data, rating=str(rating)))["rating"], rating)

    def test_invalid_ratings_are_rejected(self):
        for rating in ("", "0", "6", "1.5", "five", "-1"):
            with self.subTest(rating=rating), self.assertRaises(ValueError):
                validate_review(dict(self.data, rating=rating))

    def test_product_reviews_require_valid_product_id(self):
        for product_id in ("", "0", "-1", "not a product"):
            with self.subTest(product_id=product_id), self.assertRaises(ValueError):
                validate_review(dict(self.data, review_type="product", product_id=product_id))
        self.assertEqual(validate_review(dict(self.data, review_type="product", product_id="42"))["product_id"], 42)

    def test_general_review_discards_product_id(self):
        self.assertIsNone(validate_review(dict(self.data, product_id="42"))["product_id"])

    def test_text_limits_and_whitespace(self):
        for fields in ({"title": " "}, {"title": "x" * 101}, {"body": " " * 20},
                       {"body": "too short"}, {"body": "x" * 2001}, {"review_type": "unknown"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_review(dict(self.data, **fields))
        result = validate_review(dict(self.data, title="  Useful review  ", body="  " + "x" * 2000 + "  "))
        self.assertEqual(result["title"], "Useful review")
        self.assertEqual(len(result["body"]), 2000)


class ReviewRequestTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / "pages"), static_folder=str(root / "static"))
        self.app.config.update(TESTING=True, SECRET_KEY="review-test-secret")
        self.app.before_request(check_csrf)
        self.app.jinja_env.globals["csrf_token"] = csrf_token
        self.app.add_url_rule("/reviews", view_func=reviews, methods=["GET", "POST"])
        # The shared layout links to other areas of the website.
        for endpoint in ("home", "planner.planner", "products.products", "products.heavy_machinery",
                         "crews.crews", "manufacturers", "dashboard.dashboard", "shopping.show_cart",
                         "auth.logout", "auth.login", "auth.register", "dashboard.projects",
                         "subscription.manage_subscription", "dashboard.settings"):
            self.app.add_url_rule("/" + endpoint.replace(".", "/"), endpoint=endpoint,
                                  view_func=lambda: "", methods=["GET", "POST"])
        self.client = self.app.test_client()
        self.data = {"csrf_token": "test-token", "review_type": "general", "rating": "5",
                     "title": "Good service", "body": "Everything arrived as expected."}
        self.products = patch("routes.reviews.get_review_products", return_value=[{"id": 42, "name": "Drill", "sku": "DR-42"}])
        self.browse = patch("routes.reviews.get_reviews", return_value={
            "items": [], "total": 0, "average": 0, "counts": {}, "matching": 0,
            "page": 1, "total_pages": 1, "start": 0, "end": 0})
        self.products.start()
        self.mock_browse = self.browse.start()
        self.addCleanup(self.products.stop)
        self.addCleanup(self.browse.stop)
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-token"

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 7

    def test_public_browsing_and_guest_prompt(self):
        response = self.client.get("/reviews")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Log in to write a review", response.data)

    @patch("routes.reviews.create_review")
    def test_guest_cannot_publish(self, save):
        response = self.client.post("/reviews", data=self.data)
        self.assertEqual(response.status_code, 401)
        save.assert_not_called()
        self.assertIn(b"Everything arrived as expected.", response.data)

    @patch("routes.reviews.create_review")
    def test_missing_csrf_cannot_publish(self, save):
        self.sign_in()
        response = self.client.post("/reviews", data=dict(self.data, csrf_token=""))
        self.assertEqual(response.status_code, 400)
        save.assert_not_called()

    @patch("routes.reviews.create_review", return_value=123)
    def test_success_redirects_to_published_review(self, save):
        self.sign_in()
        response = self.client.post("/reviews", data=self.data)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/reviews#review-123")
        self.assertEqual(save.call_args.args[0], 7)

    @patch("routes.reviews.create_review", side_effect=ValueError("Choose a star rating from 1 to 5."))
    def test_validation_keeps_and_escapes_draft(self, save):
        self.sign_in()
        response = self.client.post("/reviews", data=dict(self.data, title='<script>alert("x")</script>'))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Choose a star rating", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b'<script>alert("x")', response.data)

    def test_bad_query_parameters_use_safe_defaults(self):
        response = self.client.get("/reviews?type=bad&rating=9&sort=bad&page=-5")
        self.assertEqual(response.status_code, 200)
        self.mock_browse.assert_called_once_with(kind="all", rating=0, search="", sort="newest", page=1, product_id=None)

    def test_product_link_preselects_product_for_member(self):
        self.sign_in()
        response = self.client.get("/reviews?product=42")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="42" selected', response.data)
        self.assertIn(b'value="product" checked', response.data)

    @patch("routes.reviews.get_reviews", side_effect=Error("unavailable"))
    def test_database_failure_is_not_shown_as_no_reviews(self, browse):
        with self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.get("/reviews")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Reviews are temporarily unavailable", response.data)
        self.assertNotIn(b"Be the first to share.", response.data)

    @patch("routes.reviews.create_review", side_effect=Error("save unavailable"))
    def test_save_failure_preserves_draft(self, save):
        self.sign_in()
        with self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.post("/reviews", data=self.data)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"couldn&#39;t save your review", response.data)
        self.assertIn(b"Everything arrived as expected.", response.data)


if __name__ == "__main__":
    unittest.main()
