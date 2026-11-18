import os

from dotenv import load_dotenv
from flask import Flask, render_template, session, url_for
from mysql.connector import Error as DatabaseError

# Load .env before routes create their AI clients.
load_dotenv()

from routes.auth import auth_bp, refresh_logged_in_user
from routes.crews import crews_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import PRODUCT_CATEGORIES, products_bp
from routes.reviews import reviews_bp
from routes.shopping import shopping_bp
from routes.subscription import subscription_bp
from planning.presentation import format_amount
from utils.csrf import check_csrf, csrf_token
from utils.database import DatabaseBusyError, close_database
from utils.rate_limits import check_request_limits, limiter
from utils.passwords import MAX_PASSWORD_LENGTH
from utils.assets import configure_static_cache
from services.cart import count_cart_lines
from services.products import get_manufacturers_by_category

app = Flask(__name__, template_folder="pages")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_NAME"] = "buildbetter_session"
# Keep session cookies out of cross-site POSTs.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set SESSION_COOKIE_SECURE=true when using HTTPS.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true"
# Reject oversized submissions before form parsing and database queries.
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
app.config["MAX_FORM_MEMORY_SIZE"] = 64 * 1024
app.config["MAX_FORM_PARTS"] = 100
configure_static_cache(app)
# Rate-limit requests before parsing forms or loading the account.
limiter.init_app(app)
app.before_request(check_request_limits)
app.before_request(check_csrf)
app.before_request(refresh_logged_in_user)
app.teardown_request(close_database)


@app.context_processor
def add_cart_count():
    # Shown as a badge on the nav cart link.
    if "user_id" not in session:
        return {"cart_count": 0}
    try:
        return {"cart_count": count_cart_lines(session["user_id"])}
    except DatabaseError:
        return {"cart_count": 0}


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["password_max_length"] = MAX_PASSWORD_LENGTH
app.jinja_env.filters["amount"] = format_amount

app.register_blueprint(auth_bp)
app.register_blueprint(planner_bp)
app.register_blueprint(products_bp)
app.register_blueprint(shopping_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(crews_bp)
app.register_blueprint(reviews_bp)
# Vector search is only loaded by the planner worker, so the web process never loads the model.


@app.errorhandler(429)
def too_many_requests(error):
    return {"error": "Too many requests. Please wait before trying again."}, 429


@app.errorhandler(413)
def request_too_large(error):
    return {"error": "This request is too large. Please shorten your submission."}, 413


@app.errorhandler(DatabaseError)
def database_unavailable(error):
    app.logger.error("Database error", exc_info=error)
    return render_template("unavailable.html"), 503


@app.errorhandler(DatabaseBusyError)
def database_busy(error):
    app.logger.warning("Database request busy: %s", error)
    return render_template("unavailable.html", message=str(error)), 409


@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")


@app.get("/contact")
def contact():
    return render_template("contact.html",
                           contact_email=os.getenv("CONTACT_EMAIL", "contact-us@buildbetter.lol").strip(),
                           contact_phone=os.getenv("CONTACT_PHONE", "+1-555-010-0142").strip(),
                           contact_fax=os.getenv("CONTACT_FAX", "+1-555-010-0143").strip(),
                           contact_linkedin=os.getenv("CONTACT_LINKEDIN", "https://www.linkedin.com/company/buildbetter").strip())


@app.route("/manufacturers")
def manufacturers():
    by_category = get_manufacturers_by_category()
    # Same order and names as the product page; heavy machinery has its own page.
    categories = [(category["url_name"], category["name"], "products.products") for category in PRODUCT_CATEGORIES]
    categories.append(("heavy-machinery", "Heavy Machinery", "products.heavy_machinery"))

    groups = []
    for url_name, name, endpoint in categories:
        makers = by_category.get(url_name, [])
        if not makers:
            continue
        for maker in makers:
            if url_name == "heavy-machinery":
                maker["catalog_url"] = url_for(endpoint, manufacturer=maker["manufacturer_id"])
            else:
                maker["catalog_url"] = url_for(endpoint, manufacturer=maker["manufacturer_id"], category=url_name)
        groups.append({"url_name": url_name, "name": name, "manufacturers": makers})
    return render_template("manufacturers.html", groups=groups)


if __name__ == "__main__":
    # Port 5000 may be used by AirPlay on macOS.
    app.run(debug=True, port=5001)
