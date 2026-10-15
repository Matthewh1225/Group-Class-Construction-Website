from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.users import create_user, delete_user as delete_user_record

dashboard_bp = Blueprint("dashboard", __name__)


def dashboard_login_required(view):
    """Use the existing session login for new dashboard pages."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped

# reload permissions from the database before each dashboard request
@dashboard_bp.before_request
def refresh_dashboard_user():
    if "user_id" not in session:
        return

    try:
        with database_cursor() as cursor:
            cursor.execute(
                "SELECT username, permission_level FROM users WHERE id = %s",
                (session["user_id"],),
            )
            user = cursor.fetchone()
    except Error:
        current_app.logger.exception("Dashboard account lookup failed")
        return "Dashboard is temporarily unavailable.", 503

    if user is None:
        session.clear()
        return redirect(url_for("auth.login"))

    session["username"] = user.get("username")
    session["permission_level"] = user.get("permission_level")


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    permission_level = session.get("permission_level", "user")

    if request.method == "POST":
        if permission_level != "admin":
            abort(403)

        permission_lvl = request.form.get("permission_level", "user")
        try:
            create_user(request.form, permission_lvl)
            flash("User created successfully.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            flash("That username or email is already in use.", "error")
        except Error:
            flash("The user could not be created.", "error")

        # redirect after POST so refreshing does not create the user again
        return redirect(url_for("dashboard.dashboard"))

    if permission_level == "admin":
        try:
            with database_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, email, permission_level, created_at
                    FROM users
                    ORDER BY id
                    """
                )
                users = cursor.fetchall()
        except Error:
            current_app.logger.exception("Dashboard user list lookup failed")
            return "Dashboard is temporarily unavailable.", 503

        return render_template(
            "admin_dashboard.html", username=session.get("username"),
            permission_level=permission_level, users=users, admin_workspace=True,
        )

    return render_template(
        "dashboard/overview.html", username=session.get("username"),
        recent_projects=[], project_count=None, material_list_count=None,
        cart_count=None,
    )


@dashboard_bp.get("/dashboard/projects")
@dashboard_login_required
def projects():
    return render_template("dashboard/projects.html", projects=[])


@dashboard_bp.get("/dashboard/projects/<int:project_id>")
@dashboard_login_required
def project_detail(project_id):
    return render_template("dashboard/project_detail.html", project=None)


@dashboard_bp.get("/dashboard/material-lists")
@dashboard_login_required
def material_lists():
    return render_template("dashboard/material_lists.html", project_lists=[])


@dashboard_bp.get("/dashboard/projects/<int:project_id>/materials")
@dashboard_login_required
def material_list_detail(project_id):
    return render_template(
        "dashboard/material_list_detail.html", project=None,
        material_list=None, materials=[], estimated_total=None,
    )


@dashboard_bp.get("/dashboard/orders")
@dashboard_login_required
def orders():
    return render_template("dashboard/orders.html", orders=[])


@dashboard_bp.get("/dashboard/orders/<int:order_id>")
@dashboard_login_required
def order_detail(order_id):
    return render_template("dashboard/order_detail.html", order=None, items=[])


@dashboard_bp.get("/dashboard/settings")
@dashboard_login_required
def settings():
    return render_template(
        "dashboard/settings.html", profile={"username": session.get("username", "")},
    )


@dashboard_bp.post("/dashboard/users/<int:user_id>/delete")
def delete_user(user_id):
    #only admins & no self deletes
    if "user_id" not in session or session.get("permission_level") != "admin":
        abort(403)
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("dashboard.dashboard"))

    try:
        deleted = delete_user_record(user_id)
    except Error:
        flash("The user could not be deleted.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if deleted:
        flash("User deleted successfully.", "success")
    else:
        flash("User not found.", "error")

    return redirect(url_for("dashboard.dashboard"))
