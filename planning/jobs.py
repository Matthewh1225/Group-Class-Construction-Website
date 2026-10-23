# Planner jobs and saved projects are stored in SQLite, not MySQL.
# Answering questions requeues a job; restarting a failed job creates a new one.

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

from services.subscriptions import has_active_pro

from .ai_config import WORKFLOW_TIERS

LEASE_SECONDS = 15 * 60       # seconds before an unsaved job is interrupted
MAX_RUNNING_JOBS = 2
MAX_QUEUED_JOBS = 100
MAX_REQUEST_BYTES = 20000
MAX_ANSWER_LENGTH = 2000
ONE_DAY = 24 * 60 * 60# seconds

# Other fields go in the JSON data column.
COLUMN_FIELDS = ["id", "owner", "tier", "status", "created", "updated"]


# Not a ValueError: the routes use those for user input errors.
class LeaseLost(Exception):
    pass


def database_path():
    # The website and worker must use the same file.
    data_folder = Path(__file__).resolve().parents[1] / "data"
    default = data_folder / "planner_jobs.sqlite3"
    return Path(os.getenv("PLANNER_JOB_DATABASE", str(default)))


# Commit when the with block finishes; roll back if it fails.
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
            created REAL NOT NULL, updated REAL NOT NULL,
            lease_until REAL NOT NULL DEFAULT 0, worker TEXT,
            data TEXT NOT NULL, UNIQUE(owner, submission_key)
        )""")
        database.execute("CREATE INDEX IF NOT EXISTS planner_queue ON planner_jobs(status, created)")
        # Saved projects link to the original job; plan remains for older saved records.
        database.execute("""CREATE TABLE IF NOT EXISTS saved_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, job_id TEXT NOT NULL,
            name TEXT NOT NULL, plan TEXT NOT NULL,
            crew TEXT, completed INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(owner, job_id)
        )""")
        database.execute("""CREATE TABLE IF NOT EXISTS crew_cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL, crew TEXT NOT NULL,
            UNIQUE(owner, crew)
        )""")
        with database:
            yield database
    finally:
        database.close()


def decode(row):
    if row is None:
        return None
    job = json.loads(row["data"])
    for field in COLUMN_FIELDS:
        job[field] = row[field]
    return job


def encode(job):
    data = job.copy()
    for field in COLUMN_FIELDS:
        data.pop(field, None)
    return json.dumps(data, allow_nan=False)


def pro_access_allowed(owner):
    if not owner:
        return False
    return has_active_pro(owner)


def pending_stages(tier):
    stages = {"interpreter": "pending", "planner": "pending"}
    if tier == "pro":
        stages["second_planner"] = "pending"
    stages["auditor"] = "pending"
    return stages


# Older jobs may not have stage details.
def stop_running_stages(job, new_state):
    for stage, state in job.get("stages", {}).items():
        if state == "processing":
            job["stages"][stage] = new_state


# The hash catches a submission key reused with different inputs.
def check_submission(owner, submission_key, project, tier, answers):
    if tier not in WORKFLOW_TIERS:
        raise ValueError("This planning tier is unavailable.")
    if tier == "pro" and not pro_access_allowed(owner):
        raise ValueError(f"{WORKFLOW_TIERS['pro']['label']} access has not been enabled for this account.")
    if not isinstance(submission_key, str) or not 8 <= len(submission_key) <= 100:
        raise ValueError("Reload the planner before submitting this form.")
    submission = {"project": project, "tier": tier, "answers": answers}
    request_text = json.dumps(submission, sort_keys=True, allow_nan=False)
    if len(request_text.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError(f"Keep project details below {MAX_REQUEST_BYTES:,} bytes.")
    return hashlib.sha256(request_text.encode()).hexdigest()


def check_queue_capacity(database, owner):
    active = database.execute(
        "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND status IN ('queued', 'running')",
        (owner,),
    ).fetchone()[0]
    if active:
        raise ValueError("Finish or cancel your current planning job first.")
    queued = database.execute("SELECT COUNT(*) FROM planner_jobs WHERE status = 'queued'").fetchone()[0]
    if queued >= MAX_QUEUED_JOBS:
        raise ValueError("The planner queue is full. Please try again later.")


# Reusing a submission key returns the first job.
def submit_job(owner, submission_key, project, tier="fast", answers=None):
    if answers is None:
        answers = []
    request_hash = check_submission(owner, submission_key, project, tier, answers)
    owner = str(owner)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"project": project, "questions": [], "answers": answers,
            "specification": None, "result": None, "error": None,
            "stages": pending_stages(tier)}
    with connection() as database:
        # Lock while checking limits so two requests cannot slip through together.
        database.execute("BEGIN IMMEDIATE")
        existing = database.execute(
            "SELECT * FROM planner_jobs WHERE owner = ? AND submission_key = ?",
            (owner, submission_key),
        ).fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError("This submission key already belongs to another request.")
            return decode(existing)
        jobs_today = database.execute(
            "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND tier = ? AND created >= ?",
            (owner, tier, now - ONE_DAY),
        ).fetchone()[0]
        if jobs_today >= WORKFLOW_TIERS[tier]["daily_jobs"]:
            raise ValueError("Your daily planning allowance has been reached.")
        check_queue_capacity(database, owner)
        database.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, created, updated, data) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)",
            (job_id, owner, submission_key, request_hash, tier, now, now, encode(data)),
        )
        return find_job(database, job_id, owner)


def find_job(database, job_id, owner):
    row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                           (job_id, str(owner))).fetchone()
    return decode(row)


def get_job(job_id, owner):
    with connection() as database:
        return find_job(database, job_id, owner)


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


# Wait for the time limit: another worker may still be running the job.
# Interrupted jobs fail so the user can restart them.
def fail_interrupted_jobs(database, now):
    expired_rows = database.execute(
        "SELECT * FROM planner_jobs WHERE status = 'running' AND lease_until < ?", (now,)
    ).fetchall()
    for row in expired_rows:
        job = decode(row)
        job["error"] = "Planning was interrupted before it finished."
        stop_running_stages(job, "failed")
        database.execute(
            "UPDATE planner_jobs SET status = 'failed', worker = NULL, data = ?, updated = ? WHERE id = ?",
            (encode(job), now, row["id"]),
        )


def claim_job(worker):
    now = time.time()
    with connection() as database:
        # Lock before picking a job so two workers cannot take the same one.
        database.execute("BEGIN IMMEDIATE")
        fail_interrupted_jobs(database, now)
        running = database.execute("SELECT COUNT(*) FROM planner_jobs WHERE status = 'running'").fetchone()[0]
        if running >= MAX_RUNNING_JOBS:
            return None
        row = database.execute(
            "SELECT * FROM planner_jobs WHERE status = 'queued' ORDER BY created LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        database.execute(
            "UPDATE planner_jobs SET status = 'running', worker = ?, lease_until = ?, updated = ? WHERE id = ?",
            (worker, now + LEASE_SECONDS, now, row["id"]),
        )
        job = decode(row)
        job["status"] = "running"
        return job


def save_job(job, worker):
    now = time.time()
    with connection() as database:
        # Only the worker still assigned to the running job can save it.
        changed = database.execute(
            "UPDATE planner_jobs SET data = ?, status = ?, updated = ?, lease_until = ? WHERE id = ? AND worker = ? AND status = 'running'",
            (encode(job), job["status"], now, now + LEASE_SECONDS, job["id"], worker),
        ).rowcount
        if changed != 1:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")


def answer_job(job_id, owner, answers):
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        job = find_job(database, job_id, owner)
        if job is None or job["status"] != "needs_input":
            raise ValueError("This plan is not waiting for answers.")
        if len(answers) != len(job["questions"]) or any(len(answer) > MAX_ANSWER_LENGTH for answer in answers):
            raise ValueError(f"Submit one answer per question, using at most {MAX_ANSWER_LENGTH:,} characters each.")
        check_queue_capacity(database, job["owner"])
        job["answers"] = []
        for question, answer in zip(job["questions"], answers):
            answer = answer.strip()
            if not answer:
                answer = "Not answered"
            job["answers"].append({"question": question, "answer": answer})
        job["questions"] = []
        job["stages"] = pending_stages(job["tier"])
        database.execute(
            "UPDATE planner_jobs SET data = ?, status = 'queued', worker = NULL, lease_until = 0, updated = ? WHERE id = ?",
            (encode(job), time.time(), job_id),
        )


# A fixed key stops repeated clicks from creating extra jobs.
def restart_job(job_id, owner):
    job = get_job(job_id, owner)
    if job is None or job["status"] != "failed":
        raise ValueError("Only failed plans can be started again.")
    return submit_job(owner, "restart-" + job_id, job["project"], job["tier"], job["answers"])


def delete_planner_jobs(owner):
    with connection() as database:
        database.execute("DELETE FROM crew_cart WHERE owner = ?", (str(owner),))
        database.execute("DELETE FROM planner_jobs WHERE owner = ?", (str(owner),))
        database.execute("DELETE FROM saved_projects WHERE owner = ?", (str(owner),))


def cancel_job(job_id, owner):
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        job = find_job(database, job_id, owner)
        if job is None or job["status"] not in ("queued", "running", "needs_input"):
            return False
        stop_running_stages(job, "cancelled")
        changed = database.execute(
            "UPDATE planner_jobs SET status = 'cancelled', worker = NULL, data = ?, updated = ? WHERE id = ? AND owner = ? AND status IN ('queued', 'running', 'needs_input')",
            (encode(job), time.time(), job_id, str(owner)),
        ).rowcount
    return changed == 1
