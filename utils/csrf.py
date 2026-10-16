import secrets

from flask import abort, request, session


def csrf_token():
    # made once per session; login clears the session
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def check_csrf():
    # Runs before every request. A POST without this session's token is rejected  before any route code runs
    if request.method != "POST":
        return None
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")

    if expected and secrets.compare_digest(expected.encode(), supplied.encode()):
        return None
    message = "Form expired. Reload the page."
    if request.is_json:
        return {"error": message}, 400
    abort(400, description=message)
