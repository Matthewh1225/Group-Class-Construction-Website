from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.users import create_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    permission_level = session.get("permission_level", "user")

    if request.method == "POST":
        if permission_level != "admin":
            abort(403)

        new_permission = request.form.get("permission_level", "user")
        try:
            create_user(request.form, new_permission)
            flash("User created.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            flash("That username or emai in use.", "error")
        except Error:
            flash(" user could not be created.")

        return redirect(url_for("dashboard.dashboard"))

    users = []
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
            flash("The user list could not be loaded.", "error")

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        permission_level=permission_level,
        users=users,
    )


@dashboard_bp.post("/dashboard/users/<int:user_id>/delete")
def delete_user(user_id):
    if session.get("permission_level") != "admin":
        abort(403)
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("dashboard.dashboard"))

    try:
        with database_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            deleted = cursor.rowcount
    except Error:
        flash("The user could not be deleted.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if deleted:
        flash("User deleted.", "success")
    else:
        flash("User not found.", "error")

    return redirect(url_for("dashboard.dashboard"))
