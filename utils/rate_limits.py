import os

from flask import request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

storage_uri = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
limiter = Limiter(
    key_func=get_remote_address,
    # Memory storage only counts requests in this process.
    storage_uri=storage_uri,
    storage_options={"socket_connect_timeout": 2, "socket_timeout": 2}
        if storage_uri.startswith(("redis://", "rediss://")) else {},
    # Shared across dynamic endpoints so changing URLs does not reset the budget.
    application_limits=["20 per second", "200 per minute"],
    headers_enabled=True,
    # Count recent requests instead of resetting at fixed times.
    strategy="moving-window",
)


@limiter.request_filter
def static_asset_request():
    return request.endpoint == "static"


def account_rate_limit_key():
    user_id = session.get("user_id")
    if user_id is not None:
        return f"account:{user_id}"
    return f"guest:{get_remote_address()}"


POST_LIMITS = {
    "reviews": "5 per minute; 20 per hour",
    "auth.login": "10 per minute; 50 per hour",
    "auth.register": "5 per minute; 20 per hour",
    "auth.google_login": "10 per minute; 50 per hour",
    "planner.submit_planning_job": "4 per minute; 30 per hour",
    "planner.planning_job_add_to_cart": "30 per minute",
    "planner.planning_job_answers": "4 per minute; 30 per hour",
    "planner.planning_job_restart": "4 per minute; 30 per hour",
}


def check_request_limits():
    # Flask-Limiter skips unresolved routes; don't let those reach account queries.
    if request.routing_exception is not None:
        raise request.routing_exception
    if request.endpoint == "static":
        return
    if session.get("user_id") is not None:
        with limiter.shared_limit("10 per second; 200 per minute", key_func=account_rate_limit_key,
                                  scope="account-traffic"):
            pass
    if request.endpoint in {"products.products", "products.heavy_machinery", "manufacturers", "reviews"} and request.method in {"GET", "HEAD"}:
        # Page changes and search terms share one catalog budget.
        with limiter.shared_limit("10 per second; 200 per minute", scope="catalog-traffic"):
            pass
    # Context limits run here, before account refresh, rather than in the views.
    policy = POST_LIMITS.get(request.endpoint)
    if request.method != "POST" or policy is None:
        return
    with limiter.limit(policy, scope=f"early-{request.endpoint}-ip"):
        pass
    if request.endpoint == "reviews":
        with limiter.limit("5 per minute; 20 per hour", key_func=account_rate_limit_key,
                           scope="review-post-account"):
            pass
