import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from planning.ai_config import WORKFLOW_TIERS
from planning.jobs import answer_job, cancel_job, count_jobs, get_job, list_jobs, pro_access_allowed, retry_job, submit_job
from planning.project_forms import PROJECT_TEMPLATES, build_custom_project
from planning.presentation import plan_presentation, status_label
from services.projects import can_save, default_project_name, get_project_for_job, save_project
from utils.rate_limits import limiter

planner_bp = Blueprint("planner", __name__)


def show_planner(popup_message=None, form_data=None):
    form_data = form_data or {}
    return render_template(
        "planner.html", popup_message=popup_message,
        project_mode=form_data.get("projectMode"), project_size=form_data.get("projectSize"),
        project_template=form_data.get("projectTemplate"), form_data=form_data,
        project_templates=PROJECT_TEMPLATES,
        submission_key=secrets.token_urlsafe(24), workflow_tiers=WORKFLOW_TIERS,
        pro_allowed=pro_access_allowed(session.get("user_id")),
    )


def build_project(form):
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


def owned_job(job_id):
    # The signed-in user's job, or an error page: 401 when signed out, 404 for anyone else's.
    if "user_id" not in session:
        abort(401, description="Sign in to view planning jobs.")
    job = get_job(job_id, session["user_id"])
    if job is None:
        abort(404)
    return job


@planner_bp.get("/planner")
def planner():
    return show_planner(form_data=request.args)


@planner_bp.post("/planner/jobs")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def submit_planning_job():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    try:
        project = build_project(request.form)
        tier = request.form.get("planType", "fast")
        job = submit_job(session["user_id"], request.form.get("submissionKey", ""), project, tier)
    except ValueError as error:
        return show_planner(str(error), request.form), 400
    return redirect(url_for("planner.planning_job", job_id=job["id"]), code=303)


@planner_bp.get("/planner/jobs/<job_id>")
def planning_job(job_id):
    job = owned_job(job_id)
    return render_template("planner_job.html", job=job,
                           plan=plan_presentation(job),
                           tier_label=WORKFLOW_TIERS[job["tier"]]["label"],
                           saved_project=get_project_for_job(job_id, session["user_id"]),
                           can_save=can_save(job), default_name=default_project_name(job))


@planner_bp.post("/planner/jobs/<job_id>/save")
def planning_job_save(job_id):
    # Save Project / Update Project: keep this plan in My Projects.
    # Saving the same job again updates its project instead of making a new one.
    job = owned_job(job_id)
    try:
        project_id = save_project(session["user_id"], job, request.form.get("name"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    flash("Project saved to My Projects.", "success")
    if request.form.get("return_to") == "project":
        return redirect(url_for("dashboard.project_detail", project_id=project_id), code=303)
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.get("/planner/jobs/<job_id>/status")
def planning_job_status(job_id):
    job = owned_job(job_id)
    status = {"id": job["id"], "status": job["status"], "phase": job["phase"],
              "error": job["error"], "specification_version": job["specification_version"]}
    return status, 200, {"Cache-Control": "no-store"}


@planner_bp.get("/planner/jobs/<job_id>/result")
def planning_job_result(job_id):
    job = owned_job(job_id)
    return {"id": job["id"], "status": job["status"], "result": job["result"]}, 200, {"Cache-Control": "no-store"}


@planner_bp.post("/planner/jobs/<job_id>/answers")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_answers(job_id):
    owned_job(job_id)
    try:
        version = request.form.get("specificationVersion", type=int)
        answer_job(job_id, session["user_id"], request.form.getlist("answers"), version)
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/cancel")
def planning_job_cancel(job_id):
    owned_job(job_id)
    cancel_job(job_id, session["user_id"])
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/retry")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_retry(job_id):
    owned_job(job_id)
    try:
        retry_job(job_id, session["user_id"])
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.get("/planner/history")
def planning_history():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    page_size = 20
    total = count_jobs(session["user_id"])
    last_page = max(1, (total + page_size - 1) // page_size)
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    elif page > last_page:
        page = last_page
    offset = (page - 1) * page_size
    return render_template("dashboard/planning_history.html",
                           jobs=list_jobs(session["user_id"], limit=page_size, offset=offset),
                           status_label=status_label, workflow_tiers=WORKFLOW_TIERS,
                           page=page, last_page=last_page, offset=offset)
