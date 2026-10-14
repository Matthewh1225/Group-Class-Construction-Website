import ast
import importlib.util
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import bcrypt
from flask import render_template
from google.genai import types

from app import app
from planning.contracts import Estimate
import planning.ai_planner as ai
import routes.auth as auth_routes
import routes.planner as planner_routes
from utils.database import database_cursor
from utils.passwords import verify_password_hash
from utils.rate_limits import limiter


ROOT = Path(__file__).resolve().parents[1]
PLAN = {
    "project_type": "custom", "summary": "Rendering fixture",
    "materials": [{"name": "Test material", "category": "Test", "subcategory": "Test",
                   "product_type": "Test", "specification": "", "quantity": 3,
                   "unit": "pieces", "notes": ""}],
    "questions": [], "assumptions": [], "corrections": [],
}


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.dict(app.config, TESTING=True, SECRET_KEY="audit-test")
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.limit_patch = patch.object(limiter, "enabled", False)
        self.limit_patch.start()
        self.addCleanup(self.limit_patch.stop)
        self.client = app.test_client()

    def response(self, questions=None):
        plan = {**PLAN, "questions": questions or []}
        return {"text": json.dumps(plan), "plan": plan, "steps": [], "elapsed_seconds": 1.0}

    def test_optional_provider_keys_are_not_required_to_import_planner(self):
        with patch.dict(os.environ, {}, clear=True):
            spec = importlib.util.spec_from_file_location("planning.audit_without_keys", ROOT / "planning" / "ai_planner.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        for model in module.AI_MODELS.values():
            self.assertIsNone(model["client"])
        for model_name in module.AI_MODELS:
            with self.subTest(model=model_name):
                with self.assertRaisesRegex(ValueError, "API key"):
                    module.get_ai_response(model_name, "No network request")

    def test_configured_provider_still_receives_its_existing_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}, clear=True), patch("groq.Groq") as client:
            spec = importlib.util.spec_from_file_location("planning.audit_with_key", ROOT / "planning" / "ai_planner.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            client.assert_called_once_with(api_key="test-only-key")
            self.assertIs(module.AI_MODELS["groq"]["client"], client.return_value)

    def test_gemini_adapter_uses_supported_sdk_response_fields(self):
        client = MagicMock()
        model = {"client": client, "model": "test-model"}
        ai.call_gemini(model, "Test prompt", "low", "Test instructions", Estimate.model_json_schema())
        options = client.models.generate_content.call_args.kwargs
        config = types.GenerateContentConfig.model_validate(options["config"])
        self.assertEqual(options["model"], "test-model")
        self.assertEqual(options["contents"], "Test prompt")
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_json_schema, Estimate.model_json_schema())

    def test_password_verification_rejects_missing_and_malformed_values(self):
        for password, stored_hash in [("Ab1!", None), (None, "hash"), ("Ab1!", 1), ([], "hash"), ("Ab1!", "not-a-hash")]:
            with self.subTest(password_type=type(password).__name__, hash_type=type(stored_hash).__name__):
                self.assertFalse(verify_password_hash(password, stored_hash))

    def test_password_verification_keeps_valid_hash_behavior(self):
        stored_hash = bcrypt.hashpw(b"Ab1!", bcrypt.gensalt(rounds=4)).decode("utf-8")
        self.assertTrue(verify_password_hash("Ab1!", stored_hash))
        self.assertFalse(verify_password_hash("wrong", stored_hash))

    def test_login_with_missing_hash_returns_invalid_credentials(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"password_hash": None}

        @contextmanager
        def fake_cursor():
            yield cursor

        with patch.object(auth_routes, "database_cursor", fake_cursor):
            response = self.client.post("/login", json={"username": "Test user", "password": "Ab1!"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json, {"error": "Invalid username or password."})
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_registration_rejects_invalid_payload_before_mutation(self):
        with patch.object(auth_routes, "create_user") as create:
            for payload in [None, [], "invalid"]:
                response = self.client.post("/register", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json, {"error": "Invalid form data."})
            create.assert_not_called()

    def test_legacy_planner_submission_requires_a_login(self):
        response = self.client.post("/planner", data={"projectMode": "custom", "projectSize": "small", "userInput": "Test request"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_enabled_pro_roles_all_request_high(self):
        from planning.ai_config import WORKFLOW_TIERS
        policy = WORKFLOW_TIERS["pro"]
        self.assertTrue(policy["enabled"])
        for role in ["interpreter", "planner", "second_planner", "auditor", "auditor_fallback"]:
            self.assertEqual(policy[role][1], "high")

    def test_single_call_legacy_workflow_is_removed(self):
        self.assertFalse(hasattr(ai, "plan_project"))
        self.assertFalse(hasattr(ai, "review_plan"))

    def test_tampered_form_token_cannot_submit_a_job(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 17
            session["planner_token"] = "expected-token"
        with patch.object(planner_routes, "submit_job") as submit:
            response = self.client.post("/planner", data={"plannerToken": "tampered-token", "projectMode": "custom"})
        submit.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_material_list_preserves_zero_and_unknown_costs(self):
        with app.test_request_context("/dashboard/projects/1/materials"):
            html = render_template(
                "dashboard/material_list_detail.html", project=None, material_list={"id": 1}, estimated_total=0,
                materials=[{"name": "Zero-cost test", "quantity": 0, "unit": "pieces", "unit_cost": 0, "total_cost": 0},
                           {"name": "Unknown-cost test", "quantity": None, "unit": None, "unit_cost": None, "total_cost": None}],
            )
        self.assertEqual(html.count("<td>0</td>"), 3)
        self.assertEqual(html.count("<td>—</td>"), 4)
        self.assertIn("<strong>0</strong>", html)

    def test_every_template_compiles(self):
        for name in app.jinja_env.list_templates():
            with self.subTest(template=name):
                app.jinja_env.get_template(name)

    def test_all_service_functions_remain_intentional_stubs(self):
        functions = []
        for path in (ROOT / "services").glob("*.py"):
            functions.extend(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef))
        self.assertEqual(len(functions), 37)
        for function in functions:
            with self.subTest(function=function.name):
                self.assertIsNotNone(ast.get_docstring(function))
                self.assertEqual(len(function.body), 2)
                self.assertIsInstance(function.body[1], ast.Pass)

    def test_database_success_commits_and_closes(self):
        connection = MagicMock()
        with patch("mysql.connector.connect", return_value=connection):
            with database_cursor() as cursor:
                self.assertIs(cursor, connection.cursor.return_value.__enter__.return_value)
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once()

    def test_database_failure_rolls_back_and_closes(self):
        connection = MagicMock()
        with patch("mysql.connector.connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "Test failure"):
                with database_cursor():
                    raise RuntimeError("Test failure")
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
