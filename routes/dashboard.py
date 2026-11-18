from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from planning.ai_config import WORKFLOW_TIERS
from routes.auth import login_required
from services.orders import add_receipt_totals, get_order, get_order_items, get_user_orders
from services.crews import parse_crew
from services.payments import delete_card, get_card, list_cards, save_card, validate_card
from services.projects import (PROJECT_STATUS_LABELS, delete_project, get_project_details, count_projects, get_project_list,
                               rename_project, save_project_crew, set_project_completed)
from services.subscriptions import get_user_subscription
from utils.users import (change_user_password, check_profile_form, create_user, delete_user_completely, full_name,
                         get_all_users, get_profile, set_user_status, update_profile)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    role = session.get("permission_level", "user")

    if request.method == "POST":
        if role != "admin":
            abort(403)

        new_role = request.form.get("permission_level", "user")
        try:
            create_user(request.form, new_role)
            flash("User created.", "success")
            return redirect(url_for("dashboard.dashboard"))
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            flash("Email already in use.", "error")
        except Error:
            current_app.logger.exception("Unable to create an admin user")
            flash("Unable to create user. Try again.", "error")
        return redirect(url_for("dashboard.dashboard", add_user="error"))

    if role == "admin":
        users_error = False
        try:
            users = get_all_users()
        except Error:
            current_app.logger.exception("Unable to load the admin user list")
            users = []
            users_error = True
        admin_count = 0
        for user in users:
            if user["role"] == "admin":
                admin_count += 1
        user_statistics = [
            ("Total Users", len(users), "icon-user"),
            ("Administrators", admin_count, "icon-grid"),
            ("Regular Users", len(users) - admin_count, "icon-user"),
        ]
        return render_template(
            "admin_dashboard.html", display_name=session.get("display_name"),
            role=role, users=users, users_error=users_error,
            admin_workspace=True, user_statistics=user_statistics,
        )

    return show_overview()


def show_overview():
    user_id = session["user_id"]
    project_count = count_projects(user_id)
    orders = get_user_orders(user_id)
    cards = list_cards(user_id)
    default_card = None
    for card in cards:
        if card["is_default"]:
            default_card = card
    return render_template(
        "dashboard/overview.html", project_count=project_count,
        order_count=len(orders), card_count=len(cards),
        default_card=default_card, subscription=get_user_subscription(user_id),
        workflow_tiers=WORKFLOW_TIERS,
    )


@dashboard_bp.get("/dashboard/projects")
@login_required
def projects():
    search = request.args.get("query", "").strip()
    status = request.args.get("status", "")
    status_filter = ""
    if status in PROJECT_STATUS_LABELS:
        status_filter = status

    shown = get_project_list(session["user_id"], search=search, status=status_filter)
    total = count_projects(session["user_id"])
    status_options = []
    for value, label in PROJECT_STATUS_LABELS.items():
        status_options.append({"value": value, "label": label})
    return render_template("dashboard/projects.html", projects=shown, total=total, search=search,
                           status=status, statuses=status_options,
                           workflow_tiers=WORKFLOW_TIERS)


def get_project_or_404(project_id):
    project = get_project_details(project_id, session["user_id"])
    if project is None:
        abort(404)
    return project


@dashboard_bp.get("/dashboard/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = get_project_or_404(project_id)
    return redirect(url_for("planner.planning_job", job_id=project["job_id"]))


# Return to the "Saved project" controls after an update.
def back_to_saved_project(project):
    return redirect(url_for("planner.planning_job", job_id=project["job_id"], _anchor="save-project"), code=303)


@dashboard_bp.post("/dashboard/projects/<int:project_id>/rename")
@login_required
def project_rename(project_id):
    project = get_project_or_404(project_id)
    try:
        rename_project(project_id, session["user_id"], request.form.get("name"))
        flash("Project name saved.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return back_to_saved_project(project)


@dashboard_bp.post("/dashboard/projects/<int:project_id>/completed")
@login_required
def project_completed(project_id):
    project = get_project_or_404(project_id)
    completed = request.form.get("completed") == "yes"
    set_project_completed(project_id, session["user_id"], completed)
    if completed:
        flash("Project marked as completed.", "success")
    else:
        flash("Project reopened.", "success")
    return back_to_saved_project(project)


@dashboard_bp.post("/dashboard/projects/<int:project_id>/crew/remove")
@login_required
def project_crew_remove(project_id):
    project = get_project_or_404(project_id)
    save_project_crew(project_id, session["user_id"], None)
    flash("Crew removed from this project.", "success")
    return back_to_saved_project(project)


@dashboard_bp.post("/dashboard/projects/<int:project_id>/crew")
@login_required
def project_crew(project_id):
    get_project_or_404(project_id)
    try:
        crew = parse_crew(request.form.get("crew"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("crews.crews", project_id=project_id))
    save_project_crew(project_id, session["user_id"], crew)
    flash("Crew saved to this project.", "success")
    return redirect(url_for("dashboard.project_detail", project_id=project_id, _anchor="crew"))


@dashboard_bp.post("/dashboard/projects/<int:project_id>/delete")
@login_required
def project_delete(project_id):
    project = get_project_or_404(project_id)
    delete_project(project_id, session["user_id"])
    flash("Project removed. Planning history kept.", "success")
    if request.form.get("return_to") == "history":
        return redirect(url_for("planner.planning_history"), code=303)
    if request.form.get("return_to") == "plan":
        return redirect(url_for("planner.planning_job", job_id=project["job_id"]), code=303)
    return redirect(url_for("dashboard.projects"))


@dashboard_bp.get("/dashboard/orders")
@login_required
def orders():
    return render_template("dashboard/orders.html", orders=get_user_orders(session["user_id"]))


@dashboard_bp.get("/dashboard/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = get_order(order_id, session["user_id"])
    if order is None:
        abort(404)
    items = get_order_items(order_id, session["user_id"])
    add_receipt_totals(order, items)
    return render_template("dashboard/order_detail.html", order=order, items=items)


def show_settings(profile=None, profile_error=None, password_error=None):
    """Render settings with errors from either the profile or password form."""
    user_id = session["user_id"]
    if profile is None:
        profile = get_profile(user_id)
        if profile is None:
            abort(404)
    status = 400 if profile_error or password_error else 200
    return render_template(
        "dashboard/settings.html", profile=profile, profile_error=profile_error, password_error=password_error,
    ), status


@dashboard_bp.route("/dashboard/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "GET":
        return show_settings()

    # Use the session's user ID so the form cannot target another account.
    user_id = session["user_id"]
    try:
        new_profile = check_profile_form(request.form)
        update_profile(user_id, new_profile)
    except ValueError as problem:
        error = str(problem)
    except IntegrityError:
        error = "Another account already uses that email."
    except Error:
        current_app.logger.exception("Unable to update account %s", user_id)
        error = "Couldn't save changes. Try again."
    else:
        session["display_name"] = full_name(new_profile["firstName"], new_profile["lastName"])
        flash("Account updated.", "success")
        return redirect(url_for("dashboard.settings"), code=303)

    profile = get_profile(user_id)
    if profile is None:
        abort(404)
    # Keep submitted values after errors.
    profile = dict(profile)
    profile.update(request.form.to_dict())
    return show_settings(profile=profile, profile_error=error)


@dashboard_bp.post("/dashboard/settings/password")
@login_required
def change_password():
    try:
        change_user_password(
            session["user_id"], request.form.get("current_password", ""),
            request.form.get("new_password", ""), request.form.get("confirm_password", ""),
        )
    except ValueError as problem:
        return show_settings(password_error=str(problem))
    except Error:
        current_app.logger.exception("Unable to change the password for account %s", session["user_id"])
        return show_settings(password_error="Couldn't change password. Try again.")
    flash("Password changed.", "success")
    return redirect(url_for("dashboard.settings"), code=303)


@dashboard_bp.post("/dashboard/users/<int:user_id>/status")
def change_user_status(user_id):
    if "user_id" not in session or session.get("permission_level") != "admin":
        abort(403)
    if user_id == session.get("user_id"):
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("dashboard.dashboard"))

    status = request.form.get("status")
    try:
        found = set_user_status(user_id, status)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("dashboard.dashboard"))
    except Error:
        current_app.logger.exception("Unable to change status for user %s", user_id)
        flash("Unable to change account status. Try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if not found:
        flash("User not found.", "error")
    elif status == "disabled":
        flash("Account disabled.", "success")
    else:
        flash("Account enabled.", "success")
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.post("/dashboard/users/<int:user_id>/delete")
def delete_user(user_id):
    if "user_id" not in session or session.get("permission_level") != "admin":
        abort(403)
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("dashboard.dashboard"))
    # Check DELETE on the server too.
    if request.form.get("confirm_text") != "DELETE":
        flash("Type DELETE to confirm.", "error")
        return redirect(url_for("dashboard.dashboard"))

    try:
        deleted = delete_user_completely(user_id)
    except Error:
        current_app.logger.exception("Deleting user %s failed", user_id)
        flash("Unable to delete user. Try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if deleted:
        flash("User deleted.", "success")
    else:
        flash("User not found.", "error")
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard/payments", methods=["GET", "POST"])
@login_required
def payments():
    if request.method == "POST":
        try:
            save_card(session["user_id"], validate_card(request.form))
            flash("Card saved.", "success")
        except ValueError as error:
            flash(str(error), "error")
        return redirect(url_for("dashboard.payments"), code=303)
    return render_template("dashboard/payments.html", cards=list_cards(session["user_id"]))


@dashboard_bp.route("/dashboard/payments/<int:card_id>/edit", methods=["GET", "POST"])
@login_required
def payment_edit(card_id):
    card = get_card(session["user_id"], card_id)
    if request.method == "POST":
        try:
            save_card(session["user_id"], validate_card(request.form, existing_card=card), card_id)
            flash("Card updated.", "success")
            return redirect(url_for("dashboard.payments"), code=303)
        except ValueError as error:
            flash(str(error), "error")
    return render_template("dashboard/payments.html", cards=[], editing=card)


@dashboard_bp.post("/dashboard/payments/<int:card_id>/delete")
@login_required
def payment_delete(card_id):
    delete_card(session["user_id"], card_id)
    flash("Card removed.", "success")
    return redirect(url_for("dashboard.payments"), code=303)


@dashboard_bp.post("/dashboard/payments/<int:card_id>/default")
@login_required
def payment_default(card_id):
    card = get_card(session["user_id"], card_id)
    card["is_default"] = True
    save_card(session["user_id"], card, card_id)
    flash("Default card updated.", "success")
    return redirect(url_for("dashboard.payments"), code=303)
