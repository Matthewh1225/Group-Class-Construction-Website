import json
import os
import ssl
from functools import wraps
from urllib.parse import urlencode
from urllib.request import urlopen
import time
import certifi
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for,flash
from mysql.connector import Error, IntegrityError

from utils.passwords import MAX_PASSWORD_LENGTH
from utils.rate_limits import limiter
from utils.users import check_login, create_user, find_or_create_google_user, full_name, get_account

auth_bp = Blueprint("auth", __name__)

# Use certifi for Google's HTTPS certificate check.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

INACTIVITY_LIMIT =  60 *20 # 20 min without a request before logging out


def login_required(view):
    # Keep the route name for Flask.
    @wraps(view)
    def check_login_before_view(*args, **kwargs):
        is_logged_in = "user_id" in session
        if not is_logged_in:
            login_url = url_for("auth.login")
            return redirect(login_url)
        return view(*args, **kwargs)

    return check_login_before_view


def start_session(user_id, display_name, role):
    # A new login needs a fresh CSRF token.
    session.clear()
    session["last_active"] = time.time()
    session["user_id"] = user_id
    session["display_name"] = display_name
    session["permission_level"] = role


# Cache account details for GETs; check MySQL for POSTs.
def refresh_logged_in_user():
    if "user_id" not in session or request.endpoint == "static":
        return None

    # Log out inactive users.
    last_active = session.get("last_active", 0)
    if time.time() - last_active > INACTIVITY_LIMIT:
        session.clear()
        flash(f"You were logged out after {INACTIVITY_LIMIT / 60:g} minutes of inactivity.", "message")
        return None
    session["last_active"] = time.time()

    user = get_account(session["user_id"], use_cache=request.method in ("GET", "HEAD"))
    if user is None or user["accountStatus"] != "active":
        session.clear()
        return None

    session["display_name"] = full_name(user["firstName"], user["lastName"])
    session["permission_level"] = user["role"]
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

    start_session(user["id"], full_name(user["firstName"], user["lastName"]), user["role"])
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


# Ask Google to check the sign-in token.
def read_google_token(token):
    url = "https://oauth2.googleapis.com/tokeninfo?" + urlencode({"id_token": token})
    with urlopen(url, timeout=5, context=SSL_CONTEXT) as response:
        info = json.load(response)

    if info.get("aud") != os.getenv("GOOGLE_CLIENT_ID"):
        current_app.logger.warning("Google token client ID does not match")
        return None

    if info.get("email_verified") not in (True, "true"):
        current_app.logger.warning("Google email is not verified")
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
            current_app.logger.warning("read_google_token returned None")
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
    start_session(user["id"], full_name(user["firstName"], user["lastName"]), user["role"])
    return {"redirect_url": url_for("dashboard.dashboard")}


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
