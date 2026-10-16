# This file stores planner jobs, plus the projects users save from them (the saved_projects table, used by services/projects.py).
# Existing MySQL catalog and account code is unchanged.
# The web server and worker must use the same persistent local file.

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .ai_config import WORKFLOW_TIERS, WORKFLOW_VERSION


class LeaseLost(ValueError):
    pass


def database_path():
    # Flask and the worker share this path.
# DATABASE_ENV=test (the MySQL test database) also switches to a separate test file, made by sql/setup_test_database.py, so testing never touches real plans.
    # PLANNER_JOB_DATABASE overrides both (the unit tests use a temporary file).
    data_folder = Path(__file__).resolve().parents[1] / "data"
    if os.getenv("DATABASE_ENV") == "test":
        default = data_folder / "planner_jobs_test.sqlite3"
    else:
        default = data_folder / "planner_jobs.sqlite3"
    return Path(os.getenv("PLANNER_JOB_DATABASE", str(default)))


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=10)
    database.row_factory = sqlite3.Row
    try:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("""CREATE TABLE IF NOT EXISTS planner_jobs (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, submission_key TEXT NOT NULL,
            request_hash TEXT NOT NULL, tier TEXT NOT NULL, status TEXT NOT NULL,
            phase TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
            lease_until REAL NOT NULL DEFAULT 0, worker TEXT,
            data TEXT NOT NULL, UNIQUE(owner, submission_key)
        )""")
        database.execute("CREATE INDEX IF NOT EXISTS planner_queue ON planner_jobs(status, created)")
    # A project the user saved from one planner job.
    # "plan" is a JSON copy of the job's plan at the time it was saved; "crew" is the chosen crew as JSON, or NULL.
        # UNIQUE(owner, job_id) means one job can only ever become one project.
        database.execute("""CREATE TABLE IF NOT EXISTS saved_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, job_id TEXT NOT NULL,
            name TEXT NOT NULL, plan TEXT NOT NULL, plan_version INTEGER NOT NULL,
            crew TEXT, completed INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(owner, job_id)
        )""")
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def decode(row):
    if row is None:
        return None
    job = json.loads(row["data"])
    job.update({"id": row["id"], "owner": row["owner"], "status": row["status"], "phase": row["phase"],
                "created": row["created"], "updated": row["updated"]})
    return job


def submit_job(owner, submission_key, project, tier="fast"):
    settings = WORKFLOW_TIERS.get(tier)
    if settings is None:
        raise ValueError("This planning tier is unavailable.")
    if tier == "pro" and not pro_access_allowed(owner):
        raise ValueError(f"{WORKFLOW_TIERS['pro']['label']} access has not been enabled for this account.")
    if not isinstance(submission_key, str) or not 8 <= len(submission_key) <= 100:
        raise ValueError("Reload the planner before submitting this form.")
    encoded = json.dumps({"project": project, "tier": tier}, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > 20000:
        raise ValueError("Keep project details below 20,000 bytes.")
    request_hash = hashlib.sha256(encoded.encode()).hexdigest()
    owner = str(owner)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"tier": tier, "project": project,
            "config_version": WORKFLOW_VERSION, "specification_version": 1,
            "stages": {}, "attempts": [], "answers": [],
            "result": None, "error": None}
    with connection() as database:
        # One transaction prevents simultaneous submissions from bypassing quotas.
        database.execute("BEGIN IMMEDIATE")
        existing = database.execute(
            "SELECT * FROM planner_jobs WHERE owner = ? AND submission_key = ?",
            (owner, submission_key),
        ).fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError("This submission key already belongs to another request.")
            return decode(existing)
        count = database.execute(
            "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND created >= ?",
            (owner, now - 86400),
        ).fetchone()[0]
        if count >= settings["daily_jobs"]:
            raise ValueError("Your daily planning allowance has been reached.")
        check_queue_capacity(database, owner)
        database.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, phase, created, updated, data) VALUES (?, ?, ?, ?, ?, 'queued', 'Interpreting', ?, ?, ?)",
            (job_id, owner, submission_key, request_hash, tier, now, now, json.dumps(data)),
        )
    return get_job(job_id, owner)


def pro_access_allowed(owner):
    if not str(owner or "").strip():
        return False
    # Off unless a developer opts in with PLANNER_PRO_TEST_ACCESS=true in .env, which gives EVERY account Pro.
    # Never read this from a submitted form.
    if os.getenv("PLANNER_PRO_TEST_ACCESS", "").strip().lower() == "true":
        return True
    allowed = os.getenv("PLANNER_PRO_USER_IDS", "").split(",")
    for user_id in allowed:
        if str(owner) == user_id.strip():
            return True
    return False


def check_queue_capacity(database, owner):
    active = database.execute(
        "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND status IN ('queued', 'running')",
        (owner,),
    ).fetchone()[0]
    if active:
        raise ValueError("Finish or cancel your current planning job first.")
    queued = database.execute(
        "SELECT COUNT(*) FROM planner_jobs WHERE status = 'queued'",
    ).fetchone()[0]
    if queued >= 100:
        raise ValueError("The planner queue is full. Please try again later.")


def check_resume_capacity(database, job):
    if job["config_version"] != WORKFLOW_VERSION:
        raise ValueError("This job uses an older format. Start a new project.")
    if job["tier"] == "pro" and not pro_access_allowed(job["owner"]):
        raise ValueError(f"{WORKFLOW_TIERS['pro']['label']} access has not been enabled for this account.")
    check_queue_capacity(database, job["owner"])


def round_attempts(job):
    # Answering starts a new specification version (a new round).
    # Older attempts stay in job["attempts"] as history but do not use up the new round's budget.
    return [attempt for attempt in job["attempts"]
            if attempt.get("specification_version") == job["specification_version"]]


def get_job(job_id, owner):
    with connection() as database:
        row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                               (job_id, str(owner))).fetchone()
    return decode(row)


def count_jobs(owner):
    with connection() as database:
        return database.execute("SELECT COUNT(*) FROM planner_jobs WHERE owner = ?",
                                (str(owner),)).fetchone()[0]


def list_jobs(owner, limit=20, offset=0):
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM planner_jobs WHERE owner = ? ORDER BY created DESC, id DESC LIMIT ? OFFSET ?",
            (str(owner), limit, offset),
        ).fetchall()
    return [decode(row) for row in rows]


def claim_job(worker):
    now = time.time()
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        # A crashed worker's lease expires; successful saved stages are reused.
        database.execute(
            "UPDATE planner_jobs SET status = 'queued', worker = NULL WHERE status = 'running' AND lease_until < ?",
            (now,),
        )
        active = database.execute("SELECT COUNT(*) FROM planner_jobs WHERE status = 'running'").fetchone()[0]
        if active >= 2:
            return None
        row = database.execute(
            "SELECT * FROM planner_jobs WHERE status = 'queued' ORDER BY created LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        database.execute(
            "UPDATE planner_jobs SET status = 'running', worker = ?, lease_until = ?, updated = ? WHERE id = ?",
            (worker, now + 300, now, row["id"]),
        )
        job = decode(row)
        job["status"] = "running"
        return job


def save_job(job, worker):
    data = job.copy()
    for key in ["id", "owner", "status", "phase", "created", "updated"]:
        data.pop(key, None)
    with connection() as database:
        # The update only matches while this worker still owns the running job.
        changed = database.execute(
            "UPDATE planner_jobs SET data = ?, status = ?, phase = ?, updated = ?, lease_until = ? WHERE id = ? AND worker = ? AND status = 'running'",
            (json.dumps(data, allow_nan=False), job["status"], job["phase"], time.time(),
             time.time() + 300, job["id"], worker),
        ).rowcount
        if changed != 1:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")


def answer_job(job_id, owner, answers, expected_version):
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                               (job_id, str(owner))).fetchone()
        job = decode(row)
        if job is None or job["status"] != "needs_input":
            raise ValueError("This job is not ready to accept answers.")
        if expected_version != job["specification_version"]:
            raise ValueError("These questions have changed. Reload the page.")
        check_resume_capacity(database, job)
        questions = job["questions"]
        if len(answers) != len(questions) or any(len(answer) > 2000 for answer in answers):
            raise ValueError("Submit one answer per question, using at most 2,000 characters each.")
        clarifications = []
        for question, answer in zip(questions, answers):
            clarifications.append({"id": question["id"], "question": question["question"],
                                   "answer": answer.strip() or "Not sure; use reasonable planning assumptions where possible."})
        job["answers"].extend(clarifications)
        job["previous_specification"] = job.get("specification")
        job["specification_version"] += 1
        job["stages"] = {}
        job["result"] = None
        job["error"] = None
        database.execute(
            "UPDATE planner_jobs SET data = ?, status = 'queued', phase = 'Interpreting', worker = NULL, lease_until = 0, updated = ? WHERE id = ?",
            (json.dumps(job), time.time(), job_id),
        )


def retry_job(job_id, owner):
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                               (job_id, str(owner))).fetchone()
        job = decode(row)
        if job is None or job["status"] != "failed":
            raise ValueError("Only a failed job can be retried.")
        settings = WORKFLOW_TIERS[job["tier"]]
        check_resume_capacity(database, job)
        if len(round_attempts(job)) >= settings["max_attempts"]:
            raise ValueError("This job has exhausted its provider attempts. Start a new project.")
        # Finished stages are saved in job["stages"] and reused; the rest run again.
        job["error"] = None
        database.execute(
            "UPDATE planner_jobs SET data = ?, status = 'queued', worker = NULL, lease_until = 0, updated = ? WHERE id = ?",
            (json.dumps(job), time.time(), job_id),
        )


def delete_planner_jobs(owner):
    with connection() as database:
        database.execute("DELETE FROM planner_jobs WHERE owner = ?", (str(owner),))
        database.execute("DELETE FROM saved_projects WHERE owner = ?", (str(owner),))


def cancel_job(job_id, owner):
    with connection() as database:
        changed = database.execute(
            "UPDATE planner_jobs SET status = 'cancelled', phase = 'Cancelled', worker = NULL, updated = ? WHERE id = ? AND owner = ? AND status IN ('queued', 'running', 'needs_input')",
            (time.time(), job_id, str(owner)),
        ).rowcount
    return changed == 1
