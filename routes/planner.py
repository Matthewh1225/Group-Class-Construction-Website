import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from planning.ai_config import WORKFLOW_TIERS
from planning.jobs import answer_job, cancel_job, count_jobs, get_job, list_jobs, pro_access_allowed, restart_job, submit_job
from planning.project_forms import PROJECT_SIZES, PROJECT_TEMPLATES, build_project
from planning.presentation import (STAGE_STATUS_LABELS, add_store_details, cart_items, cart_total,  project_spec_rows, stage_rows, status_label)
from services.cart import add_materials_to_cart
from services.crews import CREW_RATES, HOURS_PER_DAY, estimate_crew_cost
from services.projects import (can_save_project, default_project_name, get_project_saved_from_job, get_project_list, save_job_as_project)
from utils.rate_limits import limiter

planner_bp = Blueprint("planner", __name__)


def show_planner(popup_message=None, form_data=None):
    form_data = form_data or {}
    has_details = False
    if form_data.get("projectMode") == "custom":
        has_details = True
    elif form_data.get("projectMode") == "template":
        has_details = form_data.get("projectTemplate") in PROJECT_TEMPLATES
    return render_template(
        "planner.html", popup_message=popup_message,
        project_mode=form_data.get("projectMode"), project_size=form_data.get("projectSize"),
        project_template=form_data.get("projectTemplate"), form_data=form_data,
        project_templates=PROJECT_TEMPLATES, project_sizes=PROJECT_SIZES, has_details=has_details,
        submission_key=secrets.token_urlsafe(24), workflow_tiers=WORKFLOW_TIERS,
        pro_allowed=pro_access_allowed(session.get("user_id")),
    )


def get_user_job(job_id):
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


def get_plan_materials(job):
    if not job["result"]:
        return []
    return add_store_details(job["result"]["materials"])


@planner_bp.get("/planner/jobs/<job_id>")
def planning_job(job_id):
    job = get_user_job(job_id)
    materials = get_plan_materials(job)
    cart = cart_items(materials)
    label, tone = status_label(job)
    template = PROJECT_TEMPLATES.get(job["project"].get("project_type"), {})
    title = template.get("title", "Your project")
    saved_project = get_project_saved_from_job(job_id, session["user_id"])
    recommendation = None
    crew_estimate = None
    if job["result"]:
        recommendation = job["result"].get("crew")
    if saved_project and saved_project.get("crew"):
        recommendation = saved_project["crew"]
    if recommendation:
        crew_estimate = estimate_crew_cost(recommendation)
    crew_url = url_for("crews.crews", job_id=job["id"])
    if saved_project:
        crew_url = url_for("crews.crews", project_id=saved_project["id"])
    return render_template("planner_job.html", job=job, materials=materials,
                           cart=cart, cart_total=cart_total(cart),
                           title=title,
                           project_fields=project_spec_rows(job["project"]),
                           stage_rows=stage_rows(job), stage_status_labels=STAGE_STATUS_LABELS,
                           status_label=label, status_tone=tone,
                           tier_label=WORKFLOW_TIERS[job["tier"]]["label"],
                           crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY,
                           saved_project=saved_project, crew_recommendation=recommendation, crew_url=crew_url,
                           crew_estimate=crew_estimate,
                           can_save=can_save_project(job), default_name=default_project_name(job))


@planner_bp.post("/planner/jobs/<job_id>/cart")
@limiter.limit("30 per minute", methods=["POST"])
def planning_job_add_to_cart(job_id):
    job = get_user_job(job_id)
    materials = get_plan_materials(job)
    position = request.form.get("material", type=int)
    if position is None:
        chosen = materials
    elif 0 <= position < len(materials):
        chosen = [materials[position]]
    else:
        chosen = []

    result = add_materials_to_cart(session["user_id"], chosen)
    added = result["added"]
    failed = result["failed"]
    skipped = result["skipped"]

    if len(added) == 1:
        flash(f"Added {added[0]} to your cart.", "success")
    elif len(added) > 1:
        flash(f"Added {len(added)} products to your cart.", "success")
    if failed:
        flash("Could not add to your cart: " + "; ".join(failed) + ".", "error")
    if skipped >= 1:
        flash(" material was not added: we do not sell it or it is out of stock.", "info")
    if not chosen:
        flash("There was nothing to add to your cart.", "error")
    return redirect(url_for("planner.planning_job", job_id=job_id, _anchor="plan-messages"), code=303)


@planner_bp.post("/planner/jobs/<job_id>/save")
def planning_job_save(job_id):
    job = get_user_job(job_id)
    try:
        project_id = save_job_as_project(session["user_id"], job, request.form.get("name"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    if project_id is None:
        flash("Project could not be saved.", "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    flash("Project saved.", "success")
    if request.form.get("return_to") == "history":
        return redirect(url_for("planner.planning_history"), code=303)
    if request.form.get("return_to") == "project":
        return redirect(url_for("dashboard.project_detail", project_id=project_id), code=303)
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.get("/planner/jobs/<job_id>/status")
def planning_job_status(job_id):
    job = get_user_job(job_id)
    label, tone = status_label(job)
    status = {"id": job["id"], "status": job["status"], "label": label, "error": job["error"],
              "stages": job.get("stages", {})}
    return status, 200, {"Cache-Control": "no-store"}


@planner_bp.post("/planner/jobs/<job_id>/answers")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_answers(job_id):
    get_user_job(job_id)
    try:
        answer_job(job_id, session["user_id"], request.form.getlist("answers"))
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/cancel")
def planning_job_cancel(job_id):
    get_user_job(job_id)
    cancel_job(job_id, session["user_id"])
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/restart")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_restart(job_id):
    get_user_job(job_id)
    try:
        new_job = restart_job(job_id, session["user_id"])
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    return redirect(url_for("planner.planning_job", job_id=new_job["id"]), code=303)


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
    saved_ids = {}
    for saved in get_project_list(session["user_id"]):
        saved_ids[saved["id"]] = saved["saved_project_id"]
    shown = list_jobs(session["user_id"], limit=page_size, offset=offset)
    for job in shown:
        job["saved_project_id"] = saved_ids.get(job["id"])
        label, tone = status_label(job)
        job["planning_status_label"] = label
        job["planning_status_tone"] = tone
        job["can_save"] = can_save_project(job)
    return render_template("dashboard/planning_history.html",
                           jobs=shown, workflow_tiers=WORKFLOW_TIERS,
                           page=page, last_page=last_page, offset=offset)
