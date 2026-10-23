import json
import time

from planning.jobs import decode, find_job
from planning.project_forms import PROJECT_TEMPLATES
from services.crews import check_crew
from utils.database import database_cursor

PROJECT_STATUS_LABELS = {"Review Needed": "Partial result"}
PROJECT_QUERY = """SELECT s.*, j.data, j.status AS job_status, j.tier,
                          j.created AS job_created, j.updated AS job_updated
                   FROM saved_projects s LEFT JOIN planner_jobs j
                   ON j.id = s.job_id AND j.owner = s.owner"""


def default_project_name(job):
    project = job.get("project") or {}
    template = PROJECT_TEMPLATES.get(project.get("project_type"), {})
    return (project.get("description") or template.get("title") or "Untitled project").strip()[:120]


def can_save_project(job):
    return job.get("status") == "complete" and bool((job.get("result") or {}).get("materials"))


def check_name(name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError("Enter a project name between 1 and 120 characters.")
    return name.strip()


def save_job_as_project(user_id, job, name):
    name = check_name(name)
    with database_cursor() as cursor:
        # Read the stored plan and ownership, rather than trusting a caller's copy.
        job = find_job(cursor, job["id"], user_id, for_update=True)
        if job is None or not can_save_project(job):
            raise ValueError("Only a finished plan with materials can be saved.")
        now = time.time()
        cursor.execute(
            """INSERT INTO saved_projects (owner, job_id, name, plan, created, updated)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
            (int(user_id), job["id"], name, json.dumps(job, allow_nan=False), now, now),
        )
        return cursor.lastrowid


def read_project(row):
    row["job_exists"] = row["data"] is not None
    if row["job_exists"]:
        row["plan"] = decode({
            "data": row["data"], "id": row["job_id"], "owner": row["owner"],
            "status": row["job_status"], "tier": row["tier"],
            "created": row["job_created"], "updated": row["job_updated"],
        })
    else:
        row["plan"] = json.loads(row["plan"])
    row["crew"] = json.loads(row["crew"]) if row["crew"] else None
    plan = row["plan"]
    if row["completed"]:
        status, tone = "Completed", "ready"
    elif plan["status"] == "complete":
        status, tone = "Ready", "ready"
    elif plan.get("result"):
        status, tone = "Review Needed", "attention"
    else:
        status, tone = "In Progress", "neutral"
    row["status"] = status
    row["status_label"] = PROJECT_STATUS_LABELS.get(status, status)
    row["status_tone"] = tone
    project_type = (plan.get("project") or {}).get("project_type", "custom")
    row["type"] = PROJECT_TEMPLATES.get(project_type, {}).get("title", project_type.replace("_", " ").title())
    return row


def get_project_list(user_id, limit=None, search="", status=""):
    with database_cursor() as cursor:
        cursor.execute(PROJECT_QUERY + " WHERE s.owner = %s ORDER BY s.updated DESC, s.id DESC", (int(user_id),))
        rows = cursor.fetchall()
    projects = []
    for row in rows:
        project = read_project(row)
        if search.casefold() not in project["name"].casefold():
            continue
        if status and project["status"] != status:
            continue
        job = project["plan"].copy()
        job.update(saved_project_id=project["id"], saved_name=project["name"], updated=project["updated"])
        projects.append(job)
    return projects if limit is None else projects[:limit]


def count_projects(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM saved_projects WHERE owner = %s", (int(user_id),))
        return cursor.fetchone()["total"]


def get_project_details(project_id, user_id):
    with database_cursor() as cursor:
        cursor.execute(PROJECT_QUERY + " WHERE s.id = %s AND s.owner = %s", (project_id, int(user_id)))
        row = cursor.fetchone()
    return read_project(row) if row else None


def get_project_saved_from_job(job_id, user_id):
    with database_cursor() as cursor:
        cursor.execute(PROJECT_QUERY + " WHERE s.job_id = %s AND s.owner = %s", (job_id, int(user_id)))
        row = cursor.fetchone()
    return read_project(row) if row else None


def rename_project(project_id, user_id, name):
    name = check_name(name)
    with database_cursor() as cursor:
        cursor.execute("UPDATE saved_projects SET name = %s, updated = %s WHERE id = %s AND owner = %s",
                       (name, time.time(), project_id, int(user_id)))
        return cursor.rowcount == 1


def set_project_completed(project_id, user_id, completed):
    with database_cursor() as cursor:
        cursor.execute("UPDATE saved_projects SET completed = %s, updated = %s WHERE id = %s AND owner = %s",
                       (bool(completed), time.time(), project_id, int(user_id)))
        return cursor.rowcount == 1


def save_project_crew(project_id, user_id, crew):
    crew_json = json.dumps(check_crew(crew), allow_nan=False) if crew is not None else None
    with database_cursor() as cursor:
        cursor.execute("UPDATE saved_projects SET crew = %s, updated = %s WHERE id = %s AND owner = %s",
                       (crew_json, time.time(), project_id, int(user_id)))
        return cursor.rowcount == 1


def delete_project(project_id, user_id):
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM saved_projects WHERE id = %s AND owner = %s", (project_id, int(user_id)))
        return cursor.rowcount == 1
