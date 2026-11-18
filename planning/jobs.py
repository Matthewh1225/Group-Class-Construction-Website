import hashlib
import json
import time
import uuid

from services.subscriptions import has_active_pro
from utils.database import database_cursor

from .ai_config import WORKFLOW_TIERS

# The lease must outlast one AI call (3 tries x 5 minutes plus delays is about 16 minutes); saving progress renews it.
LEASE_SECONDS = 40 * 60
MAX_RUNNING_JOBS = 2
MAX_QUEUED_JOBS = 100
MAX_REQUEST_BYTES = 20000
MAX_ANSWER_LENGTH = 2000
ONE_DAY = 24 * 60 * 60

# Other fields go in the JSON data column.
COLUMN_FIELDS = ["id", "owner", "tier", "status", "created", "updated"]


class LeaseLost(Exception):
    pass


def job_from_row(row):
    if row is None:
        return None
    job = json.loads(row["data"])
    for field in COLUMN_FIELDS:
        job[field] = row[field]
    return job


def job_to_json(job):
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
    stages["matcher"] = "pending"
    return stages


def mark_processing_stages(job, new_state):
    for stage, state in job.get("stages", {}).items():
        if state == "processing":
            job["stages"][stage] = new_state


# Hash the inputs so submit_job can detect a reused key with different data.
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


# The same submission key returns the same job.
def submit_job(owner, submission_key, project, tier="fast", answers=None, resume=None):
    if answers is None:
        answers = []
    request_hash = check_submission(owner, submission_key, project, tier, answers)
    now = time.time()
    job_id = uuid.uuid4().hex
    data = {"project": project, "questions": [], "answers": answers,
            "specification": None, "result": None, "error": None,
            "stages": pending_stages(tier)}
    if resume is not None:
        data["specification"] = resume["specification"]
        data["checkpoints"] = resume["checkpoints"]
        data["stages"] = resume["stages"]
        if resume.get("project_name"):
            data["project_name"] = resume["project_name"]
    with database_cursor(lock_name="planner_queue") as cursor:
        cursor.execute(
            "SELECT * FROM planner_jobs WHERE owner = %s AND submission_key = %s",
            (owner, submission_key),
        )
        existing = cursor.fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError("This submission key already belongs to another request.")
            return job_from_row(existing)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM planner_jobs WHERE owner = %s AND tier = %s AND created >= %s",
            (owner, tier, now - ONE_DAY),
        )
        jobs_last_24h = cursor.fetchone()["total"]
        if jobs_last_24h >= WORKFLOW_TIERS[tier]["max_jobs_per_24h"]:
            raise ValueError("This planning mode's limit for the past 24 hours has been reached.")
        check_queue_capacity(cursor, owner)
        cursor.execute(
            "INSERT INTO planner_jobs (id, owner, submission_key, request_hash, tier, status, created, updated, data) VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s, %s)",
            (job_id, owner, submission_key, request_hash, tier, now, now, job_to_json(data)),
        )
        return find_job(cursor, job_id, owner)


def find_job(cursor, job_id, owner, for_update=False):
    query = "SELECT * FROM planner_jobs WHERE id = %s AND owner = %s"
    if for_update:
        query += " FOR UPDATE"
    cursor.execute(query, (job_id, owner))
    return job_from_row(cursor.fetchone())


def get_job(job_id, owner):
    with database_cursor() as cursor:
        return find_job(cursor, job_id, owner)


def count_jobs(owner):
    with database_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM planner_jobs WHERE owner = %s", (owner,))
        return cursor.fetchone()["total"]


def list_jobs(owner, limit=20, offset=0):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT j.*, s.id AS saved_project_id, s.name AS saved_name FROM planner_jobs j
               LEFT JOIN saved_projects s ON s.owner = j.owner AND s.job_id = j.id
               WHERE j.owner = %s ORDER BY j.created DESC, j.id DESC LIMIT %s OFFSET %s""",
            (owner, limit, offset),
        )
        rows = cursor.fetchall()
    jobs = []
    for row in rows:
        job = job_from_row(row)
        job["saved_project_id"] = row["saved_project_id"]
        job["saved_name"] = row["saved_name"]
        jobs.append(job)
    return jobs


def fail_interrupted_jobs(cursor, now):
    cursor.execute(
        "SELECT * FROM planner_jobs WHERE status = 'running' AND lease_until < %s FOR UPDATE", (now,)
    )
    expired_rows = cursor.fetchall()
    for row in expired_rows:
        job = job_from_row(row)
        job["error"] = "Planning was interrupted before it finished."
        mark_processing_stages(job, "failed")
        cursor.execute(
            "UPDATE planner_jobs SET status = 'failed', worker = NULL, data = %s, updated = %s WHERE id = %s",
            (job_to_json(job), now, row["id"]),
        )


def claim_job(worker):
    now = time.time()
    with database_cursor(lock_name="planner_queue") as cursor:
        # Lock the queue while counting and claiming jobs.
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
        job = job_from_row(row)
        job["status"] = "running"
        job["updated"] = now
        return job


def save_job(job, worker):
    now = time.time()
    with database_cursor() as cursor:
        # Keep the name stored by the user while the worker was planning.
        cursor.execute(
            """UPDATE planner_jobs
               SET data = JSON_MERGE_PATCH(%s, JSON_OBJECT('project_name', JSON_EXTRACT(data, '$.project_name'))),
                   status = %s, updated = %s, lease_until = %s
               WHERE id = %s AND worker = %s AND status = 'running'""",
            (job_to_json(job), job["status"], now, now + LEASE_SECONDS, job["id"], worker),
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
        job["stages"]["interpreter"] = "done"
        cursor.execute(
            "UPDATE planner_jobs SET data = %s, status = 'queued', worker = NULL, lease_until = 0, updated = %s WHERE id = %s",
            (job_to_json(job), time.time(), job_id),
        )


# Reuse the key so repeated restart clicks don't create extra jobs.
def restart_job(job_id, owner):
    job = get_job(job_id, owner)
    if job is None or job["status"] != "failed":
        raise ValueError("Only failed plans can be started again.")
    checkpoints = job.get("checkpoints", {})
    stages = {}
    for stage, state in job["stages"].items():
        finished = stage == "interpreter" or stage in checkpoints
        if state == "done" and finished:
            stages[stage] = "done"
        else:
            stages[stage] = "pending"
    progress = {"specification": job["specification"], "checkpoints": checkpoints, "stages": stages,
                "project_name": job.get("project_name")}
    return submit_job(owner, "restart-" + job_id, job["project"], job["tier"], job["answers"], progress)


def cancel_job(job_id, owner):
    with database_cursor(lock_name="planner_queue") as cursor:
        job = find_job(cursor, job_id, owner, for_update=True)
        if job is None or job["status"] not in ("queued", "running", "needs_input"):
            return False
        mark_processing_stages(job, "cancelled")
        cursor.execute(
            "UPDATE planner_jobs SET status = 'cancelled', worker = NULL, data = %s, updated = %s WHERE id = %s AND owner = %s AND status IN ('queued', 'running', 'needs_input')",
            (job_to_json(job), time.time(), job_id, owner),
        )
        changed = cursor.rowcount
    return changed == 1
