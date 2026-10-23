import json
import os
from functools import wraps
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from mysql.connector import Error, IntegrityError

from utils.passwords import MAX_PASSWORD_LENGTH
from utils.rate_limits import limiter
from utils.users import check_login, create_user, find_or_create_google_user, full_name, get_account

auth_bp = Blueprint("auth", __name__)


def login_required(view):
    # Keep each route's name so Flask can tell the wrapped views apart.
    @wraps(view)
    def check_login_before_view(*args, **kwargs):
        is_logged_in = "user_id" in session
        if not is_logged_in:
            login_url = url_for("auth.login")
            return redirect(login_url)
        return view(*args, **kwargs)

    return check_login_before_view


def start_session(user_id, display_name, permission_level):
    # A new login needs a fresh CSRF token.
    session.clear()
    session["user_id"] = user_id
    session["display_name"] = display_name
    session["permission_level"] = permission_level


def refresh_logged_in_user():
    if "user_id" not in session or request.endpoint == "static":
        return None

    user = get_account(session["user_id"])
    if user is None or user["accountStatus"] != "active":
        session.clear()
        return None

    session["display_name"] = full_name(user["firstName"], user["lastName"])
    session["permission_level"] = user["permissions"]
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", google_client_id=os.getenv("GOOGLE_CLIENT_ID"))
    
    data = request.get_json(silent=True)
    
    if not isinstance(data, dict):
        return {"error": "Invalid form data."}, 400

    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        return {"error": "Invalid form data."}, 400
    email = email.strip()
    if len(password) > MAX_PASSWORD_LENGTH:
        return {"error": "Invalid email or password."}, 401

    try:
        user = check_login(email, password)
    except Error:
        current_app.logger.exception("Login database query failed")
        return {"error": "Login unavailable."}, 503

    if user is None:
        return {"error": "Invalid email or password."}, 401
    if user["accountStatus"] != "active":
        return {"error": "This account is disabled."}, 403

    start_session(user["id"], full_name(user["firstName"], user["lastName"]), user["permissions"])
    return {"redirect_url": url_for("dashboard.dashboard")}


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", google_client_id=os.getenv("GOOGLE_CLIENT_ID"))

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

    start_session(user_id, full_name(data["firstName"].strip(), data["lastName"].strip()), "user")
    return {"redirect_url": url_for("dashboard.dashboard")}, 201


# Ask Google whether this sign-in token is real and was made for our app.
def read_google_token(token):
    url = "https://oauth2.googleapis.com/tokeninfo?" + urlencode({"id_token": token})
    with urlopen(url, timeout=5) as response:
        info = json.load(response)
    if info.get("aud") != os.getenv("GOOGLE_CLIENT_ID"):
        return None
    if info.get("email_verified") not in (True, "true"):
        return None
    return info


@auth_bp.route("/google-login", methods=["POST"])
@limiter.limit("10 per minute; 50 per hour")
def google_login():
    data = request.get_json(silent=True)
    token = data.get("credential") if isinstance(data, dict) else None
    if not isinstance(token, str) or not os.getenv("GOOGLE_CLIENT_ID"):
        return {"error": "Google sign-in unavailable."}, 400

    try:
        info = read_google_token(token)
        if info is None:
            return {"error": "Google sign-in failed."}, 401
        first_name = info.get("given_name") or info["email"].split("@")[0]
        user = find_or_create_google_user(info["email"], first_name, info.get("family_name", ""))
    except Error:
        current_app.logger.exception("Google sign-in database query failed")
        return {"error": "Google sign-in unavailable."}, 503
    except (OSError, ValueError):
        current_app.logger.exception("Google token check failed")
        return {"error": "Google sign-in failed."}, 401

    if user["accountStatus"] != "active":
        return {"error": "This account is disabled."}, 403
    start_session(user["id"], full_name(user["firstName"], user["lastName"]), user["permissions"])
    return {"redirect_url": url_for("dashboard.dashboard")}


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
