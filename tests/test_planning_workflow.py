import copy
import json
import os
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import MagicMock, patch

from app import app
from planning import ai_config, ai_planner, jobs, workflow
from planning.contracts import Estimate, Specification, check_estimate
from planning.worker import process_one
from utils.rate_limits import limiter

PROJECT = {"project_type": "custom", "description": "Floor a 10 ft by 12 ft room.",
           "project_mode": "custom", "project_size": "small", "project_template": None}
SPECIFICATION = {"summary": "Floor a room", "details": ["10 ft by 12 ft", "10% waste"], "questions": []}
ESTIMATE = {
    "summary": "Flooring estimate", "assumptions": ["One layer"], "questions": [], "warnings": [],
    "materials": [{"name": "Flooring", "specification": "Click-lock vinyl", "quantity": 999.0,
                   "unit": "sq_ft", "waste_percent": 10.0, "round_up": False, "notes": "One layer",
                   "calculation": {"method": "rectangle_area", "inputs": [
                       {"name": "length", "value": 10.0, "unit": "ft"},
                       {"name": "width", "value": 12.0, "unit": "ft"},
                       {"name": "layers", "value": 1.0, "unit": "count"},
                   ]}}],
}


def provider_response(value):
    return {"text": json.dumps(value), "status": "completed", "finish_reason": "stop",
            "total_tokens": 100, "input_tokens": 60, "output_tokens": 40}


class PlanningWorkflowTests(unittest.TestCase):
    def test_all_tiers_share_estimate_schema_and_preserve_model_settings(self):
        for tier, aliases, reasoning in [
            ("fast", ["gemini_fast", "gpt_oss", "gemini_fast"], ["low"] * 3),
            ("standard", ["gemini_fast", "gpt_oss", "gemini_strong"], ["medium", "high", "medium"]),
            ("pro", ["gemini_strong", "gemini_strong", "gpt_oss", "nemotron"], ["high"] * 4),
        ]:
            with self.subTest(tier=tier), patch.dict(os.environ, {"PLANNER_PRO_TEST_ACCESS": "true"}):
                response = self.client.post("/planner/jobs", data={
                    "plannerToken": "test-planner-token", "submissionKey": "application-" + tier,
                    "projectMode": "custom", "projectSize": "small", "userInput": PROJECT["description"],
                    "planType": tier,
                })
                self.assertEqual(response.status_code, 303)
                job_id = response.location.rsplit("/", 1)[-1]
                def respond(alias, prompt, level, instructions, schema, output_tokens):
                    return provider_response(SPECIFICATION if "details" in schema["properties"] else ESTIMATE)
                with patch.object(workflow, "workflow_response", side_effect=respond) as provider:
                    process_one()
                calls = provider.call_args_list
                if tier == "pro":
                    self.assertCountEqual([c.args[0] for c in calls], aliases)
                else:
                    self.assertEqual([c.args[0] for c in calls], aliases)
                self.assertEqual([c.args[2] for c in calls], reasoning)
                if tier == "pro":
                    self.assertEqual([c.args[5] for c in calls], [16384, 16384, 32768, 16384])
                for call in calls[1:]:
                    self.assertEqual(call.args[4], Estimate.model_json_schema())
                saved = jobs.get_job(job_id, 17)
                self.assertEqual(saved["status"], "complete")
                self.assertEqual(saved["result"]["estimate"]["materials"][0]["quantity"], 132)
                # Quantities are corrected before any successful stage is saved.
                for name, stage in saved["stages"].items():
                    if name != "interpret":
                        self.assertEqual(stage["output"]["materials"][0]["quantity"], 132)
                self.assertEqual(self.client.get(response.location).status_code, 200)
                self.assertEqual(self.client.get(response.location + "/result").json["result"]["estimate"], saved["result"]["estimate"])

    def test_pro_branches_run_in_parallel_with_identical_inputs(self):
        job = self.pro_job()
        barrier, prompts = Barrier(2), []
        def respond(alias, prompt, level, instructions, schema, output_tokens):
            if "details" in schema["properties"]:
                return provider_response(SPECIFICATION)
            if alias != "nemotron":
                prompts.append(json.loads(prompt))
                barrier.wait(timeout=3)
            else:
                self.assertEqual(set(json.loads(prompt)["estimates"]), {"primary", "secondary"})
            return provider_response(ESTIMATE)
        with patch.object(workflow, "workflow_response", side_effect=respond):
            process_one()
        self.assertEqual(prompts[0], prompts[1])
        self.assertNotIn("estimate", prompts[0])
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_pro_retry_preserves_successful_work_and_recovers_both_failed_branches(self):
        for failed_aliases in [{"gpt_oss"}, {"gemini_strong", "gpt_oss"}]:
            with self.subTest(failed_aliases=failed_aliases):
                with patch.dict(os.environ, {"PLANNER_PRO_TEST_ACCESS": "true"}):
                    job = jobs.submit_job(17, "retry-branches-" + str(len(failed_aliases)), PROJECT, "pro")
                    def failed(alias, prompt, level, instructions, schema, output_tokens):
                        if "details" in schema["properties"]:
                            return provider_response(SPECIFICATION)
                        if alias in failed_aliases:
                            raise TimeoutError()
                        return provider_response(ESTIMATE)
                    with patch.object(workflow, "workflow_response", side_effect=failed):
                        process_one()
                    self.assertEqual(jobs.get_job(job["id"], 17)["status"], "failed")
                    jobs.retry_job(job["id"], 17)
                    with patch.object(workflow, "workflow_response", return_value=provider_response(ESTIMATE)) as provider:
                        process_one()
                    self.assertEqual(provider.call_count, len(failed_aliases) + 1)
                    self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_review_replaces_estimate_and_python_rechecks_it(self):
        job = self.submit()
        revised = copy.deepcopy(ESTIMATE)
        revised["materials"][0]["waste_percent"] = 20.0
        provider = self.process([SPECIFICATION, ESTIMATE, revised])
        reviewed_input = json.loads(provider.call_args_list[-1].args[1])
        self.assertEqual(reviewed_input["estimate"]["materials"][0]["quantity"], 132)
        self.assertEqual(jobs.get_job(job["id"], 17)["result"]["estimate"]["materials"][0]["quantity"], 144)

    def test_review_retry_reuses_saved_interpretation_and_plan(self):
        job = self.submit()
        with patch.object(workflow, "workflow_response", side_effect=[
                provider_response(SPECIFICATION), provider_response(ESTIMATE), TimeoutError(), TimeoutError()]):
            process_one()
        jobs.retry_job(job["id"], 17)
        self.assertEqual(self.process([ESTIMATE]).call_count, 1)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_expired_worker_reuses_saved_interpretation(self):
        job = self.submit()
        claimed = jobs.claim_job("crashed-worker")
        with patch.object(workflow, "workflow_response", return_value=provider_response(SPECIFICATION)):
            workflow.run_stage(claimed, "interpret", "interpreter", Specification,
                               {"original_request": PROJECT, "answers": [], "previous_specification": None},
                               ai_config.INTERPRETER_PROMPT, lambda value: jobs.save_job(value, "crashed-worker"))
        with jobs.connection() as database:
            database.execute("UPDATE planner_jobs SET lease_until = 0 WHERE id = ?", (job["id"],))
        self.assertEqual(self.process([ESTIMATE, ESTIMATE]).call_count, 2)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_questions_pause_and_resume_with_answers_in_all_prompts(self):
        job = self.submit()
        missing = {**SPECIFICATION, "questions": ["Room width?"]}
        self.assertEqual(self.process([missing]).call_count, 1)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "needs_input")
        with self.assertRaisesRegex(ValueError, "changed"):
            jobs.answer_job(job["id"], 17, ["12 ft"], 0)
        jobs.answer_job(job["id"], 17, ["12 ft"], 1)
        provider = self.process()
        for call in provider.call_args_list:
            self.assertEqual(json.loads(call.args[1])["answers"][0]["answer"], "12 ft")
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_answers_cannot_bypass_active_job_limit(self):
        job = self.submit()
        self.process([{**SPECIFICATION, "questions": ["Width?"]}])
        other = self.submit("another-job")
        with self.assertRaisesRegex(ValueError, "current planning job"):
            jobs.answer_job(job["id"], 17, ["12 ft"], 1)
        self.assertEqual(jobs.get_job(job["id"], 17)["answers"], [])
        jobs.cancel_job(other["id"], 17)
        jobs.answer_job(job["id"], 17, ["12 ft"], 1)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "queued")

    def test_review_questions_remain_answerable(self):
        job = self.submit()
        self.process([SPECIFICATION, ESTIMATE, {**ESTIMATE, "questions": ["Which finish?"]}])
        saved = jobs.get_job(job["id"], 17)
        self.assertEqual(saved["status"], "needs_input")
        self.assertEqual(saved["result"]["planning_status"], "partial")
        jobs.answer_job(job["id"], 17, ["Matte"], 1)
        self.process()
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "complete")

    def test_unresolved_review_warnings_keep_result_partial(self):
        job = self.submit()
        self.process([SPECIFICATION, ESTIMATE, {**ESTIMATE, "warnings": ["Verify subfloor condition."]}])
        saved = jobs.get_job(job["id"], 17)
        self.assertEqual(saved["status"], "partial")
        self.assertIn("Verify subfloor condition.", saved["result"]["warnings"])

    def test_fallback_is_partial_but_new_specification_can_complete(self):
        job = self.pro_job()
        class Unauthorized(Exception):
            status_code = 401
        def respond(alias, prompt, level, instructions, schema, output_tokens):
            if "details" in schema["properties"]:
                return provider_response(SPECIFICATION)
            if alias == "nemotron":
                raise Unauthorized()
            return provider_response({**ESTIMATE, "questions": ["Which finish?"]})
        with patch.object(workflow, "workflow_response", side_effect=respond):
            process_one()
        saved = jobs.get_job(job["id"], 17)
        self.assertTrue(saved["result"]["review_process_degraded"])
        self.assertEqual(saved["result"]["planning_status"], "partial")
        jobs.answer_job(job["id"], 17, ["Matte"], 1)
        def resumed(alias, prompt, level, instructions, schema, output_tokens):
            return provider_response(SPECIFICATION if "details" in schema["properties"] else ESTIMATE)
        with patch.object(workflow, "workflow_response", side_effect=resumed):
            process_one()
        saved = jobs.get_job(job["id"], 17)
        self.assertFalse(saved["result"]["review_process_degraded"])
        self.assertEqual(saved["status"], "complete")

    def test_invalid_calculation_gets_bounded_retry_before_saving(self):
        job = self.submit()
        invalid = copy.deepcopy(ESTIMATE)
        invalid["materials"][0]["calculation"]["inputs"].pop()
        provider = self.process([SPECIFICATION, invalid, invalid])
        saved = jobs.get_job(job["id"], 17)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(saved["status"], "failed")
        self.assertNotIn("plan", saved["stages"])

    def test_manual_and_unknown_quantities_are_labeled(self):
        for quantity in [7.0, None]:
            job = self.submit("manual-" + str(quantity))
            value = copy.deepcopy(ESTIMATE)
            value["materials"][0].update(quantity=quantity, calculation={"method": "manual", "inputs": []}, notes="Allowance including 10% waste")
            self.process([SPECIFICATION, value, value])
            saved = jobs.get_job(job["id"], 17)
            self.assertEqual(saved["result"]["estimate"]["materials"][0]["quantity"], quantity)
            self.assertIn("unverified", saved["result"]["warnings"][0])
            self.assertEqual(saved["status"], "partial" if quantity is None else "complete")

    def test_old_results_render_and_old_jobs_cannot_resume_under_new_schema(self):
        job = self.submit()
        claimed = jobs.claim_job("legacy-worker")
        claimed.update(config_version="4", status="complete", result={
            "tier": "fast", "planning_status": "complete", "audited": True, "plan_version": 1,
            "estimate": {"summary": "Saved legacy plan", "materials": [{"name": "Old flooring", "unit": "sq_ft", "notes": "", "specification": "Vinyl"}], "assumptions": [], "questions": []},
            "calculations": [{"quantity": 132}], "warnings": [], "findings": [],
        })
        jobs.save_job(claimed, "legacy-worker")
        page = self.client.get("/planner/jobs/" + job["id"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("132 sq ft", page.get_data(as_text=True))
        with patch.object(workflow, "workflow_response") as provider:
            with self.assertRaisesRegex(workflow.StageError, "older format"):
                workflow.run_workflow(claimed, lambda value: None)
        provider.assert_not_called()

        old_job = self.submit("old-unfinished-job")
        unfinished = jobs.claim_job("old-worker")
        unfinished.update(config_version="4", status="failed", current_stage="plan")
        jobs.save_job(unfinished, "old-worker")
        with self.assertRaisesRegex(ValueError, "older format"):
            jobs.retry_job(old_job["id"], 17)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.environment = patch.dict(os.environ, {
            "PLANNER_JOB_DATABASE": str(Path(self.folder.name) / "jobs.sqlite3"),
            "PLANNER_PRO_TEST_ACCESS": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.config = patch.dict(app.config, TESTING=True, SECRET_KEY="planner-test", RATELIMIT_ENABLED=False)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.limit = patch.object(limiter, "enabled", False)
        self.limit.start()
        self.addCleanup(self.limit.stop)
        self.model = patch.object(workflow, "workflow_model", return_value=({}, {}))
        self.model.start()
        self.addCleanup(self.model.stop)
        self.sleep = patch.object(workflow.time, "sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.standard = patch.dict(ai_config.WORKFLOW_TIERS["standard"], {"enabled": True})
        self.standard.start()
        self.addCleanup(self.standard.stop)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 17
            session["planner_token"] = "test-planner-token"

    def submit(self, key="submission-key-1", owner=17):
        return jobs.submit_job(owner, key, PROJECT)

    def process(self, outputs=None):
        outputs = outputs or [SPECIFICATION, ESTIMATE, ESTIMATE]
        responses = []
        for output in outputs:
            responses.append(provider_response(output))
        with patch.object(workflow, "workflow_response", side_effect=responses) as provider:
            process_one()
        return provider

    def test_invalid_json_recovery_is_bounded(self):
        job = self.submit()
        with patch.object(workflow, "workflow_response", return_value={**provider_response({}), "text": "bad JSON"}) as provider:
            process_one()
        failed = jobs.get_job(job["id"], 17)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(len(failed["attempts"]), 2)

    def test_truncated_json_is_not_accepted_even_when_parseable(self):
        job = self.submit()
        response = {**provider_response(SPECIFICATION), "status": "incomplete", "finish_reason": "length"}
        with patch.object(workflow, "workflow_response", return_value=response) as provider:
            process_one()
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "failed")

    def test_transport_failure_uses_two_attempts(self):
        job = self.submit()
        with patch.object(workflow, "workflow_response", side_effect=TimeoutError) as provider:
            process_one()
        self.assertEqual(provider.call_count, 2)
        failed = jobs.get_job(job["id"], 17)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(failed["attempts"]), 2)

    def test_duplicate_submission_returns_same_job(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(jobs.list_jobs(17)), 1)
        with self.assertRaises(ValueError):
            jobs.submit_job(17, "submission-key-1", {**PROJECT, "description": "Different"})

    def test_another_users_job_is_not_accessible(self):
        job = self.submit(owner=999)
        for suffix in ["", "/status", "/result"]:
            self.assertEqual(self.client.get("/planner/jobs/" + job["id"] + suffix).status_code, 404)
        self.assertEqual(self.client.post("/planner/jobs/" + job["id"] + "/cancel").status_code, 404)

    def test_submission_requires_login_and_form_token(self):
        response = self.client.post("/planner/jobs", data={})
        self.assertEqual(response.status_code, 400)
        anonymous = app.test_client()
        self.assertEqual(anonymous.post("/planner/jobs", data={}).status_code, 302)
        self.assertEqual(len(jobs.list_jobs(17)), 0)

    def test_cancelled_job_cannot_be_saved_by_old_worker(self):
        job = self.submit()
        claimed = jobs.claim_job("worker-1")
        jobs.cancel_job(job["id"], 17)
        with self.assertRaises(jobs.LeaseLost):
            jobs.save_job(claimed, "worker-1")
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "cancelled")

    def test_unrelated_worker_value_error_marks_job_failed(self):
        job = self.submit()
        with patch("planning.worker.run_workflow", side_effect=ValueError("Unexpected data")):
            process_one()
        saved = jobs.get_job(job["id"], 17)
        self.assertEqual(saved["status"], "failed")
        self.assertIn("could not finish", saved["error"])

    def test_cancellation_during_provider_keeps_job_cancelled(self):
        job = self.submit()

        def cancel_during_call(*args):
            jobs.cancel_job(job["id"], 17)
            return provider_response(SPECIFICATION)

        with patch.object(workflow, "workflow_response", side_effect=cancel_during_call) as provider:
            process_one()
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "cancelled")

    def test_attempt_limit_prevents_calls(self):
        job = self.submit("attempt-limit-test")
        with patch.dict(ai_config.WORKFLOW_TIERS["fast"], {"max_attempts": 0}), patch.object(workflow, "workflow_response") as provider:
            process_one()
        provider.assert_not_called()
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "failed")

    def test_daily_quota_and_concurrency_are_enforced(self):
        first = self.submit()
        with self.assertRaises(ValueError):
            self.submit("second-job")
        jobs.cancel_job(first["id"], 17)
        with patch.dict(ai_config.WORKFLOW_TIERS["fast"], {"daily_jobs": 1}):
            with self.assertRaises(ValueError):
                self.submit("second-job")

    def test_future_tier_cannot_bypass_gate(self):
        with patch.dict(ai_config.WORKFLOW_TIERS["pro"], {"enabled": False}):
            with self.assertRaises(ValueError):
                jobs.submit_job(17, "future-tier-key", PROJECT, "pro")

    def test_gemini_and_groq_send_explicit_settings_and_disable_sdk_retries(self):
        gemini = MagicMock()
        gemini.models.generate_content.return_value = {"text": "{}", "candidates": [{"finish_reason": "STOP"}]}
        _, response = ai_planner.call_gemini({"client": gemini, "model": "gemini-3.5-flash-lite"}, "{}", "low", "Role", {}, 8192)
        config = gemini.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config["thinking_config"], {"thinking_level": "low"})
        self.assertEqual(config["http_options"]["retry_options"]["attempts"], 1)
        groq = MagicMock()
        ai_planner.call_groq({"client": groq, "model": "openai/gpt-oss-120b"}, "{}", "low", "Role", {}, 8192)
        groq.with_options.assert_called_once_with(max_retries=0)
        self.assertEqual(groq.with_options.return_value.chat.completions.create.call_args.kwargs["reasoning_effort"], "low")

    def test_unverified_model_configuration_is_rejected(self):
        with patch.dict(ai_planner.AI_MODELS["gemini_weak"], {"model": "unverified-model", "client": object()}):
            with self.assertRaisesRegex(ValueError, "no verified"):
                ai_planner.workflow_model("gemini_fast", "low")

    def test_failed_retry_is_still_bounded_by_attempt_limit(self):
        job = self.submit()
        with patch.object(workflow, "workflow_response", side_effect=TimeoutError):
            process_one()
        with patch.dict(ai_config.WORKFLOW_TIERS["fast"], {"max_attempts": 2}):
            with self.assertRaises(ValueError):
                jobs.retry_job(job["id"], 17)

    def test_all_strong_gemini_clients_use_temporary_35_replacement(self):
        for alias in ["gemini_strong", "gemini_strong_2", "gemini_strong_3"]:
            self.assertEqual(ai_planner.AI_MODELS[alias]["model"], "gemini-3.5-flash-lite")
        self.assertEqual(ai_config.MODEL_CAPABILITIES["gemini-3.5-flash-lite"]["levels"], ["low", "medium", "high"])

    def pro_job(self):
        enabled = patch.dict(ai_config.WORKFLOW_TIERS["pro"], {"enabled": True})
        enabled.start()
        self.addCleanup(enabled.stop)
        entitlement = patch.dict(os.environ, {"PLANNER_PRO_USER_IDS": "17"})
        entitlement.start()
        self.addCleanup(entitlement.stop)
        return jobs.submit_job(17, "pro-test-key", PROJECT, "pro")

    def test_pro_access_cannot_be_granted_by_submitted_tier_or_session(self):
        with patch.dict(ai_config.WORKFLOW_TIERS["pro"], {"enabled": True}), patch.dict(os.environ, {"PLANNER_PRO_USER_IDS": ""}):
            with self.assertRaisesRegex(ValueError, "access"):
                jobs.submit_job(17, "not-paid-test", PROJECT, "pro")

    def test_pro_testing_access_allows_signed_in_submission_only(self):
        with patch.dict(os.environ, {"PLANNER_PRO_TEST_ACCESS": "true", "PLANNER_PRO_USER_IDS": ""}), patch.dict(
                ai_config.WORKFLOW_TIERS["pro"], {"enabled": True}):
            self.assertTrue(jobs.pro_access_allowed(17))
            self.assertFalse(jobs.pro_access_allowed(None))
            job = jobs.submit_job(17, "testing-access-key", PROJECT, "pro")
            self.assertEqual(job["status"], "queued")
            anonymous = app.test_client()
            response = anonymous.post("/planner/jobs", data={"planType": "pro"})
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.location)

    def test_revoked_pro_access_stops_worker_before_provider_calls(self):
        job = self.pro_job()
        with patch.dict(os.environ, {"PLANNER_PRO_USER_IDS": ""}), patch.object(workflow, "workflow_response") as provider:
            process_one()
        provider.assert_not_called()
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "failed")

    def test_pro_never_silently_lowers_reasoning(self):
        job = self.pro_job()
        with patch.dict(ai_config.WORKFLOW_TIERS["pro"], {"auditor_fallback": ("gemini_strong", "medium")}), patch.object(workflow, "workflow_response") as provider:
            process_one()
        provider.assert_not_called()
        self.assertEqual(jobs.get_job(job["id"], 17)["status"], "failed")

    def test_openrouter_adapter_requests_high_without_unsupported_schema_parameter(self):
        client = MagicMock()
        client.chat.send.return_value = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"total_tokens": 10}}
        ai_planner.call_openrouter({"client": client, "model": "nvidia/nemotron-3-ultra-550b-a55b:free"}, "Original", "high", "Role", {"type": "object"}, 16384)
        options = client.chat.send.call_args.kwargs
        self.assertEqual(options["reasoning"], {"effort": "high", "exclude": True})
        self.assertEqual(options["provider"], {"require_parameters": True})
        self.assertNotIn("response_format", options)
        self.assertIn('"type": "object"', options["messages"][1]["content"])

    def test_groq_output_limit_error_is_reported_without_exposing_generated_text(self):
        error = ValueError("Provider returned HTTP 400")
        error.status_code = 400
        error.body = {"error": {"message": "max completion tokens reached before generating a valid document",
                                "failed_generation": "private project details"}}
        message, kind, retryable = workflow.stage_error(error)
        self.assertEqual(kind, "output_limit")
        self.assertTrue(retryable)
        self.assertIn("output tokens", message)
        self.assertNotIn("private project details", message)

    def test_groq_json_object_mode_keeps_schema_and_high_reasoning(self):
        client = MagicMock()
        client.with_options.return_value.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"summary":"ok"}'), finish_reason="stop")],
            usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
        ai_planner.call_groq({"client": client, "model": "openai/gpt-oss-120b"},
                             "Project facts", "high", "Planner role", Estimate.model_json_schema(), 32768)
        options = client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(options["reasoning_effort"], "high")
        self.assertEqual(options["response_format"], {"type": "json_object"})
        self.assertEqual(options["max_completion_tokens"], 32768)
        self.assertIn('"materials"', options["messages"][1]["content"])


class QuantityTests(unittest.TestCase):
    def estimate(self, method, unit, inputs, waste=0, round_up=False):
        value = copy.deepcopy(ESTIMATE)
        item = value["materials"][0]
        item.update(unit=unit, waste_percent=float(waste), round_up=round_up,
                    calculation={"method": method, "inputs": [
                        {"name": name, "value": float(number), "unit": input_unit}
                        for name, number, input_unit in inputs]})
        return Estimate.model_validate(value)

    def test_supported_formulas_and_unit_conversions(self):
        dimensions = [("length", 10, "ft"), ("width", 12, "ft")]
        layers = [("layers", 1, "count")]
        wall = dimensions + [("height", 8, "ft"), ("openings_area", 32, "sq_ft")]
        cases = [
            ("rectangle_area", "sq_ft", dimensions + layers, 10, False, 132),
            ("rectangle_area", "sq_ft", [("length", 120, "in"), ("width", 12, "ft")] + layers, 0, False, 120),
            ("rectangle_area", "sq_m", [("length", 200, "cm"), ("width", 3, "m")] + layers, 0, False, 6),
            ("wall_area", "sq_ft", wall, 0, False, 320),
            ("coverage", "gallon", [("area", 400, "sq_ft"), ("layers", 2, "count"), ("coverage", 400, "sq_ft/gallon")], 0, False, 2),
            ("rectangle_coverage", "sheet", [("length", 32, "ft"), ("width", 8, "ft")] + layers + [("coverage", 32, "sq_ft/sheet")], 0, True, 8),
            ("wall_coverage", "gallon", wall + layers + [("coverage", 400, "sq_ft/gallon")], 0, True, 1),
            ("perimeter", "ft", dimensions, 0, False, 44),
            ("count", "piece", [("count", 10, "piece")], 5, True, 11),
            ("count", "piece", [("count", 0, "piece")], 0, True, 0),
        ]
        for method, unit, inputs, waste, rounding, expected in cases:
            with self.subTest(method=method, unit=unit):
                value = self.estimate(method, unit, inputs, waste, rounding)
                check_estimate(value)
                self.assertAlmostEqual(value.materials[0].quantity, expected)
                check_estimate(value)  # Rechecking never reapplies waste to the final quantity.
                self.assertAlmostEqual(value.materials[0].quantity, expected)

    def test_bad_values_missing_fields_and_unknown_methods_are_rejected(self):
        for field, value in [("quantity", -1), ("quantity", float("nan")), ("quantity", float("inf")),
                             ("quantity", "12"), ("quantity", True), ("waste_percent", 101),
                             ("round_up", "true"), ("name", ""), ("unit", "")]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(ESTIMATE)
                data["materials"][0][field] = value
                with self.assertRaises(ValueError):
                    Estimate.model_validate(data)
        for change in ["missing", "extra", "expression"]:
            data = copy.deepcopy(ESTIMATE)
            if change == "missing":
                del data["materials"][0]["unit"]
            elif change == "extra":
                data["materials"][0]["price"] = 10
            else:
                data["materials"][0]["calculation"]["method"] = "eval(length * width)"
            with self.assertRaises(ValueError):
                Estimate.model_validate(data)

    def test_invalid_formula_inputs_and_units_are_rejected(self):
        cases = [
            ("coverage", "gallon", [("area", 400, "sq_ft"), ("layers", 2, "count"), ("coverage", 0, "sq_ft/gallon")]),
            ("coverage", "gallon", [("area", 400, "sq_ft"), ("layers", 2, "count"), ("coverage", 400, "sq_ft")]),
            ("coverage", "sq_ft", [("area", 400, "sq_ft"), ("layers", 2, "count"), ("coverage", 1, "sq_ft/sq_ft")]),
            ("count", "sheet", [("count", 2, "gallon")]),
            ("rectangle_area", "sheet", [("length", 10, "ft"), ("width", 12, "ft"), ("layers", 1, "count")]),
            ("rectangle_area", "sq_ft", [("length", 10, "ft"), ("width", 12, "ft")]),
            ("wall_area", "sq_ft", [("length", 1, "ft"), ("width", 1, "ft"), ("height", 1, "ft"), ("openings_area", 5, "sq_ft")]),
            ("count", "piece", [("count", 1, "piece"), ("count", 2, "piece")]),
        ]
        for method, unit, inputs in cases:
            with self.subTest(method=method, inputs=inputs), self.assertRaises(ValueError):
                check_estimate(self.estimate(method, unit, inputs))


if __name__ == "__main__":
    unittest.main()
