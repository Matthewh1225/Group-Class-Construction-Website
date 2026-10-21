# Planner jobs live in SQLite. Saved project helpers are still unfinished.
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
MAX_RUNNING_JOBS = 2          # shared by all workers
MAX_QUEUED_JOBS = 100         # shared by all users
MAX_REQUEST_BYTES = 20000     # bytes
MAX_ANSWER_LENGTH = 2000      # characters per answer
ONE_DAY = 24 * 60 * 60        # seconds

# Other fields go in the JSON data column.
COLUMN_FIELDS = ["id", "owner", "tier", "status", "phase", "created", "updated"]


# Not a ValueError: the routes use those for user input errors.
class LeaseLost(Exception):
    pass


def database_path():
    # The website and worker must use the same file.
    # Test mode uses a separate file.
    data_folder = Path(__file__).resolve().parents[1] / "data"
    if os.getenv("DATABASE_ENV") == "test":
        default = data_folder / "planner_jobs_test.sqlite3"
    else:
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
            phase TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
            lease_until REAL NOT NULL DEFAULT 0, worker TEXT,
            data TEXT NOT NULL, UNIQUE(owner, submission_key)
        )""")
        database.execute("CREATE INDEX IF NOT EXISTS planner_queue ON planner_jobs(status, created)")
        # Plan and crew are saved as JSON.
        # Each user can save a job as one project.
        database.execute("""CREATE TABLE IF NOT EXISTS saved_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, job_id TEXT NOT NULL,
            name TEXT NOT NULL, plan TEXT NOT NULL,
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
    for field in COLUMN_FIELDS:
        job[field] = row[field]
    return job


def encode(job):
    data = job.copy()
    for field in COLUMN_FIELDS:
        data.pop(field, None)
    return json.dumps(data, allow_nan=False)


def pro_access_allowed(owner):
    if not str(owner or "").strip():
        return False
    return has_active_pro(owner)


# The hash catches a submission key reused with different inputs.
def check_submission(owner, submission_key, project, tier, answers):
    if tier not in WORKFLOW_TIERS:
        raise ValueError("This planning tier is unavailable.")
    if tier == "pro" and not pro_access_allowed(owner):
        raise ValueError(f"{WORKFLOW_TIERS['pro']['label']} access has not been enabled for this account.")
    if not isinstance(submission_key, str) or not 8 <= len(submission_key) <= 100:
        raise ValueError("Reload the planner before submitting this form.")
    request_text = json.dumps({"project": project, "tier": tier, "answers": answers}, sort_keys=True, allow_nan=False)
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
# Restarts can include earlier answers.
def submit_job(owner, submission_key, project, tier="fast", answers=None):
    if answers is None:
        answers = []
    request_hash = check_submission(owner, submission_key, project, tier, answers)
    owner = str(owner)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"project": project, "questions": [], "answers": answers,
            "specification": None, "result": None, "error": None}
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
        # Each tier has its own daily limit.
        jobs_today = database.execute(
            "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND tier = ? AND created >= ?",
            (owner, tier, now - ONE_DAY),
        ).fetchone()[0]
        if jobs_today >= WORKFLOW_TIERS[tier]["daily_jobs"]:
            raise ValueError("Your daily planning allowance has been reached.")
        check_queue_capacity(database, owner)
        database.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, phase, created, updated, data) VALUES (?, ?, ?, ?, ?, 'queued', 'Queued', ?, ?, ?)",
            (job_id, owner, submission_key, request_hash, tier, now, now, encode(data)),
        )
    return get_job(job_id, owner)


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
        database.execute(
            "UPDATE planner_jobs SET status = 'failed', phase = 'Interrupted', worker = NULL, data = ?, updated = ? WHERE id = ?",
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
            "UPDATE planner_jobs SET data = ?, status = ?, phase = ?, updated = ?, lease_until = ? WHERE id = ? AND worker = ? AND status = 'running'",
            (encode(job), job["status"], job["phase"], now, now + LEASE_SECONDS, job["id"], worker),
        ).rowcount
        if changed != 1:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")


# Rerun the job with the user's answers.
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
        database.execute(
            "UPDATE planner_jobs SET data = ?, status = 'queued', phase = 'Queued', worker = NULL, lease_until = 0, updated = ? WHERE id = ?",
            (encode(job), time.time(), job_id),
        )


# A fixed key stops repeated clicks from creating extra jobs.
def restart_job(job_id, owner):
    job = get_job(job_id, owner)
    if job is None or job["status"] != "failed":
        raise ValueError("Only a failed plan can be started again.")
    return submit_job(owner, "restart-" + job_id, job["project"], job["tier"], job["answers"])


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
