from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.passwords import MAX_PASSWORD_LENGTH, check_password
from utils.rate_limits import limiter
from utils.users import create_user

auth_bp = Blueprint("auth", __name__)


def start_session(user_id, display_name, permission_level):
    # Clear the old login and CSRF token first.
    session.clear()
    session["user_id"] = user_id
    session["display_name"] = display_name
    session["permission_level"] = permission_level


def check_logged_in_user():
    # Refresh the account each request so name, role, and status changes take effect.
    if "user_id" not in session or request.endpoint == "static":
        return None

    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.firstName, u.lastName, u.permissions, c.accountStatus
               FROM `User` u
               JOIN Customer c ON c.userId = u.id
               WHERE u.id = %s""",
            (session["user_id"],),
        )
        user = cursor.fetchone()

    if user is None or user["accountStatus"] != "active":
        session.clear()
        return None

    session["display_name"] = (user["firstName"] + " " + user["lastName"]).strip()
    session["permission_level"] = user["permissions"]
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    
    data = request.get_json(silent=True)
    
    if not isinstance(data, dict):
        return {"error": "Invalid form data."}, 400

    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        return {"error": "Invalid form data."}, 400
    email = email.strip()
    # Reject oversized passwords before hashing them.
    if len(password) > MAX_PASSWORD_LENGTH:
        return {"error": "Invalid email or password."}, 401

    try:
        with database_cursor() as cursor:
            cursor.execute(
                """SELECT u.id, u.firstName, u.lastName, u.passkey, u.permissions, c.accountStatus
                   FROM `User` u
                   JOIN Customer c ON c.userId = u.id
                   WHERE u.email = %s""",
                (email,),
            )
            user = cursor.fetchone()

    except Error:
        current_app.logger.exception("Login database query failed")
        return {"error": "Login unavailable."}, 503

    if user is None or not check_password(user["passkey"], password):
        return {"error": "Invalid email or password."}, 401
    # Show account status only after the password has been verified.
    if user["accountStatus"] != "active":
        return {"error": "This account is disabled."}, 403

    start_session(user["id"], (user["firstName"] + " " + user["lastName"]).strip(), user["permissions"])
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
        return {"error": "Email already in use."}, 409
    except Error:
        current_app.logger.exception("Registration failed")
        return {"error": "Registration unavailable."}, 503

    start_session(user_id, data["firstName"].strip() + " " + data["lastName"].strip(), "user")
    return {"redirect_url": url_for("dashboard.dashboard")}, 201


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
