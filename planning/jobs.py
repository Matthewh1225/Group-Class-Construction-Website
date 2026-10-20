# This file stores planner jobs, plus the projects users save from them (the saved_projects table, used by services/projects.py).
#
# A job's "data" column is JSON with these keys:
#   project        the user's form inputs (see routes/planner.py build_project)
#   questions      the interpreter's follow-up questions while status is "needs_input", else []
#   answers        [{"question": ..., "answer": ...}] - at most one round
#   specification  the interpreter's summary, details and questions, or None
#   result         the finished plan (format in planning/schemas.py), or None
#   error          a short message when status is "failed", else None
#
# Status goes: queued -> running -> complete / partial / needs_input / failed / cancelled.
# needs_input goes back to queued when the user answers. A failed job is never resumed:
# restart_job starts a new job with the same inputs and answers.

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

LEASE_SECONDS = 15 * 60       # how long a worker may go without saving before its job counts as interrupted
MAX_RUNNING_JOBS = 2          # jobs the worker runs at the same time
MAX_QUEUED_JOBS = 100         # jobs waiting for a worker, from all users together
MAX_REQUEST_BYTES = 20000     # size limit for one job's project details
MAX_ANSWER_LENGTH = 2000      # characters allowed in one answer to a follow-up question
ONE_DAY = 24 * 60 * 60        # seconds, for the daily job allowance

# These job fields have their own database columns. Everything else is stored in the "data" column.
COLUMN_FIELDS = ["id", "owner", "tier", "status", "phase", "created", "updated"]


class LeaseLost(ValueError):
    pass


def database_path():
    # Flask and the worker share this path.
    # DATABASE_ENV=test selects a separate file, so tests never touch real jobs.
    data_folder = Path(__file__).resolve().parents[1] / "data"
    if os.getenv("DATABASE_ENV") == "test":
        default = data_folder / "planner_jobs_test.sqlite3"
    else:
        default = data_folder / "planner_jobs.sqlite3"
    return Path(os.getenv("PLANNER_JOB_DATABASE", str(default)))


# Opens the planner's SQLite file (making the tables if they are missing).
# Saves the changes when the "with" block ends, or undoes them if an error happens.
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
        # "plan" is a JSON copy of the job's tier, project, answers and result; "crew" is the chosen crew as JSON, or NULL.
        # (owner, job_id) means one job can only ever become one project.
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


# Turns a database row into a job dict. Columns override old JSON copies, including tier.
def decode(row):
    if row is None:
        return None
    job = json.loads(row["data"])
    for field in COLUMN_FIELDS:
        job[field] = row[field]
    return job


# Turns a job dict into the JSON text for the data column.
def encode(job):
    data = job.copy()
    for field in COLUMN_FIELDS:
        data.pop(field, None)
    return json.dumps(data, allow_nan=False)


# Pro is only for signed-in users who have an active Pro subscription.
def pro_access_allowed(owner):
    if not str(owner or "").strip():
        return False
    return has_active_pro(owner)


# Raises ValueError if a new job is not allowed.
# Returns a hash of the request, used to spot a submission key being reused for a different request.
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


# Raises ValueError if this user already has a job waiting or running, or if the queue is full.
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


# Adds a new planning job to the queue and returns it. Raises ValueError if a limit is hit.
# Sending the same submission_key twice returns the first job instead of making a second one.
# answers is only given when restarting a job that already had its question round.
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
        # One transaction prevents simultaneous submissions from bypassing the limits.
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
            "SELECT COUNT(*) FROM planner_jobs WHERE owner = ? AND created >= ?",
            (owner, now - ONE_DAY),
        ).fetchone()[0]
        if jobs_today >= WORKFLOW_TIERS[tier]["daily_jobs"]:
            raise ValueError("Your daily planning allowance has been reached.")
        check_queue_capacity(database, owner)
        database.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, phase, created, updated, data) VALUES (?, ?, ?, ?, ?, 'queued', 'Queued', ?, ?, ?)",
            (job_id, owner, submission_key, request_hash, tier, now, now, encode(data)),
        )
    return get_job(job_id, owner)


# Looks up one job, only if it belongs to this owner. Returns None otherwise.
# Takes an open database so it can also be used inside a transaction.
def find_job(database, job_id, owner):
    row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                           (job_id, str(owner))).fetchone()
    return decode(row)


def get_job(job_id, owner):
    with connection() as database:
        return find_job(database, job_id, owner)


# How many jobs this owner has made in total
def count_jobs(owner):
    with connection() as database:
        return database.execute("SELECT COUNT(*) FROM planner_jobs WHERE owner = ?",
                                (str(owner),)).fetchone()[0]


# One page of this owner's jobs, newest first. offset is how many jobs to skip.
def list_jobs(owner, limit=20, offset=0):
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM planner_jobs WHERE owner = ? ORDER BY created DESC, id DESC LIMIT ? OFFSET ?",
            (str(owner), limit, offset),
        ).fetchall()
    return [decode(row) for row in rows]


# A running job whose worker stopped saving (crash or server restart) was interrupted.
# It is marked failed, not resumed, so the user sees what happened and can start it again.
# This waits for the lease (LEASE_SECONDS) to run out instead of failing every "running" job
# when a worker starts, because another worker may still be running that job: planning/worker.py
# can also be started from the command line, and during a Gunicorn reload the old worker keeps
# working while the new one starts.
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


# The worker takes the oldest queued job and marks it "running". Returns None if there is nothing to take.
def claim_job(worker):
    now = time.time()
    with connection() as database:
        # BEGIN IMMEDIATE locks the file, so two workers can never claim the same job.
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


# Saves a running job's progress and extends its lease.
# Raises LeaseLost if this worker no longer owns the job (for example it was cancelled).
def save_job(job, worker):
    now = time.time()
    with connection() as database:
        # The update only matches while this worker still owns the running job.
        changed = database.execute(
            "UPDATE planner_jobs SET data = ?, status = ?, phase = ?, updated = ?, lease_until = ? WHERE id = ? AND worker = ? AND status = 'running'",
            (encode(job), job["status"], job["phase"], now, now + LEASE_SECONDS, job["id"], worker),
        ).rowcount
        if changed != 1:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")


# Stores the user's answers to the follow-up questions and puts the job back in the queue.
# The whole workflow then runs again with the original inputs plus these answers.
def answer_job(job_id, owner, answers):
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        job = find_job(database, job_id, owner)
        # The status check also stops the same answers being sent twice.
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


# Starts a failed job again from the beginning, as a new job with the same inputs and answers.
# Returns the new job. The new job counts toward the daily allowance like any other.
# Its submission key is fixed, so pressing "Start again" twice returns the same new job.
def restart_job(job_id, owner):
    job = get_job(job_id, owner)
    if job is None or job["status"] != "failed":
        raise ValueError("Only a failed plan can be started again.")
    return submit_job(owner, "restart-" + job_id, job["project"], job["tier"], job["answers"])


# Deletes all of one user's planning jobs and saved projects (used when their account is deleted).
def delete_planner_jobs(owner):
    with connection() as database:
        database.execute("DELETE FROM planner_jobs WHERE owner = ?", (str(owner),))
        database.execute("DELETE FROM saved_projects WHERE owner = ?", (str(owner),))


# Cancels a job that is queued, running, or waiting for answers. Returns True if it was cancelled.
def cancel_job(job_id, owner):
    with connection() as database:
        changed = database.execute(
            "UPDATE planner_jobs SET status = 'cancelled', phase = 'Cancelled', worker = NULL, updated = ? WHERE id = ? AND owner = ? AND status IN ('queued', 'running', 'needs_input')",
            (time.time(), job_id, str(owner)),
        ).rowcount
    return changed == 1
