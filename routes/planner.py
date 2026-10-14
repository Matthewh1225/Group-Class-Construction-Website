import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from planning.ai_config import WORKFLOW_TIERS
from planning.jobs import answer_job, cancel_job, get_job, list_jobs, retry_job, submit_job
from planning.project_forms import PROJECT_TEMPLATES, build_custom_project
from planning.presentation import plan_presentation
from utils.rate_limits import limiter

planner_bp = Blueprint("planner", __name__)


def show_planner(popup_message=None, form_data=None):
    form_data = form_data or {}
    if "planner_token" not in session:
        session["planner_token"] = secrets.token_urlsafe(32)
    return render_template(
        "planner.html", ai_response=None, popup_message=popup_message,
        project_mode=form_data.get("projectMode"), project_size=form_data.get("projectSize"),
        project_template=form_data.get("projectTemplate"), form_data=form_data,
        project_templates=PROJECT_TEMPLATES, planner_token=session["planner_token"],
        submission_key=secrets.token_urlsafe(24), workflow_tiers=WORKFLOW_TIERS,
    )


def build_project(form):
    """Turn the submitted form into one project dictionary."""
    project_mode = form.get("projectMode")
    project_size = form.get("projectSize")
    project_template = form.get("projectTemplate")
    if project_mode == "template":
        template = PROJECT_TEMPLATES.get(project_template)
        if template is None:
            raise ValueError("Choose a valid project template.")
        project_size = template["size"]
        project_data = template["builder"](form)
    elif project_mode == "custom":
        project_data = build_custom_project(form)
    else:
        raise ValueError("Choose a template or custom project.")
    if project_size not in {"small", "medium", "large", "mega"}:
        raise ValueError("Choose a valid project size.")
    project_data.update({"project_mode": project_mode, "project_size": project_size,
                         "project_template": project_template})
    return project_data


def require_planner_user():
    if "user_id" not in session:
        abort(401, description="Sign in to save and process planning jobs.")
    return session["user_id"]


def check_planner_token():
    expected = session.get("planner_token", "")
    supplied = request.form.get("plannerToken", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        abort(400, description="Reload the planner before submitting the form.")


def owned_job(job_id):
    job = get_job(job_id, require_planner_user())
    if job is None:
        abort(404)
    return job


def submit_project_form():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    check_planner_token()
    try:
        project = build_project(request.form)
        tier = request.form.get("planType", "fast")
        # Old Basic submissions use the new Fast workflow, including its audit.
        if tier == "basic":
            tier = "fast"
        job = submit_job(session["user_id"], request.form.get("submissionKey", ""), project, tier)
    except ValueError as error:
        return show_planner(str(error), request.form), 400
    return redirect(url_for("planner.planning_job", job_id=job["id"]), code=303)


@planner_bp.route("/planner", methods=["GET", "POST"])
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planner():
    if request.method == "POST":
        return submit_project_form()
    return show_planner(form_data=request.args)


@planner_bp.post("/planner/jobs")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def submit_planning_job():
    return submit_project_form()


@planner_bp.get("/planner/jobs/<job_id>")
def planning_job(job_id):
    job = owned_job(job_id)
    if "planner_token" not in session:
        session["planner_token"] = secrets.token_urlsafe(32)
    return render_template("planner_job.html", job=job,
                           plan=plan_presentation(job),
                           tier_label=WORKFLOW_TIERS[job["tier"]]["label"],
                           planner_token=session["planner_token"])


@planner_bp.get("/planner/jobs/<job_id>/status")
def planning_job_status(job_id):
    job = owned_job(job_id)
    return {"id": job["id"], "status": job["status"], "phase": job["phase"],
            "error": job["error"], "specification_version": job["specification_version"],
            "plan_version": job["plan_version"]}, 200, {"Cache-Control": "no-store"}


@planner_bp.get("/planner/jobs/<job_id>/result")
def planning_job_result(job_id):
    job = owned_job(job_id)
    return {"id": job["id"], "status": job["status"], "result": job["result"]}, 200, {"Cache-Control": "no-store"}


@planner_bp.post("/planner/jobs/<job_id>/answers")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_answers(job_id):
    owned_job(job_id)
    check_planner_token()
    try:
        version = request.form.get("specificationVersion", type=int)
        answer_job(job_id, session["user_id"], request.form.getlist("answers"), version)
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/cancel")
def planning_job_cancel(job_id):
    owned_job(job_id)
    check_planner_token()
    cancel_job(job_id, session["user_id"])
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/retry")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_retry(job_id):
    owned_job(job_id)
    check_planner_token()
    try:
        retry_job(job_id, session["user_id"])
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.get("/planner/history")
def planning_history():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    return render_template("dashboard/planning_history.html", jobs=list_jobs(session["user_id"]))
