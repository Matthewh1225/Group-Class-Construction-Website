from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.database import database_cursor
from utils.passwords import verify_password
from utils.users import create_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    data = request.get_json(silent=True)
    username = data.get("username", "")
    password = data.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        return {"error": "Enter valid text fields."}, 400
    username = username.strip()

    try:
        with database_cursor() as cursor:
            cursor.execute(
                """SELECT id, username, password_hash, permission_level
                   FROM users WHERE username = %s OR email = %s LIMIT 1""",
                (username, username),
            )
            user = cursor.fetchone()

    except Error:
        current_app.logger.exception("Login database query failed")
        return {"error": "Login unavailable."}, 503

    if user is None or not verify_password(password, user["password_hash"]):
        return {"error": "Invalid username or password."}, 401

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["permission_level"] = user["permission_level"]
    return {"redirect_url": url_for("dashboard.dashboard")}


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Invalid form data."}, 400

    try:
        create_user(data)
    except ValueError as error:
        return {"error": str(error)}, 400
    except IntegrityError:
        return {"error": "That username or email is already in the database."}, 409
    except Error:
        current_app.logger.exception("Registration failed")
        return {"error": "Registration unavailable."}, 503

    return {"redirect_url": url_for("auth.login")}, 201


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
