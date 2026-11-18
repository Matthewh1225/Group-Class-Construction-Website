import json
import os
import ssl
from functools import wraps
from urllib.parse import urlencode
from urllib.request import urlopen
import time
import certifi
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for, flash
from mysql.connector import Error, IntegrityError

from services.cart import add_item
from utils.passwords import MAX_PASSWORD_LENGTH
from utils.users import check_login, create_user, find_or_create_google_user, full_name, get_account

auth_bp = Blueprint("auth", __name__)

# Use certifi for Google's HTTPS certificate check.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

INACTIVITY_LIMIT = 60 * 20  # log out after 20 minutes without a request


def login_required(view):
    @wraps(view)
    def check_login_before_view(*args, **kwargs):
        is_logged_in = "user_id" in session
        if not is_logged_in:
            # After logging in, send them back to the page they wanted.
            if request.method == "GET":
                session["after_login"] = {"next": request.full_path.rstrip("?")}
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return check_login_before_view


def is_local_path(path):
    # Only follow links inside this site.
    return isinstance(path, str) and path.startswith("/") and not path.startswith("//") and "\\" not in path


def after_login_url(user_id):
    """Finish what the visitor was doing before logging in, and return where to send them."""
    pending = session.pop("after_login", None) or {}
    product = pending.get("add_product")
    if product:
        try:
            name = add_item(user_id, product["product_id"], product["quantity"])
            flash("Added " + name + " to your cart.", "success")
        except ValueError as error:
            flash(str(error), "error")
    if is_local_path(pending.get("next")):
        return pending["next"]
    return url_for("dashboard.dashboard")


def start_session(user_id, display_name, role):
    # Keep the page or cart item the visitor was waiting on.
    after_login = session.get("after_login")
    # A new login needs a fresh CSRF token.
    session.clear()
    if after_login:
        session["after_login"] = after_login
    session["last_active"] = time.time()
    session["user_id"] = user_id
    session["display_name"] = display_name
    session["permission_level"] = role


# Cache account details for GETs; check MySQL for POSTs.
def refresh_logged_in_user():
    if "user_id" not in session or request.endpoint == "static":
        return None

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
    return {"redirect_url": after_login_url(user["id"])}


@auth_bp.route("/register", methods=["GET", "POST"])
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
    return {"redirect_url": after_login_url(user_id)}, 201


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
    return {"redirect_url": after_login_url(user["id"])}


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
