import os

from dotenv import load_dotenv
from flask import Flask, render_template, url_for
from mysql.connector import Error as DatabaseError

# Load .env before routes create their AI clients.
load_dotenv()

from routes.auth import auth_bp, refresh_logged_in_user
from routes.crews import crews_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import products_bp
from routes.reviews import reviews
from routes.shopping import shopping_bp
from routes.subscription import subscription_bp
from planning.presentation import format_amount
from utils.csrf import check_csrf, csrf_token
from utils.database import close_database
from utils.rate_limits import check_request_limits, limiter
from utils.passwords import MAX_PASSWORD_LENGTH
from services.products import get_all_manufacturers
from services.vector_search import load_vector_search

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
# Register rate limiting before CSRF parsing and account refresh/database access.
limiter.init_app(app)
app.before_request(check_request_limits)
# Check CSRF and login; close database connections after requests.
app.before_request(check_csrf)
app.before_request(refresh_logged_in_user)
app.teardown_request(close_database)


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

# Load product vectors once; use keyword search if loading fails.
load_vector_search()


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


@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")


app.add_url_rule("/reviews", view_func=reviews, methods=["GET", "POST"])


@app.route("/manufacturers")
def manufacturers():
    manufacturers = get_all_manufacturers()
    for manufacturer in manufacturers:
        endpoint = "products.products"
        if manufacturer["has_machinery"]:
            endpoint = "products.heavy_machinery"
        manufacturer["catalog_url"] = url_for(endpoint, manufacturer=manufacturer["manufacturer_id"])
    return render_template("manufacturers.html", manufacturers=manufacturers)


if __name__ == "__main__":
    # Port 5000 may be used by AirPlay on macOS.
    app.run(debug=True, port=5001)
