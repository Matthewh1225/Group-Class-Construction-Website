from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.passwords import MAX_PASSWORD_LENGTH, check_password, hash_password, needs_new_hash
from utils.rate_limits import limiter
from utils.users import create_user

auth_bp = Blueprint("auth", __name__)


def start_session(user_id, username, permission_level):
    # Clear the old login and CSRF token first.
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    session["permission_level"] = permission_level


def check_logged_in_user():
    # Refresh the account each request so name, role, and status changes take effect.
    if "user_id" not in session or request.endpoint == "static":
        return None

    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.username, u.status,
                      CASE WHEN a.user_Id IS NULL THEN 'user' ELSE 'admin' END AS permission_level
               FROM `User` u
               LEFT JOIN Administrator a ON a.user_Id = u.Id
               WHERE u.Id = %s""",
            (session["user_id"],),
        )
        user = cursor.fetchone()

    if user is None or user["status"] == "disabled":
        session.clear()
        return None

    session["username"] = user["username"]
    session["permission_level"] = user["permission_level"]
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    
    data = request.get_json(silent=True)
    
    if not isinstance(data, dict):
        return {"error": "Invalid form data."}, 400

    username = data.get("username", "")
    password = data.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        return {"error": "Invalid form data."}, 400
    username = username.strip()
    # Reject oversized passwords before hashing them.
    if len(password) > MAX_PASSWORD_LENGTH:
        return {"error": "Invalid username or password."}, 401

    try:
        with database_cursor() as cursor:
            # An Administrator row makes the user an admin.
            cursor.execute(
                """SELECT u.Id, u.username, u.password, u.status,
                          CASE WHEN a.user_Id IS NULL THEN 'user' ELSE 'admin' END AS permission_level
                   FROM `User` u
                   LEFT JOIN Administrator a ON a.user_Id = u.Id
                   WHERE u.username = %s OR u.email = %s LIMIT 1""",
                (username, username),
            )
            user = cursor.fetchone()

    except Error:
        current_app.logger.exception("Login database query failed")
        return {"error": "Login unavailable."}, 503

    if user is None or not check_password(user["password"], password):
        return {"error": "Invalid username or password."}, 401
    # Show account status only after the password has been verified.
    if user["status"] == "disabled":
        return {"error": "This account is disabled."}, 403
    if needs_new_hash(user["password"]):
        try:
            with database_cursor() as cursor:
                cursor.execute("UPDATE `User` SET password = %s WHERE Id = %s",
                               (hash_password(password), user["Id"]))
        except Error:
            current_app.logger.exception("Could not update the password hash for user %s", user["Id"])

    start_session(user["Id"], user["username"], user["permission_level"])
    return {"redirect_url": url_for("dashboard.dashboard")}


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Invalid form data."}, 400

    try:
        user_id = create_user(data)
    except ValueError as error:
        return {"error": str(error)}, 400
    except IntegrityError:
        return {"error": "Username or email already in use."}, 409
    except Error:
        current_app.logger.exception("Registration failed")
        return {"error": "Registration unavailable."}, 503

    start_session(user_id, data["username"].strip(), "user")
    return {"redirect_url": url_for("dashboard.dashboard")}, 201


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
