import importlib
import json
import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from threading import Event

from planning import ai_config, ai_planner, jobs, presentation, worker, workflow
from planning.schemas import AuditedEstimate, DraftEstimate, Material, clear_unknown_products
from services.crews import CREW_RATES, HOURS_PER_DAY, estimate_crew_cost, parse_crew


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
    "unit_price": 12, "available_quantity": 100,
}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        mock = patch.object(workflow, "pro_access_allowed", return_value=True)
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(workflow.time, "sleep")
        mock.start()
        self.addCleanup(mock.stop)

    def stage(self, response):
        with patch.object(workflow, "ask_model", return_value=json.dumps(response)):
            return workflow.run_stage("fast", "auditor", AuditedEstimate, {"catalog": [PRODUCT]},
                                      ai_config.AUDITOR_PROMPT)

    def test_gemini_3_8_is_replaced_by_3_5_flash_lite(self):
        # Reload the model settings with .env asking for Gemini 3.8, then restore them.
        self.addCleanup(importlib.reload, ai_planner)
        with patch.dict(os.environ, {"GEMINI_MODEL_STRONG": "gemini-3.8-flash", "GEMINI_MODEL_FAST": ""}):
            importlib.reload(ai_planner)
        self.assertEqual(ai_planner.AI_MODELS["gemini_strong"]["model"], "gemini-3.5-flash-lite")
        self.assertEqual(ai_planner.AI_MODELS["gemini_fast"]["model"], "gemini-3.5-flash-lite")

    def test_planner_stages_use_the_groq_client(self):
        draft = {"materials": [{**MATERIAL, "product_id": None}]}
        response = {"text": json.dumps(draft), "finish_reason": "stop"}
        with patch.dict(ai_planner.AI_MODELS["gpt_oss"], {"client": object()}), \
                patch.object(ai_planner, "call_groq", return_value=response) as groq, \
                patch.object(ai_planner, "call_gemini") as gemini:
            for tier, role in (("fast", "planner"), ("standard", "planner"), ("pro", "second_planner")):
                with self.subTest(tier=tier):
                    result = workflow.run_stage(tier, role, DraftEstimate, {}, ai_config.PLANNER_PROMPT)
                    self.assertEqual(result, draft)
                    self.assertEqual(groq.call_args.args[0]["provider"], "groq")
            self.assertEqual(groq.call_count, 3)
            gemini.assert_not_called()

    def test_tiers_and_fallback_use_their_assigned_api_keys(self):
        assignments = {
            "fast": {"interpreter": "GEMINI_API_KEY", "auditor": "GEMINI_API_KEY"},
            "standard": {"interpreter": "GEMINI_API_KEY2", "auditor": "GEMINI_API_KEY2"},
            "pro": {"interpreter": "GEMINI_API_KEY3", "planner": "GEMINI_API_KEY3"},
        }
        fake_keys = {name: f"test-key-{number}" for number, name in enumerate(
            ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEY3", "GEMINI_API_KEY4"), 1)}
        with patch.dict(os.environ, fake_keys), patch.object(ai_planner.genai, "Client") as client:
            for tier, roles in assignments.items():
                for role, expected_key in roles.items():
                    with self.subTest(tier=tier, role=role):
                        settings = ai_config.MODELS[ai_config.WORKFLOW_TIERS[tier][role]["model"]]
                        ai_planner.make_client(settings["provider"], settings["api_key"])
                        client.assert_called_with(api_key=fake_keys[expected_key])
            fallback = ai_config.WORKFLOW_TIERS["pro"]["auditor"]["fallback"]
            settings = ai_config.MODELS[fallback]
            ai_planner.make_client(settings["provider"], settings["api_key"])
            client.assert_called_with(api_key=fake_keys["GEMINI_API_KEY4"])

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
            text = json.dumps({"materials": [{**MATERIAL, "quantity": quantity}]})
            draft = DraftEstimate.model_validate_json(text).model_dump()
            self.assertEqual(draft["materials"][0]["quantity"], quantity)

    def test_schema_rejects_blank_text_and_empty_materials(self):
        for field in ("material_name", "unit", "notes"):
            text = json.dumps({"materials": [{**MATERIAL, field: " "}]})
            with self.subTest(field=field), self.assertRaises(ValidationError):
                DraftEstimate.model_validate_json(text)
        with self.assertRaises(ValidationError):
            DraftEstimate.model_validate_json('{"materials": []}')
        # An empty specification and empty project notes are still allowed.
        text = json.dumps({"materials": [{**MATERIAL, "specification": ""}]})
        DraftEstimate.model_validate_json(text)
        AuditedEstimate.model_validate_json(json.dumps({**RESULT, "notes": []}))

    def test_unknown_catalog_products_are_cleared(self):
        estimate = {"materials": [dict(MATERIAL), {**MATERIAL, "product_id": 999}]}
        clear_unknown_products(estimate, {123})
        self.assertEqual(estimate["materials"][0]["product_id"], 123)
        self.assertIsNone(estimate["materials"][1]["product_id"])

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
                    catalog.assert_not_called()
                    self.assertNotIn("catalog", request)
                    self.assertEqual(request["details"], [])
                    return json.dumps({"details": ["8 foot ceiling"], "questions": []})
                self.assertEqual(request["details"], ["8 foot ceiling"])
                if schema["title"] == "DraftEstimate":
                    catalog.assert_not_called()
                    self.assertNotIn("catalog", request)
                    return json.dumps({"materials": [{**MATERIAL, "product_id": None}]})
                self.assertEqual(request["catalog"], [PRODUCT])
                catalog.assert_called_once_with()
                self.assertEqual(len(request["estimates"]), planner_count)
                for estimate in request["estimates"]:
                    self.assertIsNone(estimate["materials"][0]["product_id"])
                self.assertNotIn("estimate", request)
                self.assertEqual(set(request["available_crew_roles"]), set(CREW_RATES))
                self.assertEqual(instructions, ai_config.AUDITOR_PROMPT)
                return json.dumps(RESULT)

            with self.subTest(tier=tier), patch.object(workflow, "ask_model", side_effect=answer), \
                    patch.object(workflow, "get_planner_catalog", return_value=[PRODUCT]) as catalog:
                job = {"tier": tier, "owner": "test", "project": project, "answers": answers,
                       "stages": jobs.pending_stages(tier)}
                workflow.run_workflow(job, lambda job: None)
                self.assertEqual(len(calls), planner_count + 2)
                self.assertEqual(job["status"], "complete")
                self.assertEqual(job["result"]["crew"]["label"], "AI-estimated crew")
                self.assertEqual(job["result"]["crew"]["members"], RESULT["crew"]["members"])
                self.assertEqual(job["result"]["materials"], RESULT["materials"])
                catalog.assert_called_once_with()
                self.assertNotIn("summary", job["specification"])

    def test_final_auditor_filters_ids_without_losing_unmatched_materials(self):
        materials = [dict(MATERIAL), {**MATERIAL, "material_name": "Special panel", "product_id": 999,
                                     "quantity": 2.5}, {**MATERIAL, "material_name": "Unmatched trim", "product_id": None}]
        audited = {**RESULT, "materials": materials}
        for catalog in ([PRODUCT], []):
            with self.subTest(catalog=catalog), patch.object(workflow, "ask_model", return_value=json.dumps(audited)):
                output = workflow.run_stage("fast", "auditor", AuditedEstimate, {"catalog": catalog}, ai_config.AUDITOR_PROMPT)
                expected = [123, None, None] if catalog else [None, None, None]
                self.assertEqual([row["product_id"] for row in output["materials"]], expected)
                self.assertEqual(len(output["materials"]), 3)
                for original, final in zip(materials, output["materials"]):
                    self.assertEqual({key: value for key, value in original.items() if key != "product_id"},
                                     {key: value for key, value in final.items() if key != "product_id"})
                self.assertEqual(output["crew"]["members"], RESULT["crew"]["members"])

    def test_invalid_product_id_types_are_rejected(self):
        for product_id in ("123", True, 123.5):
            with self.subTest(product_id=product_id), self.assertRaises(workflow.PlanningError):
                self.stage({**RESULT, "materials": [{**MATERIAL, "product_id": product_id}]})

    def test_planner_drafts_cannot_assign_store_ids(self):
        for tier, role in (("fast", "planner"), ("standard", "planner"), ("pro", "planner"), ("pro", "second_planner")):
            with self.subTest(tier=tier, role=role), patch.object(workflow, "ask_model", return_value=json.dumps({"materials": [MATERIAL]})), \
                    patch.object(workflow, "clear_unknown_products") as validate_ids:
                output = workflow.run_stage(tier, role, DraftEstimate, {}, ai_config.PLANNER_PROMPT)
                self.assertIsNone(output["materials"][0]["product_id"])
                self.assertEqual(output["materials"][0]["quantity"], MATERIAL["quantity"])
                validate_ids.assert_not_called()

    def test_auditor_fallback_uses_the_same_catalog_and_filters_ids(self):
        audited = {**RESULT, "materials": [{**MATERIAL, "product_id": 999}]}
        with patch.object(workflow, "ask_model", side_effect=["{}", json.dumps(audited)]) as ask:
            output = workflow.run_stage("pro", "auditor", AuditedEstimate, {"catalog": [PRODUCT]}, ai_config.AUDITOR_PROMPT)
        self.assertIsNone(output["materials"][0]["product_id"])
        self.assertEqual([call.args[0] for call in ask.call_args_list], ["nemotron", "gemini_fallback"])
        for call in ask.call_args_list:
            self.assertEqual(json.loads(call.args[1])["catalog"], [PRODUCT])

    def test_questions_pause_before_planning(self):
        with patch.object(workflow, "ask_model", return_value=json.dumps({
                "details": [], "questions": ["How large?"]})) as ask:
            job = {"tier": "fast", "project": {"description": "Room"}, "answers": [],
                   "stages": jobs.pending_stages("fast")}
            workflow.run_workflow(job, lambda job: None)
            self.assertEqual(job["status"], "needs_input")
            self.assertEqual(ask.call_count, 1)

    def test_invalid_answer_retries_then_succeeds(self):
        bad = deepcopy(RESULT)
        bad["materials"][0]["quantity"] = 0
        with patch.object(workflow, "ask_model", side_effect=[json.dumps(bad), json.dumps(RESULT)]) as ask:
            output = workflow.run_stage("fast", "auditor", AuditedEstimate, {"catalog": [PRODUCT]}, "")
            self.assertEqual(output["materials"][0]["quantity"], 9)
            self.assertIn("problem_with_last_answer", json.loads(ask.call_args.args[1]))
        with self.assertRaises(workflow.PlanningError):
            self.stage(bad)

    def test_missing_crew_is_retried_with_feedback(self):
        for missing in (True, False):
            result = deepcopy(RESULT)
            if missing:
                del result["crew"]
            else:
                result["crew"] = None
            with self.subTest(missing=missing), patch.object(
                    workflow, "ask_model", side_effect=[json.dumps(result), json.dumps(RESULT)]) as ask:
                output = workflow.run_stage("fast", "auditor", AuditedEstimate, {"catalog": [PRODUCT]}, "")
                self.assertEqual(output["crew"]["members"], RESULT["crew"]["members"])
                feedback = json.loads(ask.call_args.args[1])["problem_with_last_answer"]
                self.assertIn("crew", feedback)
            with self.assertRaises(workflow.PlanningError):
                self.stage(result)

    def test_all_tiers_retry_null_quantities_with_specific_feedback(self):
        for tier in ai_config.WORKFLOW_TIERS:
            for role, record_type in (("planner", DraftEstimate), ("auditor", AuditedEstimate)):
                good = deepcopy(RESULT) if role == "auditor" else {"materials": [dict(MATERIAL)]}
                bad = deepcopy(good)
                bad["materials"][0].update(quantity=None, notes="Footing volume is design-dependent.")
                with self.subTest(tier=tier, role=role), patch.object(
                        workflow, "ask_model", side_effect=[json.dumps(bad), json.dumps(good)]) as ask:
                    inputs = {"catalog": [PRODUCT]} if role == "auditor" else {}
                    output = workflow.run_stage(tier, role, record_type, inputs, "")
                    self.assertGreater(output["materials"][0]["quantity"], 0)
                    feedback = json.loads(ask.call_args.args[1])["problem_with_last_answer"]
                    self.assertIn("materials.0.quantity", feedback)
                    self.assertIn("assumptions", feedback)
        with self.assertRaises(workflow.PlanningError):
            self.stage(bad)

    def test_failed_plan_restart_keeps_project_and_answers(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(jobs, "database_path", return_value=Path(folder) / "jobs.sqlite3"):
            project = {"description": "Deck with ramp"}
            answers = [{"question": "Size?", "answer": "12 by 16 feet"}]
            old = jobs.submit_job("test", "failed-plan", project, answers=answers)
            with self.assertRaises(ValueError):
                jobs.restart_job(old["id"], "test")
            old = jobs.claim_job("test-worker")
            old.update(status="failed", error="The planner step failed.")
            jobs.save_job(old, "test-worker")
            with self.assertRaises(ValueError):
                jobs.restart_job(old["id"], "someone-else")
            new = jobs.restart_job(old["id"], "test")
            self.assertNotEqual(old["id"], new["id"])
            self.assertEqual(new["project"], project)
            self.assertEqual(new["answers"], answers)
            self.assertEqual(new["status"], "queued")
            self.assertIsNone(new["result"])
            self.assertEqual(jobs.restart_job(old["id"], "test")["id"], new["id"])

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

        states = {}

        def update(role, state):
            states[role] = state

        with patch.object(workflow, "run_stage", side_effect=stage):
            self.assertEqual(workflow.run_two_planners("pro", {}, update), [{"materials": [MATERIAL]}])
        self.assertEqual(states, {"planner": "done", "second_planner": "failed"})

    def test_job_storage_and_crew_edit_round_trip(self):
        result = self.stage(RESULT)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(jobs, "database_path", return_value=Path(folder) / "jobs.sqlite3"):
            job = jobs.submit_job("test", "test-submission", {"description": "Drywall"})
            job = jobs.claim_job("test-worker")
            job.update(result=result, status="complete")
            jobs.save_job(job, "test-worker")
            reopened = jobs.get_job(job["id"], "test")
            self.assertEqual(reopened["result"], result)
            crew = parse_crew(json.dumps(reopened["result"]["crew"]))
            crew["members"][0]["workers"] = 3
            self.assertEqual(parse_crew(json.dumps(crew))["members"][0]["workers"], 3)
            self.assertEqual(crew["members"][1]["days"], [1, 2])

    def test_store_rounding_totals_and_unit_mismatch(self):
        products = {123: PRODUCT}
        with patch.object(presentation, "get_products_by_ids", return_value=products):
            rows = presentation.add_store_details([{**MATERIAL, "quantity": 8.2}, {**MATERIAL, "quantity": 1.1}])
        cart = presentation.cart_items(rows)
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], Decimal(10))
        self.assertEqual(presentation.cart_total(cart), Decimal(120))
        self.assertIsNone(presentation.buy_quantity({**MATERIAL, "unit": "sq_ft"}, PRODUCT))
        self.assertIsNone(presentation.buy_quantity(MATERIAL, None))

    def test_project_rows_preserve_false_zero_and_small_quantities(self):
        rows = presentation.project_spec_rows({
            "dimensions": {"width_ft": 0, "thickness_inches": 0.00025},
            "project_type": "shed", "description": "A shed", "perch": False,
            "lighting": True, "bedrooms": 0, "missing": None, "color": "Natural",
        })
        self.assertEqual(rows, [
            {"label": "Width ft", "value": "0"},
            {"label": "Thickness inches", "value": "0.00025"},
            {"label": "Perch", "value": "No"},
            {"label": "Lighting", "value": "Yes"},
            {"label": "Bedrooms", "value": "0"},
            {"label": "Color", "value": "Natural"},
        ])

    def test_amount_filter_keeps_existing_rounding(self):
        from app import app
        values = [(None, "Unknown"), (0, "0"), (2.50, "2.5"), (1234.567, "1,234.57"),
                  (Decimal("0.00025"), "0.00025"), (0.009999, "0.009999"),
                  (0.01, "0.01"), (-0.001, "-0")]
        for value, expected in values:
            with self.subTest(value=value):
                self.assertEqual(presentation.format_amount(value), expected)
                with app.app_context():
                    rendered = app.jinja_env.from_string("{{ value|amount }}").render(value=value)
                self.assertEqual(rendered, expected)

    def test_stage_rows_keep_tier_order_and_default_states(self):
        for tier in ("fast", "standard", "pro"):
            with self.subTest(tier=tier):
                rows = presentation.stage_rows({"tier": tier, "stages": {"interpreter": "done"}})
                expected = ["interpreter", "planner", "auditor"]
                if tier == "pro":
                    expected.insert(2, "second_planner")
                self.assertEqual([row["name"] for row in rows], expected)
                self.assertEqual(rows[0]["status_label"], "Done")
                self.assertEqual(rows[1]["state"], "pending")
                for row in rows:
                    self.assertEqual(row["status_label"], presentation.STAGE_STATUS_LABELS[row["state"]])

    def test_material_display_states_remain_distinct(self):
        cases = [
            (None, {}, "unmatched", "unknown", False, False, False),
            (999, {}, "missing", "unknown", False, False, False),
            (123, {**PRODUCT, "available_quantity": None}, "matched", "unknown", True, False, False),
            (123, {**PRODUCT, "available_quantity": 0}, "matched", "out_of_stock", False, True, False),
            (123, {**PRODUCT, "available_quantity": 2}, "matched", "available", True, True, False),
            (123, {**PRODUCT, "unit": "box"}, "matched", "available", False, False, True),
        ]
        for product_id, product, match, stock, can_add, insufficient, store_link in cases:
            with self.subTest(product_id=product_id, product=product):
                products = {}
                if product:
                    products[product_id] = product
                with patch.object(presentation, "get_products_by_ids", return_value=products):
                    row = presentation.add_store_details([{**MATERIAL, "product_id": product_id}])[0]
                self.assertEqual(row["match_status"], match)
                self.assertEqual(row["stock_status"], stock)
                self.assertEqual(row["can_add"], can_add)
                self.assertEqual(row["insufficient_stock"], insufficient)
                self.assertEqual(row["show_store_link"], store_link)
                if store_link:
                    self.assertTrue(row["incompatible_units"])
        with patch.object(presentation, "get_products_by_ids",
                          return_value={123: {**PRODUCT, "unit_price": 0}}):
            row = presentation.add_store_details([MATERIAL])[0]
        self.assertEqual(row["line_total"], Decimal(0))

    def test_result_and_saved_project_templates(self):
        from app import app
        from flask import render_template

        result = self.stage(RESULT)
        with patch.object(presentation, "get_products_by_ids", return_value={123: PRODUCT}):
            materials = presentation.add_store_details(result["materials"])
        job = {"id": "test", "tier": "fast", "status": "complete", "result": result,
               "project": {"description": "Drywall", "project_type": "custom"}, "answers": []}
        project = {"id": 1, "name": "Room", "type": "Custom", "status": "Planned",
                   "status_label": "Planned",
                   "status_tone": "ready", "created": 1, "updated": 1, "completed": False,
                   "job_exists": True, "job_id": "test"}
        with app.test_request_context():
            for template in app.jinja_env.list_templates():
                app.jinja_env.get_template(template)
            html = render_template("planner_job.html", job=job, title="Room", materials=materials,
                                   cart=[], cart_total=0, saved_project=None, can_save=False,
                                   crew_recommendation=result["crew"], crew_url="/crews?job_id=test",
                                   project_fields=presentation.project_spec_rows(job["project"]),
                                   stage_rows=presentation.stage_rows(job),
                                   stage_status_labels=presentation.STAGE_STATUS_LABELS,
                                   crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY)
            self.assertIn(MATERIAL["notes"], html)
            self.assertIn("Planning notes", html)
            self.assertIn("AI-estimated crew", html)
            self.assertIn("job_id=test", html)
            self.assertNotIn("Recalculate plan", html)
            html = render_template("planner_job.html", job={**job, "status": "failed", "result": None,
                                                            "error": "The planner step failed."},
                                   title="Room", materials=[], cart=[], cart_total=0,
                                   saved_project=None, can_save=False,
                                   project_fields=presentation.project_spec_rows(job["project"]),
                                   stage_rows=presentation.stage_rows(job),
                                   stage_status_labels=presentation.STAGE_STATUS_LABELS,
                                   crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY)
            self.assertIn('action="/planner/jobs/test/restart"', html)
            self.assertIn("The planner step failed.", html)
            for crew in (None, estimate_crew_cost(result["crew"])):
                html = render_template("dashboard/project_detail.html", project=project, plan=job,
                                       materials=materials, crew=crew, crew_rates=CREW_RATES,
                                       project_fields=presentation.project_spec_rows(job["project"]),
                                       hours_per_day=HOURS_PER_DAY)
                self.assertIn(RESULT["notes"][0], html)
                self.assertNotIn(">Waste<", html)


class PlannerProgressTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        settings = {
            "planning.jobs.database_path": Path(folder.name) / "progress.sqlite3",
            "planning.jobs.pro_access_allowed": True,
            "planning.workflow.pro_access_allowed": True,
            "planning.workflow.get_planner_catalog": [PRODUCT],
        }
        for target, value in settings.items():
            mocked = patch(target, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        mocked = patch.object(workflow.time, "sleep")
        mocked.start()
        self.addCleanup(mocked.stop)
        self.snapshots = []
        self.number = 0

    def make_job(self, tier="fast"):
        self.number += 1
        job = jobs.submit_job("progress-owner", f"progress-{self.number}",
                              {"description": "Drywall a room"}, tier)
        self.assertTrue(all(status == "pending" for status in job["stages"].values()))
        return jobs.claim_job("progress-worker")

    def test_failed_transaction_rolls_back_and_closes_the_connection(self):
        job = self.make_job()
        with self.assertRaisesRegex(ValueError, "Test failure"):
            with jobs.connection() as database:
                database.execute("UPDATE planner_jobs SET status = 'complete' WHERE id = ?", (job["id"],))
                raise ValueError("Test failure")
        self.assertEqual(jobs.get_job(job["id"], job["owner"])["status"], "running")
        with self.assertRaises(sqlite3.ProgrammingError):
            database.execute("SELECT 1")

    def test_catalog_failure_marks_job_failed_without_auditing_an_empty_catalog(self):
        from mysql.connector import Error

        job = self.make_job()
        with patch.object(worker, "claim_job", return_value=job), \
                patch.object(workflow, "get_planner_catalog", side_effect=Error("Test database failure")), \
                patch.object(workflow, "ask_model", side_effect=self.answer) as ask, \
                self.assertLogs(worker.logger, level="ERROR"):
            worker.process_one("progress-worker")
        saved = jobs.get_job(job["id"], job["owner"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["stages"]["auditor"], "failed")
        self.assertIsNone(saved["result"])
        self.assertEqual(ask.call_count, 2)

    def save_progress(self, job):
        jobs.save_job(job, "progress-worker")
        self.snapshots.append(deepcopy(jobs.get_job(job["id"], job["owner"])))

    def answer(self, model, prompt, reasoning, instructions, schema, tokens):
        if schema["title"] == "Specification":
            return json.dumps({"details": ["Drywall a room"], "questions": []})
        if schema["title"] == "DraftEstimate":
            return json.dumps({"materials": [MATERIAL]})
        return json.dumps(RESULT)

    def test_all_tiers_save_real_stage_transitions(self):
        for tier in ai_config.WORKFLOW_TIERS:
            job = self.make_job(tier)
            self.snapshots = []
            with self.subTest(tier=tier), patch.object(workflow, "ask_model", side_effect=self.answer):
                workflow.run_workflow(job, self.save_progress)
                saved = jobs.get_job(job["id"], job["owner"])
                self.assertEqual(saved["status"], "complete")
                self.assertTrue(all(state == "done" for state in saved["stages"].values()))
                self.assertEqual("second_planner" in saved["stages"], tier == "pro")
                for stage in saved["stages"]:
                    states = [snapshot["stages"][stage] for snapshot in self.snapshots]
                    self.assertIn("processing", states)
                    self.assertGreater(states.index("done"), states.index("processing"))

    def test_pro_planners_run_in_parallel_and_keep_their_order(self):
        job = self.make_job("pro")
        second_started = Event()

        def answer(model, prompt, reasoning, instructions, schema, tokens):
            if schema["title"] == "DraftEstimate":
                if model == "gemini_strong":
                    # This only finishes if planner 2 runs at the same time.
                    self.assertTrue(second_started.wait(3), "The Pro planners did not run in parallel")
                    name = "First draft"
                else:
                    second_started.set()
                    name = "Second draft"
                return json.dumps({"materials": [{**MATERIAL, "material_name": name}]})
            if schema["title"] == "AuditedEstimate":
                drafts = json.loads(prompt)["estimates"]
                self.assertEqual([draft["materials"][0]["material_name"] for draft in drafts],
                                 ["First draft", "Second draft"])
            return self.answer(model, prompt, reasoning, instructions, schema, tokens)

        with patch.object(workflow, "ask_model", side_effect=answer):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(job["status"], "complete")
        self.assertTrue(all(state == "done" for state in job["stages"].values()))

    def test_retry_stays_processing_until_validated(self):
        job = self.make_job()
        attempts = 0

        def answer(model, prompt, reasoning, instructions, schema, tokens):
            nonlocal attempts
            if schema["title"] == "DraftEstimate":
                attempts += 1
                saved = jobs.get_job(job["id"], job["owner"])
                self.assertEqual(saved["stages"]["planner"], "processing")
                self.assertFalse(any(s["stages"]["planner"] == "done" for s in self.snapshots))
                if attempts == 1:
                    return json.dumps({"materials": [{**MATERIAL, "quantity": None}]})
            return self.answer(model, prompt, reasoning, instructions, schema, tokens)

        with patch.object(workflow, "ask_model", side_effect=answer):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(attempts, 2)
        self.assertEqual(job["stages"]["planner"], "done")

    def test_worker_marks_only_the_failing_stage_failed(self):
        for failed_stage, failed_schema in (("interpreter", "Specification"),
                                            ("planner", "DraftEstimate"), ("auditor", "AuditedEstimate")):
            job = self.make_job()

            def answer(model, prompt, reasoning, instructions, schema, tokens):
                if schema["title"] == failed_schema:
                    return "{}"
                return self.answer(model, prompt, reasoning, instructions, schema, tokens)

            with self.subTest(stage=failed_stage), patch.object(worker, "claim_job", return_value=job), \
                    patch.object(workflow, "ask_model", side_effect=answer):
                worker.process_one("progress-worker")
                saved = jobs.get_job(job["id"], job["owner"])
                self.assertEqual(saved["status"], "failed")
                stages = list(saved["stages"])
                for stage, state in saved["stages"].items():
                    # Stages before the failing one finished; the ones after it never started.
                    if stage == failed_stage:
                        expected = "failed"
                    elif stages.index(stage) < stages.index(failed_stage):
                        expected = "done"
                    else:
                        expected = "pending"
                    self.assertEqual(state, expected)

    def test_one_failed_pro_planner_stays_failed_on_successful_job(self):
        job = self.make_job("pro")

        def answer(model, prompt, reasoning, instructions, schema, tokens):
            if schema["title"] == "DraftEstimate" and model == "gpt_oss":
                return "{}"
            return self.answer(model, prompt, reasoning, instructions, schema, tokens)

        with patch.object(workflow, "ask_model", side_effect=answer):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["stages"], {"interpreter": "done", "planner": "done",
                                        "second_planner": "failed", "auditor": "done"})

    def test_both_pro_planners_fail_without_starting_auditor(self):
        job = self.make_job("pro")

        def answer(model, prompt, reasoning, instructions, schema, tokens):
            self.assertNotEqual(schema["title"], "AuditedEstimate")
            if schema["title"] == "DraftEstimate":
                return "{}"
            return self.answer(model, prompt, reasoning, instructions, schema, tokens)

        with patch.object(worker, "claim_job", return_value=job), \
                patch.object(workflow, "ask_model", side_effect=answer):
            worker.process_one("progress-worker")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["stages"], {"interpreter": "done", "planner": "failed",
                                        "second_planner": "failed", "auditor": "pending"})

    def test_pro_auditor_fallback_is_processing_until_success(self):
        job = self.make_job("pro")
        auditors = []

        def answer(model, prompt, reasoning, instructions, schema, tokens):
            if schema["title"] == "AuditedEstimate":
                auditors.append(model)
                self.assertEqual(jobs.get_job(job["id"], job["owner"])["stages"]["auditor"], "processing")
                if model == "nemotron":
                    return "{}"
            return self.answer(model, prompt, reasoning, instructions, schema, tokens)

        with patch.object(workflow, "ask_model", side_effect=answer):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(auditors, ["nemotron", "gemini_fallback"])
        self.assertEqual(job["stages"]["auditor"], "done")

    def test_unexpected_pro_failure_keeps_successful_planner_done(self):
        states = jobs.pending_stages("pro")

        def stage(tier, role, *args):
            if role == "planner":
                raise RuntimeError("Unexpected problem")
            return {"materials": [MATERIAL]}

        def update(role, state):
            states[role] = state

        with patch.object(workflow, "run_stage", side_effect=stage), self.assertRaises(RuntimeError):
            workflow.run_two_planners("pro", {}, update)
        self.assertEqual(states["planner"], "failed")
        self.assertEqual(states["second_planner"], "done")

    def test_questions_reset_progress_before_interpreter_runs_again(self):
        job = self.make_job()
        with patch.object(workflow, "ask_model", return_value=json.dumps({
                "details": [], "questions": ["How large?"]})):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(job["status"], "needs_input")
        self.assertEqual(job["stages"]["interpreter"], "done")
        self.assertEqual(job["stages"]["planner"], "pending")
        jobs.answer_job(job["id"], job["owner"], ["10 by 12 feet"])
        saved = jobs.get_job(job["id"], job["owner"])
        self.assertEqual(saved["status"], "queued")
        self.assertTrue(all(state == "pending" for state in saved["stages"].values()))
        job = jobs.claim_job("progress-worker")
        with patch.object(workflow, "ask_model", side_effect=self.answer):
            workflow.run_workflow(job, self.save_progress)
        self.assertEqual(job["status"], "complete")

    def test_interrupted_stage_is_failed(self):
        job = self.make_job()
        job["stages"].update(interpreter="done", planner="processing")
        self.save_progress(job)
        with jobs.connection() as database:
            database.execute("UPDATE planner_jobs SET lease_until = 0 WHERE id = ?", (job["id"],))
            jobs.fail_interrupted_jobs(database, jobs.time.time())
        saved = jobs.get_job(job["id"], job["owner"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["stages"], {"interpreter": "done", "planner": "failed", "auditor": "pending"})

    def test_cancellation_stops_stage_and_rejects_late_completion(self):
        job = self.make_job()
        job["stages"].update(interpreter="done", planner="processing")
        self.save_progress(job)
        self.assertTrue(jobs.cancel_job(job["id"], job["owner"]))
        saved = jobs.get_job(job["id"], job["owner"])
        self.assertEqual(saved["stages"]["planner"], "cancelled")
        self.assertEqual(saved["stages"]["interpreter"], "done")
        job["stages"]["planner"] = "done"
        with self.assertRaises(jobs.LeaseLost):
            jobs.save_job(job, "progress-worker")

    def test_status_response_contains_stages_and_keeps_ownership_check(self):
        from app import app
        from routes.planner import planning_job_status

        job = self.make_job("pro")
        with app.test_request_context(), patch("routes.planner.get_user_job", return_value=job) as owned:
            data, code, headers = planning_job_status(job["id"])
            owned.assert_called_once_with(job["id"])
            self.assertEqual(code, 200)
            self.assertEqual(data["stages"], job["stages"])
            self.assertEqual(data["label"], "Preparing your plan")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("result", data)
            self.assertNotIn("phase", data)


if __name__ == "__main__":
    unittest.main()
