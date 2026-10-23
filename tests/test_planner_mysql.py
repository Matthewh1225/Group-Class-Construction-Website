"""Opt-in integration tests in a new, disposable MySQL database.

Set RUN_MYSQL_TESTS=1. Requires CREATE/DROP DATABASE on the configured server.
The application's database is never used for test rows.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
import uuid

import mysql.connector

from planning import jobs, worker, workflow
from services import cart, projects
from utils.database import database_cursor, database_settings
from utils.users import delete_user_completely


ROOT = Path(__file__).resolve().parents[1]
CREW = {"label": "Shed crew", "days": [2, 3],
        "members": [{"role": "carpenter", "workers": 2, "days": [2, 3]}]}
RESULT = {"summary": "A shed", "notes": [], "crew": CREW, "materials": [
    {"material_name": "Lumber", "quantity": 10, "unit": "piece",
     "specification": "2x4", "notes": "Includes waste", "product_id": None},
]}


@unittest.skipUnless(os.getenv("RUN_MYSQL_TESTS") == "1", "Set RUN_MYSQL_TESTS=1 for isolated MySQL tests")
class PlannerMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_database = "planner_test_" + uuid.uuid4().hex
        cls.admin = mysql.connector.connect(**database_settings(), ssl_disabled=False)
        cls.addClassCleanup(cls.admin.close)
        with cls.admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{cls.test_database}` CHARACTER SET utf8mb4")
        cls.addClassCleanup(cls.drop_database)
        environment = patch.dict(os.environ, {"DB_NAME": cls.test_database})
        environment.start()
        cls.addClassCleanup(environment.stop)
        with database_cursor() as cursor:
            for filename in ("erd_schema.sql", "planner_schema.sql"):
                schema = (ROOT / "sql" / filename).read_text(encoding="utf-8")
                schema = "\n".join(line for line in schema.splitlines() if not line.lstrip().startswith("--"))
                for statement in schema.split(";"):
                    if statement.strip():
                        cursor.execute(statement)

    @classmethod
    def drop_database(cls):
        # This name is generated above, never read from the application settings.
        assert cls.test_database.startswith("planner_test_")
        with cls.admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{cls.test_database}`")

    def setUp(self):
        with database_cursor() as cursor:
            for table in ("crew_cart", "saved_projects", "planner_jobs", "User"):
                cursor.execute(f"DELETE FROM `{table}`")
            for user_id in range(1, 5):
                cursor.execute("""INSERT INTO `User`
                    (id, firstName, email, passkey, dateCreated)
                    VALUES (%s, 'Test', %s, 'unused', CURDATE())""",
                    (user_id, f"test{user_id}@example.invalid"))
            cursor.execute("INSERT INTO Customer (userId) VALUES (1)")

    def submit(self, owner=1, key="submission-key"):
        return jobs.submit_job(owner, key, {"description": "Build a shed", "project_type": "shed"})

    def complete(self):
        self.submit()
        job = jobs.claim_job("worker-one")
        job["status"] = "complete"
        job["result"] = RESULT
        jobs.save_job(job, "worker-one")
        return jobs.get_job(job["id"], 1)

    def test_concurrent_workers_claim_once_and_respect_capacity(self):
        for owner in range(1, 5):
            self.submit(owner)
        barrier = Barrier(6)

        def claim(index):
            barrier.wait(timeout=10)
            return jobs.claim_job(f"worker-{index}")

        with ThreadPoolExecutor(max_workers=6) as pool:
            claimed = [job for job in pool.map(claim, range(6)) if job]
        self.assertEqual(len(claimed), jobs.MAX_RUNNING_JOBS)
        self.assertEqual(len({job["id"] for job in claimed}), len(claimed))
        with database_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM planner_jobs WHERE status = 'running'")
            self.assertEqual(cursor.fetchone()["total"], jobs.MAX_RUNNING_JOBS)

    def test_concurrent_submissions_are_idempotent(self):
        barrier = Barrier(4)

        def submit(index):
            barrier.wait(timeout=10)
            return self.submit()

        with ThreadPoolExecutor(max_workers=4) as pool:
            submitted = list(pool.map(submit, range(4)))
        self.assertEqual(len({job["id"] for job in submitted}), 1)
        self.assertEqual(jobs.count_jobs(1), 1)
        with self.assertRaisesRegex(ValueError, "another request"):
            jobs.submit_job(1, "submission-key", {"description": "Changed"})
        with self.assertRaisesRegex(ValueError, "Finish or cancel"):
            self.submit(key="another-key")

    def test_worker_persists_stages_result_and_project(self):
        job = self.submit()
        outputs = [{"details": [], "questions": []}, {"materials": RESULT["materials"]}, RESULT]
        with patch.object(workflow, "run_stage", side_effect=outputs):
            worker.run_worker(once=True)
        loaded = jobs.get_job(job["id"], 1)
        self.assertEqual(loaded["status"], "complete")
        self.assertEqual(loaded["result"], RESULT)
        self.assertTrue(all(value == "done" for value in loaded["stages"].values()))
        saved_id = projects.save_job_as_project(1, loaded, "My shed")
        self.assertEqual(projects.save_job_as_project(1, loaded, "Duplicate"), saved_id)
        self.assertEqual(projects.count_projects(1), 1)
        saved = projects.get_project_details(saved_id, 1)
        self.assertEqual(saved["plan"]["result"], RESULT)
        self.assertTrue(saved["job_exists"])
        self.assertEqual(projects.get_project_saved_from_job(job["id"], 1)["id"], saved_id)

    def test_questions_cancel_expiry_and_restart(self):
        job = self.submit()
        with patch.object(workflow, "run_stage", return_value={"details": [], "questions": ["Size?"]}):
            worker.process_one("worker-one")
        self.assertEqual(jobs.get_job(job["id"], 1)["status"], "needs_input")
        jobs.answer_job(job["id"], 1, ["10 feet"])
        running = jobs.claim_job("worker-two")
        self.assertEqual(running["answers"], [{"question": "Size?", "answer": "10 feet"}])
        with self.assertRaises(jobs.LeaseLost):
            jobs.save_job(running, "wrong-worker")
        with database_cursor() as cursor:
            cursor.execute("UPDATE planner_jobs SET lease_until = 0 WHERE id = %s", (job["id"],))
        self.assertIsNone(jobs.claim_job("worker-three"))
        self.assertEqual(jobs.get_job(job["id"], 1)["status"], "failed")
        with self.assertRaises(jobs.LeaseLost):
            jobs.save_job(running, "worker-two")
        restarted = jobs.restart_job(job["id"], 1)
        self.assertNotEqual(restarted["id"], job["id"])
        self.assertEqual(restarted["stages"], jobs.pending_stages("fast"))
        self.assertIsNone(restarted["result"])
        running = jobs.claim_job("worker-four")
        self.assertTrue(jobs.cancel_job(running["id"], 1))
        with self.assertRaises(jobs.LeaseLost):
            jobs.save_job(running, "worker-four")
        self.assertFalse(jobs.cancel_job(running["id"], 1))

    def test_projects_and_crews_are_owner_scoped(self):
        job = self.complete()
        saved_id = projects.save_job_as_project(1, job, "Shed")
        self.assertIsNone(jobs.get_job(job["id"], 2))
        self.assertIsNone(projects.get_project_details(saved_id, 2))
        with self.assertRaises(ValueError):
            projects.save_job_as_project(2, job, "Not mine")
        self.assertFalse(projects.rename_project(saved_id, 2, "Not mine"))
        self.assertFalse(projects.save_project_crew(saved_id, 2, CREW))
        self.assertFalse(projects.set_project_completed(saved_id, 2, True))
        self.assertFalse(projects.delete_project(saved_id, 2))
        projects.rename_project(saved_id, 1, "Garden shed")
        projects.save_project_crew(saved_id, 1, CREW)
        self.assertEqual(projects.get_project_details(saved_id, 1)["crew"], CREW)
        projects.set_project_completed(saved_id, 1, True)
        self.assertEqual(len(projects.get_project_list(1, search="GARDEN", status="Completed")), 1)
        self.assertEqual(projects.get_project_list(1, status="Ready"), [])
        projects.set_project_completed(saved_id, 1, False)
        projects.save_project_crew(saved_id, 1, None)
        self.assertIsNone(projects.get_project_details(saved_id, 1)["crew"])
        cart.add_crew(1, json.dumps(CREW))
        cart.add_crew(1, json.dumps(CREW, sort_keys=True))
        crews = cart.get_cart_crews(1)
        self.assertEqual(len(crews), 1)
        self.assertEqual(crews[0]["estimate"]["workers"], 2)
        self.assertEqual(cart.get_cart_crews(2), [])
        self.assertFalse(cart.remove_crew(2, crews[0]["id"]))
        self.assertTrue(cart.remove_crew(1, crews[0]["id"]))
        self.assertTrue(projects.delete_project(saved_id, 1))
        self.assertIsNotNone(jobs.get_job(job["id"], 1))

    def test_delete_account_rolls_back_all_tables_on_failure(self):
        job = self.complete()
        projects.save_job_as_project(1, job, "Shed")
        cart.add_crew(1, json.dumps(CREW))
        with self.assertRaises(mysql.connector.Error):
            with database_cursor() as cursor:
                cursor.execute("DELETE FROM `User` WHERE id = 1")
                for table in ("planner_jobs", "saved_projects", "crew_cart"):
                    cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE owner = 1")
                    self.assertEqual(cursor.fetchone()["total"], 0)
                raise mysql.connector.Error("Test rollback")
        self.assertEqual(jobs.count_jobs(1), 1)
        self.assertEqual(projects.count_projects(1), 1)
        self.assertEqual(len(cart.get_cart_crews(1)), 1)
        self.assertTrue(delete_user_completely(1))
        self.assertEqual(jobs.count_jobs(1), 0)
        self.assertEqual(projects.count_projects(1), 0)
        self.assertEqual(cart.get_cart_crews(1), [])
        with database_cursor() as cursor:
            cursor.execute("SELECT id FROM `User` WHERE id = 1")
            self.assertIsNone(cursor.fetchone())

    def test_foreign_keys_reject_invalid_users_and_job_links(self):
        job = self.complete()
        saved_id = projects.save_job_as_project(1, job, "Shed")
        with self.assertRaises(mysql.connector.IntegrityError):
            self.submit(owner=999)
        with self.assertRaises(mysql.connector.IntegrityError):
            cart.add_crew(999, json.dumps(CREW))
        for column, value in (("owner", 2), ("owner", 999), ("job_id", uuid.uuid4().hex)):
            with self.subTest(column=column, value=value):
                with self.assertRaises(mysql.connector.IntegrityError):
                    with database_cursor() as cursor:
                        cursor.execute(f"UPDATE saved_projects SET {column} = %s WHERE id = %s",
                                       (value, saved_id))
        self.assertEqual(projects.get_project_details(saved_id, 1)["job_id"], job["id"])

    def test_deleting_job_cascades_to_saved_project_only(self):
        job = self.complete()
        saved_id = projects.save_job_as_project(1, job, "Shed")
        cart.add_crew(1, json.dumps(CREW))
        with database_cursor() as cursor:
            cursor.execute("DELETE FROM planner_jobs WHERE id = %s", (job["id"],))
        self.assertIsNone(projects.get_project_details(saved_id, 1))
        self.assertEqual(len(cart.get_cart_crews(1)), 1)
        with database_cursor() as cursor:
            cursor.execute("SELECT id FROM `User` WHERE id = 1")
            self.assertIsNotNone(cursor.fetchone())

    def test_upgrade_adds_the_same_foreign_keys(self):
        # Recreate the original column types and missing constraints in this test DB.
        with database_cursor() as cursor:
            cursor.execute("ALTER TABLE saved_projects DROP FOREIGN KEY saved_projects_job_fk")
            for table in ("saved_projects", "crew_cart", "planner_jobs"):
                cursor.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {table}_user_fk, MODIFY owner VARCHAR(100) NOT NULL")
            cursor.execute("ALTER TABLE planner_jobs DROP INDEX planner_owner_job")
            schema = (ROOT / "sql" / "add_planner_relations.sql").read_text(encoding="utf-8")
            for statement in schema.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute("""SELECT COUNT(*) AS total FROM information_schema.REFERENTIAL_CONSTRAINTS
                              WHERE CONSTRAINT_SCHEMA = DATABASE()
                              AND TABLE_NAME IN ('planner_jobs', 'saved_projects', 'crew_cart')""")
            self.assertEqual(cursor.fetchone()["total"], 4)
        self.test_foreign_keys_reject_invalid_users_and_job_links()

    def test_web_pages_and_crew_actions(self):
        from app import app
        from utils.rate_limits import limiter

        job = self.complete()
        with patch.dict(app.config, {"TESTING": True}), patch.object(limiter, "enabled", False):
            client = app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = 1
                session["csrf_token"] = "test-token"
            for url in ("/planner", "/planner/history", f"/planner/jobs/{job['id']}",
                        f"/planner/jobs/{job['id']}/status", "/dashboard/projects", "/crews"):
                self.assertEqual(client.get(url).status_code, 200, url)
            response = client.post(f"/planner/jobs/{job['id']}/save",
                                   data={"name": "Shed", "csrf_token": "test-token"})
            self.assertEqual(response.status_code, 303)
            saved_id = projects.get_project_saved_from_job(job["id"], 1)["id"]
            response = client.post(f"/dashboard/projects/{saved_id}/crew",
                                   data={"crew": json.dumps(CREW), "csrf_token": "test-token"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get(f"/crews?project_id={saved_id}").status_code, 200)
            self.assertEqual(client.get("/dashboard/projects").status_code, 200)
            response = client.post("/cart/crews/add", data={"crew": json.dumps(CREW), "csrf_token": "test-token"})
            self.assertEqual(response.status_code, 303)
            response = client.get("/cart")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Shed crew", response.data)


if __name__ == "__main__":
    unittest.main()
