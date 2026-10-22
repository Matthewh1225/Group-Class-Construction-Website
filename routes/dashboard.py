import sqlite3
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from planning.presentation import add_store_details
from services.orders import get_order_by_id, get_order_items, get_user_orders
from services.crews import CREW_RATES, HOURS_PER_DAY, parse_crew, crew_estimate
from services.projects import (delete_project, get_project, get_project_count, get_user_projects,
                               rename_project, save_project_crew, set_project_completed)
from utils.database import database_cursor
from utils.users import create_user, delete_user_completely, set_user_status

dashboard_bp = Blueprint("dashboard", __name__)


def dashboard_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped

# The sign-in check refreshes the role each request.
@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
@dashboard_login_required
def dashboard():
    permission_level = session.get("permission_level", "user")

    if request.method == "POST":
        if permission_level != "admin":
            abort(403)

        permission_lvl = request.form.get("permission_level", "user")
        try:
            create_user(request.form, permission_lvl)
            flash("User created.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            flash("Email already in use.", "error")
        except Error:
            current_app.logger.exception("Unable to create an admin user")
            flash("User creation is temporarily unavailable. Nothing was changed.", "error")

        # Redirect so refreshing does not create another user.
        return redirect(url_for("dashboard.dashboard"))

    if permission_level == "admin":
        users_error = False
        try:
            with database_cursor() as cursor:
                cursor.execute(
                    """SELECT u.id, CONCAT_WS(' ', u.firstName, NULLIF(u.lastName, '')) AS display_name,
                              u.email, u.permissions, u.dateCreated, c.accountStatus
                       FROM `User` u
                       JOIN Customer c ON c.userId = u.id
                       ORDER BY u.id"""
                )
                users = cursor.fetchall()
        except Error:
            current_app.logger.exception("Unable to load the admin user list")
            g.database_unavailable = True
            users = []
            users_error = True
        return render_template(
            "admin_dashboard.html", display_name=session.get("display_name"),
            permission_level=permission_level, users=users, users_error=users_error,
            admin_workspace=True,
        )

    user_id = session["user_id"]
    return render_template(
        "dashboard/overview.html", display_name=session.get("display_name"),
        recent_projects=get_user_projects(user_id, limit=3),
        project_count=get_project_count(user_id), cart_count=None,
    )


PROJECT_STATUSES = ["In Progress", "Review Needed", "Ready", "Completed"]


@dashboard_bp.get("/dashboard/projects")
@dashboard_login_required
def projects():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    all_projects = get_user_projects(session["user_id"])
    if all_projects is None:
        return render_template("unavailable.html", message="Projects unavailable."), 503
    shown = []
    for project in all_projects:
        if search and search.lower() not in project["name"].lower():
            continue
        if status in PROJECT_STATUSES and project["status"] != status:
            continue
        shown.append(project)
    return render_template("dashboard/projects.html", projects=shown, total=len(all_projects),
                           search=search, status=status, statuses=PROJECT_STATUSES)


def owned_project(project_id):
    project = get_project(project_id, session["user_id"])
    if project is None:
        abort(404)
    return project


@dashboard_bp.get("/dashboard/projects/<int:project_id>")
@dashboard_login_required
def project_detail(project_id):
    project = owned_project(project_id)
    crew = None
    if project["crew"]:
        crew = crew_estimate(project["crew"])
    plan = project["plan"]
    materials = []
    if plan.get("result"):
        materials = add_store_details(plan["result"]["materials"])
    return render_template("dashboard/project_detail.html", project=project, plan=plan,
                           materials=materials, crew=crew,
                           crew_rates=CREW_RATES, hours_per_day=HOURS_PER_DAY)


@dashboard_bp.post("/dashboard/projects/<int:project_id>/rename")
@dashboard_login_required
def project_rename(project_id):
    owned_project(project_id)
    try:
        rename_project(project_id, session["user_id"], request.form.get("name"))
        flash("Project name saved.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("dashboard.project_detail", project_id=project_id))


@dashboard_bp.post("/dashboard/projects/<int:project_id>/completed")
@dashboard_login_required
def project_completed(project_id):
    owned_project(project_id)
    completed = request.form.get("completed") == "yes"
    set_project_completed(project_id, session["user_id"], completed)
    if completed:
        flash("Project marked as completed.", "success")
    else:
        flash("Project reopened.", "success")
    return redirect(url_for("dashboard.project_detail", project_id=project_id))


@dashboard_bp.post("/dashboard/projects/<int:project_id>/crew")
@dashboard_login_required
def project_crew(project_id):
    owned_project(project_id)
    try:
        crew = parse_crew(request.form.get("crew"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("crews.crews", project_id=project_id))
    save_project_crew(project_id, session["user_id"], crew)
    flash("Crew saved to this project.", "success")
    return redirect(url_for("dashboard.project_detail", project_id=project_id, _anchor="crew"))


@dashboard_bp.post("/dashboard/projects/<int:project_id>/crew/remove")
@dashboard_login_required
def project_crew_remove(project_id):
    owned_project(project_id)
    save_project_crew(project_id, session["user_id"], None)
    flash("Crew removed from this project.", "success")
    return redirect(url_for("dashboard.project_detail", project_id=project_id, _anchor="crew"))


@dashboard_bp.post("/dashboard/projects/<int:project_id>/delete")
@dashboard_login_required
def project_delete(project_id):
    # The AI plan stays in planning history when the saved project is deleted.
    owned_project(project_id)
    delete_project(project_id, session["user_id"])
    flash("Project deleted.", "success")
    return redirect(url_for("dashboard.projects"))


@dashboard_bp.get("/dashboard/orders")
@dashboard_login_required
def orders():
    return render_template("dashboard/orders.html", orders=get_user_orders(session["user_id"]))


@dashboard_bp.get("/dashboard/orders/<int:order_id>")
@dashboard_login_required
def order_detail(order_id):
    order = get_order_by_id(order_id, session["user_id"])
    if order is None:
        abort(404)
    items = get_order_items(order_id, session["user_id"])
    return render_template("dashboard/order_detail.html", order=order, items=items)


@dashboard_bp.get("/dashboard/settings")
@dashboard_login_required
def settings():
    return render_template(
        "dashboard/settings.html", profile={"display_name": session.get("display_name", "")},
    )


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
        flash("The account status could not be changed. Try again shortly.", "error")
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
    # Check the typed confirmation here too; the dialog alone is not enough.
    if request.form.get("confirm_text") != "DELETE":
        flash("Type DELETE to confirm. Nothing was deleted.", "error")
        return redirect(url_for("dashboard.dashboard"))

    try:
        deleted = delete_user_completely(user_id)
    # Planner jobs are deleted from SQLite, so its errors count too.
    except (Error, sqlite3.Error):
        current_app.logger.exception("Deleting user %s failed", user_id)
        flash("Unable to delete user. Nothing was removed.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if deleted:
        flash("User deleted.", "success")
    else:
        flash("User not found.", "error")
    return redirect(url_for("dashboard.dashboard"))
