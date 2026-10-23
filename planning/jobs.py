# Planner jobs and saved projects use the shared MySQL database.
# Answering questions requeues a job; restarting a failed job creates a new one.

import hashlib
import json
import time
import uuid

from services.subscriptions import has_active_pro
from utils.database import database_cursor

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


def check_queue_capacity(cursor, owner):
    cursor.execute(
        "SELECT COUNT(*) AS total FROM planner_jobs WHERE owner = %s AND status IN ('queued', 'running')",
        (owner,),
    )
    active = cursor.fetchone()["total"]
    if active:
        raise ValueError("Finish or cancel your current planning job first.")
    cursor.execute("SELECT COUNT(*) AS total FROM planner_jobs WHERE status = 'queued'")
    queued = cursor.fetchone()["total"]
    if queued >= MAX_QUEUED_JOBS:
        raise ValueError("The planner queue is full. Please try again later.")


# Reusing a submission key returns the first job.
def submit_job(owner, submission_key, project, tier="fast", answers=None):
    if answers is None:
        answers = []
    request_hash = check_submission(owner, submission_key, project, tier, answers)
    owner = int(owner)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"project": project, "questions": [], "answers": answers,
            "specification": None, "result": None, "error": None,
            "stages": pending_stages(tier)}
    with database_cursor(lock_name="planner_queue") as cursor:
        # Keep queue checks and the insert in the same locked transaction.
        cursor.execute(
            "SELECT * FROM planner_jobs WHERE owner = %s AND submission_key = %s",
            (owner, submission_key),
        )
        existing = cursor.fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError("This submission key already belongs to another request.")
            return decode(existing)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM planner_jobs WHERE owner = %s AND tier = %s AND created >= %s",
            (owner, tier, now - ONE_DAY),
        )
        jobs_today = cursor.fetchone()["total"]
        if jobs_today >= WORKFLOW_TIERS[tier]["daily_jobs"]:
            raise ValueError("Your daily planning allowance has been reached.")
        check_queue_capacity(cursor, owner)
        cursor.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, created, updated, data) VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s, %s)",
            (job_id, owner, submission_key, request_hash, tier, now, now, encode(data)),
        )
        return find_job(cursor, job_id, owner)


def find_job(cursor, job_id, owner, for_update=False):
    query = "SELECT * FROM planner_jobs WHERE id = %s AND owner = %s"
    if for_update:
        query += " FOR UPDATE"
    cursor.execute(query, (job_id, int(owner)))
    return decode(cursor.fetchone())


def get_job(job_id, owner):
    with database_cursor() as cursor:
        return find_job(cursor, job_id, owner)


def count_jobs(owner):
    with database_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM planner_jobs WHERE owner = %s", (int(owner),))
        return cursor.fetchone()["total"]


def list_jobs(owner, limit=20, offset=0):
    with database_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM planner_jobs WHERE owner = %s ORDER BY created DESC, id DESC LIMIT %s OFFSET %s",
            (int(owner), limit, offset),
        )
        rows = cursor.fetchall()
    return [decode(row) for row in rows]


# Wait for the time limit: another worker may still be running the job.
# Interrupted jobs fail so the user can restart them.
def fail_interrupted_jobs(cursor, now):
    cursor.execute(
        "SELECT * FROM planner_jobs WHERE status = 'running' AND lease_until < %s FOR UPDATE", (now,)
    )
    expired_rows = cursor.fetchall()
    for row in expired_rows:
        job = decode(row)
        job["error"] = "Planning was interrupted before it finished."
        stop_running_stages(job, "failed")
        cursor.execute(
            "UPDATE planner_jobs SET status = 'failed', worker = NULL, data = %s, updated = %s WHERE id = %s",
            (encode(job), now, row["id"]),
        )


def claim_job(worker):
    now = time.time()
    with database_cursor(lock_name="planner_queue") as cursor:
        # Serialize claims and the running-job count across all workers.
        fail_interrupted_jobs(cursor, now)
        cursor.execute("SELECT COUNT(*) AS total FROM planner_jobs WHERE status = 'running'")
        running = cursor.fetchone()["total"]
        if running >= MAX_RUNNING_JOBS:
            return None
        cursor.execute(
            "SELECT * FROM planner_jobs WHERE status = 'queued' ORDER BY created, id LIMIT 1 FOR UPDATE"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute(
            "UPDATE planner_jobs SET status = 'running', worker = %s, lease_until = %s, updated = %s WHERE id = %s",
            (worker, now + LEASE_SECONDS, now, row["id"]),
        )
        job = decode(row)
        job["status"] = "running"
        job["updated"] = now
        return job


def save_job(job, worker):
    now = time.time()
    with database_cursor() as cursor:
        # Only the worker still assigned to the running job can save it.
        cursor.execute(
            "UPDATE planner_jobs SET data = %s, status = %s, updated = %s, lease_until = %s WHERE id = %s AND worker = %s AND status = 'running'",
            (encode(job), job["status"], now, now + LEASE_SECONDS, job["id"], worker),
        )
        if cursor.rowcount != 1:
            raise LeaseLost("This worker no longer owns the job, or the job was cancelled.")


def answer_job(job_id, owner, answers):
    with database_cursor(lock_name="planner_queue") as cursor:
        job = find_job(cursor, job_id, owner, for_update=True)
        if job is None or job["status"] != "needs_input":
            raise ValueError("This plan is not waiting for answers.")
        if len(answers) != len(job["questions"]) or any(len(answer) > MAX_ANSWER_LENGTH for answer in answers):
            raise ValueError(f"Submit one answer per question, using at most {MAX_ANSWER_LENGTH:,} characters each.")
        check_queue_capacity(cursor, job["owner"])
        job["answers"] = []
        for question, answer in zip(job["questions"], answers):
            answer = answer.strip()
            if not answer:
                answer = "Not answered"
            job["answers"].append({"question": question, "answer": answer})
        job["questions"] = []
        job["stages"] = pending_stages(job["tier"])
        cursor.execute(
            "UPDATE planner_jobs SET data = %s, status = 'queued', worker = NULL, lease_until = 0, updated = %s WHERE id = %s",
            (encode(job), time.time(), job_id),
        )


# A fixed key stops repeated clicks from creating extra jobs.
def restart_job(job_id, owner):
    job = get_job(job_id, owner)
    if job is None or job["status"] != "failed":
        raise ValueError("Only failed plans can be started again.")
    return submit_job(owner, "restart-" + job_id, job["project"], job["tier"], job["answers"])


def cancel_job(job_id, owner):
    with database_cursor(lock_name="planner_queue") as cursor:
        job = find_job(cursor, job_id, owner, for_update=True)
        if job is None or job["status"] not in ("queued", "running", "needs_input"):
            return False
        stop_running_stages(job, "cancelled")
        cursor.execute(
            "UPDATE planner_jobs SET status = 'cancelled', worker = NULL, data = %s, updated = %s WHERE id = %s AND owner = %s AND status IN ('queued', 'running', 'needs_input')",
            (encode(job), time.time(), job_id, int(owner)),
        )
        changed = cursor.rowcount
    return changed == 1
