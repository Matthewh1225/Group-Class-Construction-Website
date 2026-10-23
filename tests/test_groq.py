import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import httpx
from groq import APIResponseValidationError, APIStatusError, AuthenticationError, Groq, InternalServerError

from planning import ai_config, ai_planner, workflow
from planning.schemas import AuditedEstimate, DraftEstimate, Specification


DRAFT = {"materials": [{
    "material_name": "Drywall", "specification": "4 x 8 ft sheets",
    "quantity": 9, "unit": "sheet", "product_id": None,
    "notes": "256 sq ft / 32 sq ft per sheet, plus 10% waste, rounded up.",
}]}
RESPONSE = {
    "id": "test-completion", "object": "chat.completion", "created": 1,
    "model": "openai/gpt-oss-120b", "choices": [{
        "index": 0, "message": {"role": "assistant", "content": json.dumps(DRAFT)},
        "finish_reason": "stop",
    }],
}


# A complete answer from the auditor, used by the fallback tests.
AUDITED = {"summary": "Room", "notes": [], "materials": DRAFT["materials"],
           "crew": {"days": [1, 2], "members": [{"role": "general", "workers": 1, "days": [1, 2]}]}}


class GroqTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.responses = []

        def respond(request):
            self.requests.append(json.loads(request.content))
            status, body = self.responses.pop(0)
            return httpx.Response(status, json=body)

        client = Groq(api_key="test-secret", http_client=httpx.Client(
            transport=httpx.MockTransport(respond)))
        self.addCleanup(client.close)
        models = patch.dict(ai_planner.AI_MODELS, {"gpt_oss": {
            "provider": "groq", "model": "openai/gpt-oss-120b", "client": client,
        }})
        models.start()
        self.addCleanup(models.stop)
        delay = patch.object(workflow.time, "sleep")
        self.sleep = delay.start()
        self.addCleanup(delay.stop)

    def stage(self, tier="standard", role="planner"):
        return workflow.run_stage(tier, role, DraftEstimate, {
            "project": {"description": "Drywall a room"}, "answers": [], "details": [],
        }, ai_config.PLANNER_PROMPT)

    def test_groq_tiers_send_schema_and_keep_settings(self):
        for tier, role in (("fast", "planner"), ("standard", "planner"), ("pro", "second_planner")):
            with self.subTest(tier=tier):
                self.responses.append((200, RESPONSE))
                self.assertEqual(self.stage(tier, role), DRAFT)
                request = self.requests[-1]
                settings = ai_config.WORKFLOW_TIERS[tier][role]
                self.assertEqual(request["model"], "openai/gpt-oss-120b")
                self.assertEqual(request["reasoning_effort"], settings["reasoning"])
                self.assertEqual(request["max_completion_tokens"], settings["output_tokens"])
                self.assertEqual(request["temperature"], 0.5)
                self.assertNotIn("reasoning_format", request)
                self.assertNotIn("max_tokens", request)
                self.assertEqual(request["messages"][0], {
                    "role": "system", "content": ai_config.PLANNER_PROMPT,
                })
                schema = DraftEstimate.model_json_schema()
                self.assertEqual(request["response_format"], {
                    "type": "json_schema", "json_schema": {
                        "name": "DraftEstimate", "strict": True, "schema": schema,
                    },
                })
                for record in (schema, schema["$defs"]["Material"]):
                    self.assertFalse(record["additionalProperties"])
                    self.assertEqual(set(record["required"]), set(record["properties"]))
        self.assertEqual(len(self.requests), 3)

    def test_prompts_name_the_inputs_they_receive(self):
        for name in ("project", "answers", "details", "problem_with_last_answer"):
            self.assertIn(name, ai_config.SHARED_RULES)
        self.assertNotIn("catalog", ai_config.ESTIMATE_RULES)
        self.assertNotIn("catalog", ai_config.PLANNER_PROMPT)
        self.assertIn("product_id to null for every material", ai_config.PLANNER_PROMPT)
        for name in ("catalog", "product_id", "estimates", "available_crew_roles", "hours_per_day",
                     "max_workers_per_role", "max_working_days"):
            self.assertIn(name, ai_config.AUDITOR_PROMPT)
        self.assertIn("questions", ai_config.INTERPRETER_PROMPT)

    def test_groq_json_failure_gets_feedback_without_private_data(self):
        details = {
            "code": "json_validate_failed", "type": "invalid_request_error",
            "message": "test-secret", "failed_generation": "private project content",
        }
        for body in (details, {"error": details}):
            with self.subTest(nested="error" in body):
                self.responses.extend([(400, body), (200, RESPONSE)])
                with self.assertLogs(workflow.logger, level="WARNING") as logs:
                    self.assertEqual(self.stage(), DRAFT)
                retry = json.loads(self.requests[-1]["messages"][1]["content"])
                self.assertIn("JSON schema", retry["problem_with_last_answer"])
                self.assertEqual(retry["project"], {"description": "Drywall a room"})
                log = "\n".join(logs.output)
                for expected in ("planner", "gpt_oss", "JSON schema"):
                    self.assertIn(expected, log)
                for private in ("test-secret", "private project content", "failed_generation"):
                    self.assertNotIn(private, log)
                    self.assertNotIn(private, retry["problem_with_last_answer"])
        self.assertEqual(len(self.requests), 4)

    def test_repeated_json_failure_stops_after_two_attempts(self):
        self.responses.extend([(400, {"error": {"code": "json_validate_failed"}})] * 2)
        with self.assertRaisesRegex(workflow.PlanningError, "did not match the required JSON schema"):
            self.stage()
        self.assertEqual(len(self.requests), 2)

    def test_invalid_request_is_not_treated_as_bad_json(self):
        self.responses.append((400, {"error": {"code": "invalid_request_error"}}))
        with self.assertRaisesRegex(workflow.PlanningError, "provider rejected the request"):
            self.stage()
        self.assertEqual(len(self.requests), 1)

    def test_bad_answers_and_cutoffs_retry_without_accepting_partial_results(self):
        bad_materials = [
            {**DRAFT["materials"][0], "quantity": "9"},
            {**DRAFT["materials"][0], "quantity": None},
            {**DRAFT["materials"][0], "notes": ["Use nine sheets"]},
        ]
        answers = []
        for material in bad_materials:
            answers.append(json.dumps({"materials": [material]}))
        answers.append("")
        answers.append('{"materials": [')
        answers.append('```json\n' + json.dumps(DRAFT) + '\n```')
        answers.append(json.dumps({**DRAFT, "summary": "Extra field"}))
        answers.append(json.dumps(DRAFT["materials"]))

        # Each answer finishes normally ("stop"); the last one is a valid answer that was cut off.
        cases = []
        for answer in answers:
            cases.append((answer, "stop"))
        cases.append((json.dumps(DRAFT), "length"))
        for answer, finish_reason in cases:
            with self.subTest(answer=answer, finish_reason=finish_reason):
                bad = deepcopy(RESPONSE)
                bad["choices"][0]["message"]["content"] = answer
                bad["choices"][0]["finish_reason"] = finish_reason
                self.responses.extend([(200, bad), (200, RESPONSE)])
                self.assertEqual(self.stage(), DRAFT)
                retry = json.loads(self.requests[-1]["messages"][1]["content"])
                self.assertIn("problem_with_last_answer", retry)
        self.assertEqual(len(self.requests), len(cases) * 2)
        # Bad answers are retried straight away.
        self.sleep.assert_not_called()

    def test_rate_limits_and_server_errors_do_not_get_json_feedback(self):
        for status in (429, 503):
            with self.subTest(status=status):
                self.responses.extend([(status, {"error": {"message": "Unavailable"}}),
                                       (200, RESPONSE)])
                self.sleep.reset_mock()
                self.assertEqual(self.stage(), DRAFT)
                retry = json.loads(self.requests[-1]["messages"][1]["content"])
                self.assertNotIn("problem_with_last_answer", retry)
                self.sleep.assert_called_once_with(workflow.RETRY_DELAY)

    def test_sdk_response_error_is_retried(self):
        response = httpx.Response(200, request=httpx.Request("POST", "https://example.test"))
        error = APIResponseValidationError(response, body={})
        self.assertIsInstance(error, workflow.PROVIDER_ERRORS)
        self.assertNotIn(workflow.error_code(error), workflow.DO_NOT_RETRY)

    def test_account_errors_are_not_repeated_on_the_same_model(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                before = len(self.requests)
                self.responses.append((status, {"error": {"message": "test-secret"}}))
                with self.assertRaisesRegex(workflow.PlanningError, "unavailable") as caught:
                    self.stage()
                self.assertEqual(len(self.requests), before + 1)
                self.assertNotIn("test-secret", str(caught.exception))
                # Nothing to wait for: the same model would fail the same way.
                self.sleep.assert_not_called()

    def test_pro_auditor_uses_its_fallback_for_the_second_try(self):
        response = httpx.Response(401, request=httpx.Request("POST", "https://example.test"))
        error = AuthenticationError("bad key", response=response, body=None)
        with patch.object(workflow, "ask_model", side_effect=[error, json.dumps(AUDITED)]) as ask:
            output = workflow.run_stage("pro", "auditor", AuditedEstimate, {},
                                        ai_config.AUDITOR_PROMPT)
        self.assertEqual(output["crew"]["label"], "AI-estimated crew")
        models = [call.args[0] for call in ask.call_args_list]
        self.assertEqual(models, ["nemotron", "gemini_fallback"])
        # A bad key will not fix itself, so there is no wait before the fallback.
        self.sleep.assert_not_called()
        # The provider's fault is not the AI's, so no feedback is sent.
        self.assertNotIn("problem_with_last_answer", json.loads(ask.call_args.args[1]))

    def test_pro_auditor_waits_before_the_fallback_when_the_error_may_clear_up(self):
        response = httpx.Response(503, request=httpx.Request("POST", "https://example.test"))
        error = InternalServerError("busy", response=response, body=None)
        with patch.object(workflow, "ask_model", side_effect=[error, json.dumps(AUDITED)]) as ask:
            workflow.run_stage("pro", "auditor", AuditedEstimate, {}, ai_config.AUDITOR_PROMPT)
        models = [call.args[0] for call in ask.call_args_list]
        self.assertEqual(models, ["nemotron", "gemini_fallback"])
        self.sleep.assert_called_once_with(workflow.RETRY_DELAY)

    def test_account_and_request_errors_never_wait_before_the_fallback(self):
        for status in workflow.DO_NOT_RETRY:
            with self.subTest(status=status):
                self.sleep.reset_mock()
                response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
                error = APIStatusError("rejected", response=response, body=None)
                with patch.object(workflow, "ask_model", side_effect=[error, json.dumps(AUDITED)]) as ask:
                    workflow.run_stage("pro", "auditor", AuditedEstimate, {}, ai_config.AUDITOR_PROMPT)
                self.assertEqual([call.args[0] for call in ask.call_args_list], ["nemotron", "gemini_fallback"])
                self.sleep.assert_not_called()

    def test_pro_auditor_bad_answer_is_retried_on_the_fallback_without_waiting(self):
        with patch.object(workflow, "ask_model", side_effect=["{}", json.dumps(AUDITED)]) as ask:
            workflow.run_stage("pro", "auditor", AuditedEstimate, {}, ai_config.AUDITOR_PROMPT)
        models = [call.args[0] for call in ask.call_args_list]
        self.assertEqual(models, ["nemotron", "gemini_fallback"])
        self.assertIn("problem_with_last_answer", json.loads(ask.call_args.args[1]))
        self.sleep.assert_not_called()

    def test_provider_errors_on_both_tries_wait_once_then_fail(self):
        self.responses.extend([(503, {"error": {"message": "Unavailable"}})] * 2)
        with self.assertRaisesRegex(workflow.PlanningError, "request failed or timed out"):
            self.stage()
        self.assertEqual(len(self.requests), 2)
        # No wait after the last try.
        self.sleep.assert_called_once_with(workflow.RETRY_DELAY)

    def test_missing_api_key_fails_without_a_request(self):
        with patch.dict(ai_planner.AI_MODELS["gpt_oss"], {"client": None}):
            with self.assertRaisesRegex(workflow.PlanningError, "gpt_oss AI model is not configured"):
                self.stage()
        self.assertEqual(self.requests, [])
        self.sleep.assert_not_called()
        # Pro's auditor still gets its fallback model.
        gemini_answer = {"text": "{}", "finish_reason": "STOP"}
        with patch.dict(ai_planner.AI_MODELS["nemotron"], {"client": None}):
            with patch.dict(ai_planner.AI_MODELS["gemini_fallback"], {"client": object()}):
                with patch.object(ai_planner, "call_gemini", return_value=gemini_answer) as gemini:
                    with self.assertRaises(workflow.PlanningError):
                        workflow.run_stage("pro", "auditor", AuditedEstimate, {}, "")
        self.assertEqual(gemini.call_count, 1)
        # A missing key is not a provider error, so there is no wait before the fallback.
        self.sleep.assert_not_called()

    def test_interpreter_feedback_does_not_ask_for_material_quantities(self):
        good = {"details": ["A room"], "questions": []}
        with patch.object(workflow, "ask_model", side_effect=["{}", json.dumps(good)]) as ask:
            self.assertEqual(workflow.run_stage(
                "fast", "interpreter", Specification, {}, ai_config.INTERPRETER_PROMPT), good)
        feedback = json.loads(ask.call_args.args[1])["problem_with_last_answer"]
        self.assertIn("details", feedback)
        self.assertIn("questions", feedback)
        self.assertNotIn("material", feedback)
        self.assertNotIn("quantity", feedback)


if __name__ == "__main__":
    unittest.main()
