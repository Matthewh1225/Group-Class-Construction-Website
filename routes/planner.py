import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from planning.ai_config import WORKFLOW_TIERS
from planning.jobs import answer_job, cancel_job, count_jobs, get_job, list_jobs, pro_access_allowed, restart_job, submit_job
from planning.project_forms import PROJECT_TEMPLATES, build_custom_project
from planning.presentation import add_store_details, cart_items, cart_total, status_label
from services.cart import add_cart_item
from services.crews import CREW_RATES, HOURS_PER_DAY
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


def plan_materials(job):
    if not job["result"]:
        return []
    return add_store_details(job["result"]["materials"])


@planner_bp.get("/planner/jobs/<job_id>")
def planning_job(job_id):
    job = owned_job(job_id)
    materials = plan_materials(job)
    cart = cart_items(materials)
    label, tone = status_label(job)
    template = PROJECT_TEMPLATES.get(job["project"].get("project_type"), {})
    title = template.get("title", "Your project")
    # The save box stays hidden until services/projects.py is finished.
    return render_template("planner_job.html", job=job, materials=materials,
                           cart=cart, cart_total=cart_total(cart),
                           title=title,
                           status_label=label, status_tone=tone,
                           tier_label=WORKFLOW_TIERS[job["tier"]]["label"],
                           crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY,
                           saved_project=get_project_for_job(job_id, session["user_id"]),
                           can_save=can_save(job), default_name=default_project_name(job))


# No material index means add all available items.
# Get IDs and amounts from the plan and store data, not the form.
@planner_bp.post("/planner/jobs/<job_id>/cart")
@limiter.limit("30 per minute", methods=["POST"])
def planning_job_add_to_cart(job_id):
    job = owned_job(job_id)
    materials = plan_materials(job)
    position = request.form.get("material", type=int)
    if position is None:
        chosen = materials
    elif 0 <= position < len(materials):
        chosen = [materials[position]]
    else:
        chosen = []

    added = []
    failed = []
    for item in cart_items(chosen):
        product = item["product"]
        # Use plain digits rather than scientific notation.
        quantity = format(item["quantity"], "f")
        try:
            product_name = add_cart_item(session["user_id"], product["product_id"], quantity)
        except ValueError as error:
            failed.append(f"{product['product_name']} ({error})")
            continue
        # The cart helper is still a stub; None means nothing was added.
        if product_name is None:
            failed.append(product["product_name"])
        else:
            added.append(product_name)

    skipped = 0
    for row in chosen:
        if not row["can_add"]:
            skipped += 1

    if len(added) == 1:
        flash(f"Added {added[0]} to your cart.", "success")
    elif len(added) > 1:
        flash(f"Added {len(added)} products to your cart.", "success")
    if failed:
        flash("Could not add to your cart: " + "; ".join(failed) + ".", "error")
    if skipped == 1:
        flash("1 material was not added: the store does not sell it, has none in stock, "
              "or the amount is unknown.", "info")
    elif skipped > 1:
        flash(f"{skipped} materials were not added: the store does not sell them, has none in stock, "
              "or the amount is unknown.", "info")
    if not chosen:
        flash("There was nothing to add to your cart.", "error")
    return redirect(url_for("planner.planning_job", job_id=job_id, _anchor="plan-messages"), code=303)


@planner_bp.post("/planner/jobs/<job_id>/save")
def planning_job_save(job_id):
    # Saving the same job again should update its project.
    job = owned_job(job_id)
    try:
        project_id = save_project(session["user_id"], job, request.form.get("name"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    if project_id is None:
        flash("Project could not be saved.", "error")
        return redirect(url_for("planner.planning_job", job_id=job_id), code=303)
    flash("Project saved.", "success")
    if request.form.get("return_to") == "project":
        return redirect(url_for("dashboard.project_detail", project_id=project_id), code=303)
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.get("/planner/jobs/<job_id>/status")
def planning_job_status(job_id):
    job = owned_job(job_id)
    status = {"id": job["id"], "status": job["status"], "phase": job["phase"], "error": job["error"]}
    return status, 200, {"Cache-Control": "no-store"}


@planner_bp.post("/planner/jobs/<job_id>/answers")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_answers(job_id):
    owned_job(job_id)
    try:
        answer_job(job_id, session["user_id"], request.form.getlist("answers"))
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


@planner_bp.post("/planner/jobs/<job_id>/cancel")
def planning_job_cancel(job_id):
    owned_job(job_id)
    cancel_job(job_id, session["user_id"])
    return redirect(url_for("planner.planning_job", job_id=job_id), code=303)


# A failed job restarts as a new job with the same inputs and answers.
@planner_bp.post("/planner/jobs/<job_id>/restart")
@limiter.limit("4 per minute; 30 per hour", methods=["POST"])
def planning_job_restart(job_id):
    owned_job(job_id)
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
    return render_template("dashboard/planning_history.html",
                           jobs=list_jobs(session["user_id"], limit=page_size, offset=offset),
                           status_label=status_label, workflow_tiers=WORKFLOW_TIERS,
                           page=page, last_page=last_page, offset=offset)
