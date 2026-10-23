import unittest
from unittest.mock import Mock, patch

import httpx
from mysql.connector import Error as MySQLError

from planning import ai_planner, jobs, worker, workflow
from planning.schemas import PlanningError, Specification


class PlannerNoRetryTests(unittest.TestCase):
    def test_invalid_answer_stops_after_one_request(self):
        with patch.object(workflow, "ask_model", return_value="{}") as ask_model:
            with self.assertRaisesRegex(PlanningError, "interpreter step failed"):
                workflow.run_stage("fast", "interpreter", Specification, {}, "instructions")
        self.assertEqual(ask_model.call_count, 1)

    def test_provider_error_stops_after_one_request(self):
        with patch.object(workflow, "ask_model", side_effect=httpx.ConnectError("offline")) as ask_model:
            with self.assertRaisesRegex(PlanningError, "AI request failed or timed out"):
                workflow.run_stage("fast", "interpreter", Specification, {}, "instructions")
        self.assertEqual(ask_model.call_count, 1)

    def test_failed_pro_planner_fails_job_without_auditing(self):
        for failed_role in ("planner", "second_planner"):
            with self.subTest(failed_role=failed_role):
                job = {
                    "id": "test-job", "owner": "test-user", "tier": "pro",
                    "project": {"description": "shed"}, "answers": [],
                    "stages": jobs.pending_stages("pro"), "status": "running",
                    "result": None, "error": None,
                }
                called_roles = []

                def stage_result(tier, role, record_type, inputs, instructions):
                    called_roles.append(role)
                    if role == failed_role:
                        raise PlanningError(f"The {role} step failed: provider unavailable.")
                    if role == "interpreter":
                        return {"details": [], "questions": []}
                    return {"materials": []}

                with patch.object(worker, "claim_job", return_value=job), \
                     patch.object(worker, "save_job"), \
                     patch.object(workflow, "pro_access_allowed", return_value=True), \
                     patch.object(workflow, "run_stage", side_effect=stage_result), \
                     patch.object(workflow, "get_planner_catalog") as catalog:
                    worker.process_one("test-worker")

                self.assertEqual(job["status"], "failed")
                self.assertIn("provider unavailable", job["error"])
                self.assertEqual(job["stages"][failed_role], "failed")
                self.assertEqual(job["stages"]["auditor"], "pending")
                self.assertIsNone(job["result"])
                self.assertNotIn("auditor", called_roles)
                catalog.assert_not_called()
                if failed_role == "planner":
                    self.assertNotIn("second_planner", called_roles)

    def test_successful_pro_run_keeps_both_estimates(self):
        job = {
            "owner": "test-user", "tier": "pro", "project": {"description": "shed"},
            "answers": [], "stages": jobs.pending_stages("pro"), "status": "running",
        }
        result = {"materials": ["final materials"], "crew": {"members": []}}
        stage_outputs = [
            {"details": [], "questions": []},
            {"materials": ["first draft"]},
            {"materials": ["second draft"]},
            result,
        ]
        with patch.object(workflow, "pro_access_allowed", return_value=True), \
             patch.object(workflow, "run_stage", side_effect=stage_outputs) as run_stage, \
             patch.object(workflow, "get_planner_catalog", return_value=[]):
            workflow.run_workflow(job, lambda value: None)

        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["result"], result)
        self.assertTrue(all(state == "done" for state in job["stages"].values()))
        roles = [call.args[1] for call in run_stage.call_args_list]
        self.assertEqual(roles, ["interpreter", "planner", "second_planner", "auditor"])
        auditor_inputs = run_stage.call_args_list[-1].args[3]
        self.assertEqual(auditor_inputs["estimates"], stage_outputs[1:3])

    def test_catalog_failure_stops_at_auditor(self):
        job = {
            "owner": "test-user", "tier": "fast", "project": {"description": "shed"},
            "answers": [], "stages": jobs.pending_stages("fast"), "status": "running",
        }
        stage_outputs = [{"details": [], "questions": []}, {"materials": []}]
        with patch.object(workflow, "run_stage", side_effect=stage_outputs) as run_stage, \
             patch.object(workflow, "get_planner_catalog", side_effect=MySQLError("offline")):
            with self.assertRaisesRegex(PlanningError, "product catalog could not be loaded"):
                workflow.run_workflow(job, lambda value: None)
        self.assertEqual(run_stage.call_count, 2)
        self.assertEqual(job["stages"]["auditor"], "processing")

    def test_manual_restart_submits_original_request(self):
        failed = {"id": "first-job", "status": "failed", "tier": "fast",
                  "project": {"description": "shed"}, "answers": []}
        with patch.object(jobs, "get_job", return_value=failed), \
             patch.object(jobs, "submit_job", return_value={"id": "new-job"}) as submit:
            restarted = jobs.restart_job("first-job", "test-user")
        self.assertEqual(restarted["id"], "new-job")
        submit.assert_called_once_with("test-user", "restart-first-job", failed["project"], "fast", [])

    def test_mysql_save_failure_stops_worker_without_marking_failed(self):
        job = {"id": "test-job"}
        with patch.object(worker, "claim_job", return_value=job), \
             patch.object(worker, "run_workflow", side_effect=MySQLError("offline")), \
             patch.object(worker, "mark_failed") as mark_failed:
            with self.assertRaises(MySQLError):
                worker.process_one("test-worker")
        mark_failed.assert_not_called()

    def test_client_requests_disable_sdk_retries(self):
        gemini_client = Mock()
        gemini_client.models.generate_content.return_value = Mock(candidates=[], text="{}")
        ai_planner.call_gemini({"client": gemini_client, "model": "gemini"},
                               "prompt", "low", "instructions", {}, 100)
        gemini_config = gemini_client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(gemini_config["http_options"]["retry_options"]["attempts"], 1)

        groq_client = Mock()
        groq_client.with_options.return_value.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="{}"), finish_reason="stop")]
        )
        ai_planner.call_groq({"client": groq_client, "model": "groq"},
                             "prompt", "low", "instructions", {"title": "Test"}, 100)
        groq_client.with_options.assert_called_once_with(max_retries=0)

        router_client = Mock()
        router_client.chat.send.return_value = Mock(
            choices=[Mock(message=Mock(content="{}"), finish_reason="stop")]
        )
        ai_planner.call_openrouter({"client": router_client, "model": "router"},
                                   "prompt", "low", "instructions", {}, 100)
        options = router_client.chat.send.call_args.kwargs
        self.assertIsNone(options["retries"])
        self.assertFalse(options["provider"]["allow_fallbacks"])


if __name__ == "__main__":
    unittest.main()
