from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.users import create_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.before_request
def refresh_dashboard_user():
    if "user_id" not in session:
        return

    with database_cursor() as cursor:
        cursor.execute(
            "SELECT username, permission_level FROM users WHERE id = %s",
            (session["user_id"],), )
        user = cursor.fetchone()

    if user is None:
        session.clear()
    else:
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

        new_permission = request.form.get("permission_level", "user")
        try:
            create_user(request.form, new_permission)
            flash("User created.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            flash("That username or email is already in use.", "error")
        except Error:
            flash("The user could not be created.", "error")

        return redirect(url_for("dashboard.dashboard"))

    users = []
    if permission_level == "admin":
            with database_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, email, permission_level, created_at
                    FROM users
                    ORDER BY id
                    """
                )
                users = cursor.fetchall()

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        permission_level=permission_level,
        users=users,)


@dashboard_bp.post("/dashboard/users/<int:user_id>/delete")
def delete_user(user_id):
    if "user_id" not in session or session.get("permission_level") != "admin":
        abort(403)
    if user_id == session.get("user_id"):
        flash("You cannot delete yourself dubmass.", "error")
        return redirect(url_for("dashboard.dashboard"))

    
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        deleted = cursor.rowcount
    if deleted:
        flash("User Gone Forever.", "success")
    else:
        flash("User not found.", "error")

    return redirect(url_for("dashboard.dashboard"))
