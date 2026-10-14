"""Display behavior tested without providers, workers or database access."""
import copy
import unittest
from unittest.mock import patch

from app import app
from planning.ai_config import WORKFLOW_TIERS
from planning.presentation import display_quantity, material_rows, plan_presentation


def sample_job():
    return {
        "id": "preview", "tier": "fast", "status": "complete", "error": None,
        "specification_version": 1, "questions": [], "answers": [],
        "project": {"project_type": "birdhouse", "dimensions": {"width_inches": 8, "height_inches": 12}},
        "specification": {"summary": "A small outdoor birdhouse", "details": [], "questions": []},
        "result": {"format_version": 2, "audited": True, "planning_status": "complete",
                   "estimate": {"summary": "Materials for an outdoor birdhouse.",
                                "materials": [{"name": "Exterior plywood", "quantity": 1,
                                               "unit": "sheet", "specification": "Exterior grade plywood",
                                               "notes": "Check the cut layout before buying.",
                                               "waste_percent": 10, "round_up": True,
                                               "calculation": {"method": "count", "inputs": [
                                                   {"name": "count", "value": 1, "unit": "sheet"}]}}],
                                "assumptions": ["Exterior use"], "warnings": [], "questions": []}},
    }


class PresentationTests(unittest.TestCase):
    def setUp(self):
        config = patch.dict(app.config, TESTING=True, SECRET_KEY="presentation-test")
        config.start()
        self.addCleanup(config.stop)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 17
            session["planner_token"] = "test-token"

    def render(self, job):
        with patch("routes.planner.get_job", return_value=job):
            response = self.client.get("/planner/jobs/preview")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_display_precision_units_and_invalid_quantities(self):
        for number, expected in [(0, "0"), (32, "32"), (4.2, "4.2"),
                                 (0.032476085714285716, "0.03"), (0.000001, "<0.01"),
                                 (1250000.256, "1,250,000.26")]:
            with self.subTest(number=number):
                value = display_quantity(number, "sq_ft")
                self.assertEqual(value["value"], expected)
                self.assertEqual(value["original"], str(number))
                self.assertEqual(value["unit"], "sq ft")
        for value in [None, True, -1, float("nan"), float("inf"), {}, "unknown"]:
            self.assertFalse(display_quantity(value)["known"])
        self.assertTrue(display_quantity(1, "sheet", manual=True)["approximate"])

    def test_all_tiers_share_three_closed_panels_and_preserve_data(self):
        for tier, config in WORKFLOW_TIERS.items():
            with self.subTest(tier=tier):
                job = sample_job()
                job["tier"] = tier
                before = copy.deepcopy(job)
                html = self.render(job)
                self.assertIn(config["label"], html)
                self.assertEqual(html.count("<details "), 3)
                self.assertNotIn("<details open", html)
                self.assertNotIn(' open>', html)
                self.assertIn("Check the cut layout before buying.", html)
                self.assertIn("Exterior use", html)
                self.assertIn("/planner/jobs/preview/result", html)
                self.assertEqual(job, before)

    def test_critical_warnings_and_unknowns_stay_outside_panels(self):
        job = sample_job()
        job["result"]["estimate"]["warnings"] = ["Confirm the wall loading."]
        job["result"]["estimate"]["questions"] = ["What is the height?"]
        job["result"]["estimate"]["materials"][0]["quantity"] = None
        html = self.render(job)
        visible = html.split('<div class="plan-details">')[0]
        for message in ["Confirm the wall loading.", "What is the height?", "quantity is unknown.", "Review needed"]:
            self.assertIn(message, visible)
        self.assertNotIn("Arithmetic checked by Python", html)

    def test_manual_and_unknown_methods_never_appear_verified(self):
        for method in ["manual", "unexpected", None]:
            job = sample_job()
            job["result"]["estimate"]["materials"][0]["calculation"]["method"] = method
            html = self.render(job)
            self.assertNotIn("Arithmetic checked by Python", html)
            if method == "manual":
                self.assertIn("Manual estimate - not verified", html)

    def test_malformed_optional_fields_render_and_text_is_escaped(self):
        job = sample_job()
        job["result"]["estimate"].update(assumptions=None, warnings={}, questions=False,
            materials=[None, "invalid", {"name": "<script>alert(1)</script>", "calculation": [],
                                       "specification": {}, "notes": [], "quantity": "bad", "unit": None}])
        job["result"]["independent_estimates"] = {"primary": None}
        html = self.render(job)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("Not determined", html)
        job["result"] = {"estimate": None}
        self.assertIn("No material quantities are available", self.render(job))

    def test_legacy_calculations_match_ids_and_expose_errors(self):
        estimate = {"materials": [{"id": "a", "name": "Flooring", "unit": "sq_ft"},
                                  {"id": "b", "name": "Paint", "unit": "gallon"}]}
        calculations = [{"material_id": "b", "quantity": 2, "status": "invalid"},
                        {"material_id": "a", "quantity": 132, "net_quantity": 120,
                         "purchase_count": 5, "status": "verified_arithmetic"}]
        rows = material_rows(estimate, calculations)
        self.assertEqual(rows[0]["quantity"]["value"], "132")
        self.assertEqual(rows[0]["purchase"]["value"], "5")
        self.assertEqual(rows[1]["verification"], "Calculation needs review")
        job = sample_job()
        job["result"] = {"estimate": estimate, "calculations": calculations}
        self.assertIn("Paint: the calculation needs review.", plan_presentation(job)["warnings"])
        self.assertIn("Purchase quantity", self.render(job))

    def test_legacy_positional_calculations_do_not_claim_verification(self):
        estimate = {"materials": [{"name": "Paint", "unit": "gallon"}]}
        calculations = [{"quantity": 2, "method": "manual"}]
        rows = material_rows(estimate, calculations)
        self.assertEqual(rows[0]["quantity"]["value"], "2")
        self.assertEqual(rows[0]["verification"], "Manual estimate - not verified")

    def test_legacy_calculation_with_malformed_id_still_renders(self):
        estimate = {"materials": [{"id": ["old"], "name": "Paint", "unit": "gallon"}]}
        calculations = [{"material_id": ["old"], "quantity": 2, "status": "invalid"}]
        rows = material_rows(estimate, calculations)
        self.assertEqual(rows[0]["quantity"]["value"], "2")
        self.assertEqual(rows[0]["verification"], "Calculation needs review")

    def test_long_fractional_estimate_preserves_full_details(self):
        job = sample_job()
        item = job["result"]["estimate"]["materials"][0]
        item.update(quantity=0.032476085714285716, specification="Long specification " * 30)
        html = self.render(job)
        table = html.split('<table ')[1].split('</table>')[0]
        self.assertIn("0.03", table)
        self.assertNotIn("0.032476085714285716", table)
        self.assertIn("0.032476085714285716", html)
        self.assertIn(item["specification"].strip(), html)
        self.assertNotIn("Purchase quantity", table)


if __name__ == "__main__":
    unittest.main()
