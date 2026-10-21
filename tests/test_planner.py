import json
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from planning import ai_config, jobs, presentation, workflow
from planning.schemas import AuditedEstimate, BadAnswer, DraftEstimate, Material, check_estimate
from services.crews import CREW_RATES, HOURS_PER_DAY, crew_estimate, parse_crew


MATERIAL = {
    "material_name": "Drywall", "specification": "4 x 8 ft sheets",
    "quantity": 9, "unit": "sheet",
    "notes": "256 sq ft / 32 sq ft per sheet, plus 10% waste, rounded up.",
    "product_id": 123,
}
RESULT = {
    "summary": "Drywall for the room.", "materials": [MATERIAL],
    "notes": ["Drying time depends on weather."],
    "crew": {"days": [3, 5], "members": [
        {"role": "drywall", "workers": 2, "days": [2, 3]},
        {"role": "painter", "workers": 1, "days": [1, 2]},
    ]},
}
PRODUCT = {
    "product_id": 123, "product_name": "Drywall sheet", "unit": "sheet",
    "unit_price": 12, "available_quantity": 100, "purchase_increment": 1,
}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        for target, value in [("check_model", None), ("pro_access_allowed", True)]:
            mock = patch.object(workflow, target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(workflow.time, "sleep")
        mock.start()
        self.addCleanup(mock.stop)

    def stage(self, response):
        with patch.object(workflow, "ask_model", return_value=json.dumps(response)):
            return workflow.run_stage("fast", "auditor", AuditedEstimate, {},
                                      ai_config.AUDITOR_PROMPT, {123})

    def test_positive_finite_quantities_required(self):
        for quantity in (None, 0, -1, True, "9", float("nan"), float("inf")):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                Material.model_validate({**MATERIAL, "quantity": quantity})
        for field in MATERIAL:
            incomplete = dict(MATERIAL)
            del incomplete[field]
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                Material.model_validate(incomplete)

    def test_quantities_are_not_recalculated(self):
        for quantity in (0.001, 2.5, 9):
            draft = DraftEstimate.model_validate({"materials": [{**MATERIAL, "quantity": quantity}]}).model_dump()
            self.assertEqual(check_estimate(draft, {123})["materials"][0]["quantity"], quantity)

    def test_names_units_notes_and_catalog(self):
        for field in ("material_name", "unit", "notes"):
            with self.subTest(field=field), self.assertRaises(BadAnswer):
                check_estimate({"materials": [{**MATERIAL, field: " "}]}, {123})
        with self.assertRaises(BadAnswer):
            check_estimate({"materials": []}, {123})
        result = check_estimate({"materials": [{**MATERIAL, "product_id": 999}]}, {123})
        self.assertIsNone(result["materials"][0]["product_id"])

    def test_all_tiers_share_context_and_auditor_format(self):
        for tier, planner_count in (("fast", 1), ("standard", 1), ("pro", 2)):
            calls = []
            project = {"description": "Drywall only; no new wiring", "dimensions": {"area": 256}}
            answers = [{"question": "Ceiling height?", "answer": "8 feet"}]

            def answer(model, prompt, reasoning, instructions, schema, tokens):
                request = json.loads(prompt)
                calls.append((schema["title"], request, instructions))
                self.assertEqual(request["project"], project)
                self.assertEqual(request["answers"], answers)
                self.assertNotIn("original_request", request)
                self.assertNotIn("interpretation", request)
                if schema["title"] == "Specification":
                    self.assertEqual(request["details"], [])
                    return json.dumps({"details": ["8 foot ceiling"], "questions": []})
                self.assertEqual(request["details"], ["8 foot ceiling"])
                if schema["title"] == "DraftEstimate":
                    return json.dumps({"materials": [MATERIAL]})
                self.assertEqual(len(request["estimates"]), planner_count)
                self.assertNotIn("estimate", request)
                self.assertEqual(set(request["available_crew_roles"]), set(CREW_RATES))
                self.assertEqual(instructions, ai_config.AUDITOR_PROMPT)
                return json.dumps(RESULT)

            with self.subTest(tier=tier), patch.object(workflow, "ask_model", side_effect=answer), \
                    patch.object(workflow, "get_planner_catalog", return_value=[PRODUCT]):
                job = {"tier": tier, "owner": "test", "project": project, "answers": answers}
                workflow.run_workflow(job, lambda job: None)
                self.assertEqual(len(calls), planner_count + 2)
                self.assertEqual(job["status"], "complete")
                self.assertEqual(job["result"]["planning_status"], "complete")
                self.assertEqual(job["result"]["crew"]["label"], "AI-estimated crew")
                self.assertEqual(job["result"]["crew"]["members"], RESULT["crew"]["members"])
                self.assertNotIn("summary", job["specification"])

    def test_questions_pause_before_planning(self):
        with patch.object(workflow, "ask_model", return_value=json.dumps({
                "details": [], "questions": ["How large?"]})) as ask:
            job = {"tier": "fast", "project": {"description": "Room"}, "answers": []}
            workflow.run_workflow(job, lambda job: None)
            self.assertEqual(job["status"], "needs_input")
            self.assertEqual(ask.call_count, 1)

    def test_invalid_answer_retries_then_succeeds(self):
        bad = deepcopy(RESULT)
        bad["materials"][0]["quantity"] = 0
        with patch.object(workflow, "ask_model", side_effect=[json.dumps(bad), json.dumps(RESULT)]) as ask:
            output = workflow.run_stage("fast", "auditor", AuditedEstimate, {}, "", {123})
            self.assertEqual(output["materials"][0]["quantity"], 9)
            self.assertIn("problem_with_last_answer", json.loads(ask.call_args.args[1]))
        with self.assertRaises(workflow.PlanningError):
            self.stage(bad)

    def test_missing_crew_fallback(self):
        for missing in (True, False):
            result = deepcopy(RESULT)
            if missing:
                del result["crew"]
            else:
                result["crew"] = None
            output = self.stage(result)
            self.assertEqual(output["crew"]["members"][0]["role"], "general")
            self.assertEqual(output["crew"]["label"], "AI-estimated crew")
            self.assertEqual(len(output["notes"]), 2)

    def test_invalid_crews_are_rejected(self):
        for field, value in (("role", "invented"), ("workers", 0), ("workers", 100),
                             ("workers", True), ("days", [3, 2]), ("days", [1, 6])):
            result = deepcopy(RESULT)
            result["crew"]["members"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(workflow.PlanningError):
                self.stage(result)
        result = deepcopy(RESULT)
        result["crew"]["members"].append(result["crew"]["members"][0])
        with self.assertRaises(workflow.PlanningError):
            self.stage(result)

    def test_pro_can_review_one_surviving_draft(self):
        def stage(tier, role, *args):
            if role == "second_planner":
                raise workflow.PlanningError("Unavailable")
            return {"materials": [MATERIAL]}

        with patch.object(workflow, "run_stage", side_effect=stage):
            self.assertEqual(workflow.run_two_planners("pro", {}, {123}), [{"materials": [MATERIAL]}])

    def test_job_storage_and_crew_edit_round_trip(self):
        result = self.stage(RESULT)
        result["planning_status"] = "complete"
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(jobs, "database_path", return_value=Path(folder) / "jobs.sqlite3"):
            job = jobs.submit_job("test", "test-submission", {"description": "Drywall"})
            job = jobs.claim_job("test-worker")
            job.update(result=result, status="complete", phase="Complete")
            jobs.save_job(job, "test-worker")
            reopened = jobs.get_job(job["id"], "test")
            self.assertEqual(reopened["result"], result)
            crew = parse_crew(json.dumps(reopened["result"]["crew"]))
            crew["members"][0]["workers"] = 3
            self.assertEqual(parse_crew(json.dumps(crew))["members"][0]["workers"], 3)
            self.assertEqual(crew["members"][1]["days"], [1, 2])

    def test_store_rounding_totals_and_unit_mismatch(self):
        products = {123: {**PRODUCT, "purchase_increment": 10}}
        with patch.object(presentation, "get_products_by_ids", return_value=products):
            rows = presentation.add_store_details([MATERIAL, {**MATERIAL, "quantity": 1}])
        cart = presentation.cart_items(rows)
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], Decimal(10))
        self.assertEqual(presentation.cart_total(cart), Decimal(120))
        self.assertIsNone(presentation.buy_quantity({**MATERIAL, "unit": "sq_ft"}, PRODUCT))
        self.assertIsNone(presentation.buy_quantity(MATERIAL, None))

    def test_result_and_saved_project_templates(self):
        from app import app
        from flask import render_template

        result = self.stage(RESULT)
        with patch.object(presentation, "get_products_by_ids", return_value={123: PRODUCT}):
            materials = presentation.add_store_details(result["materials"])
        job = {"id": "test", "tier": "fast", "status": "complete", "result": result,
               "project": {"description": "Drywall", "project_type": "custom"}, "answers": []}
        project = {"id": 1, "name": "Room", "type": "Custom", "status": "Planned",
                   "status_tone": "ready", "created": 1, "updated": 1, "completed": False,
                   "job_exists": True, "job_id": "test"}
        with app.test_request_context():
            for template in app.jinja_env.list_templates():
                app.jinja_env.get_template(template)
            html = render_template("planner_job.html", job=job, title="Room", materials=materials,
                                   cart=[], cart_total=0, saved_project=None, can_save=False,
                                   crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY)
            self.assertIn(MATERIAL["notes"], html)
            self.assertIn("Planning notes", html)
            self.assertIn("AI-estimated crew", html)
            self.assertIn("job_id=test", html)
            for crew in (None, crew_estimate(result["crew"])):
                html = render_template("dashboard/project_detail.html", project=project, plan=job,
                                       materials=materials, crew=crew, crew_rates=CREW_RATES,
                                       hours_per_day=HOURS_PER_DAY)
                self.assertIn(RESULT["notes"][0], html)
                self.assertNotIn(">Waste<", html)
            macro = app.jinja_env.get_template("planner_components.html").module.planning_notes
            old = {"assumptions": ["Old assumption"], "warnings": ["Old warning", "Old assumption"]}
            self.assertEqual(macro(old).count("Old assumption"), 1)
            self.assertIn("Old warning", macro(old))


if __name__ == "__main__":
    unittest.main()
