"""A small durable SQLite queue, shared by Flask and a separate planner worker.

This stores planner jobs only. Existing MySQL catalog and account code is unchanged.
The web server and worker must use the same persistent local file.
"""

import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .ai_config import WORKFLOW_TIERS, WORKFLOW_VERSION


class LeaseLost(ValueError):
    """The worker cannot save a job it no longer owns."""


def database_path():
    default = Path(__file__).resolve().parents[1] / "instance" / "planner_jobs.sqlite3"
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
    import hashlib

    settings = WORKFLOW_TIERS.get(tier)
    if settings is None or not settings["enabled"]:
        raise ValueError("This tier is awaiting its required completion gate.")
    if tier == "pro" and not pro_access_allowed(owner):
        raise ValueError("Pro access has not been enabled for this account.")
    if not isinstance(submission_key, str) or not 8 <= len(submission_key) <= 100:
        raise ValueError("Reload the planner before submitting this form.")
    encoded = json.dumps({"project": project, "tier": tier}, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > 20000:
        raise ValueError("Keep project details below 20,000 bytes.")
    request_hash = hashlib.sha256(encoded.encode()).hexdigest()
    owner = str(owner)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"tier": tier, "project": project, "original_request": project,
            "config_version": WORKFLOW_VERSION, "specification_version": 1,
            "plan_version": 1, "stages": {}, "attempts": [], "answers": [],
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
    # Explicit server-side testing access; never read this from a submitted form.
    if os.getenv("PLANNER_PRO_TEST_ACCESS", "").strip().lower() == "true":
        return True
    # This server-managed list grants access; a form or session flag cannot grant it.
    # Payment services are stubs, so there is no fabricated automatic subscription.
    allowed = os.getenv("PLANNER_PRO_USER_IDS", "").split(",")
    for user_id in allowed:
        if str(owner) == user_id.strip():
            return True
    return False


def check_queue_capacity(database, owner):
    """Check the shared queue rules within a caller's write transaction."""
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
    """Check resume gates inside the caller's write transaction."""
    if job["config_version"] != WORKFLOW_VERSION:
        raise ValueError("This job uses an older format. Start a new project.")
    if not WORKFLOW_TIERS[job["tier"]]["enabled"]:
        raise ValueError("This tier is awaiting its completion gate.")
    if job["tier"] == "pro" and not pro_access_allowed(job["owner"]):
        raise ValueError("Pro access has not been enabled for this account.")
    check_queue_capacity(database, job["owner"])


def get_job(job_id, owner):
    with connection() as database:
        row = database.execute("SELECT * FROM planner_jobs WHERE id = ? AND owner = ?",
                               (job_id, str(owner))).fetchone()
    return decode(row)


def list_jobs(owner, limit=20):
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM planner_jobs WHERE owner = ? ORDER BY created DESC LIMIT ?",
            (str(owner), limit),
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
        database.execute("BEGIN IMMEDIATE")
        previous = database.execute(
            "SELECT * FROM planner_jobs WHERE id = ? AND worker = ? AND status = 'running'",
            (job["id"], worker),
        ).fetchone()
        if previous is None:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")
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
            raise ValueError("This job is not waiting for answers.")
        if expected_version != job["specification_version"]:
            raise ValueError("These questions have changed. Reload the page.")
        check_resume_capacity(database, job)
        questions = job["questions"]
        if len(answers) != len(questions) or any(not answer.strip() or len(answer) > 2000 for answer in answers):
            raise ValueError("Answer each question, or enter 'Not sure'.")
        clarifications = []
        for question, answer in zip(questions, answers):
            clarifications.append({"id": question["id"], "question": question["question"], "answer": answer.strip()})
        job["answers"].extend(clarifications)
        job["previous_specification"] = job.get("specification")
        job["specification_version"] += 1
        job["plan_version"] += 1
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
        if len(job["attempts"]) >= settings["max_attempts"]:
            raise ValueError("This job has exhausted its provider attempts. Start a new project.")
        stage = job.get("current_stage")
        if not stage:
            raise ValueError("This job cannot be resumed. Start a new project.")
        invocations = job.setdefault("stage_invocations", {})
        # Both parallel branches may have exhausted recovery. Reset every
        # unfinished stage in this specification, retaining successful stages.
        unfinished = {stage}
        unfinished.update(
            attempt["name"] for attempt in job["attempts"]
            if attempt["specification_version"] == job["specification_version"]
            and attempt["name"] not in job["stages"]
        )
        for name in unfinished:
            invocations[name] = invocations.get(name, 1) + 1
        job["error"] = None
        database.execute(
            "UPDATE planner_jobs SET data = ?, status = 'queued', worker = NULL, lease_until = 0, updated = ? WHERE id = ?",
            (json.dumps(job), time.time(), job_id),
        )


def cancel_job(job_id, owner):
    with connection() as database:
        changed = database.execute(
            "UPDATE planner_jobs SET status = 'cancelled', phase = 'Cancelled', worker = NULL, updated = ? WHERE id = ? AND owner = ? AND status IN ('queued', 'running', 'needs_input')",
            (time.time(), job_id, str(owner)),
        ).rowcount
    return changed == 1
