import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for
from mysql.connector import Error as DatabaseError

# Load .env before routes create their AI clients.
load_dotenv()

from routes.auth import auth_bp, refresh_logged_in_user
from routes.crews import crews_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import products_bp
from routes.shopping import shopping_bp
from routes.subscription import subscription_bp
from planning.presentation import format_amount
from utils.csrf import check_csrf, csrf_token
from utils.database import close_database
from utils.rate_limits import limiter
from utils.passwords import MAX_PASSWORD_LENGTH
from services.products import get_all_manufacturers

app = Flask(__name__, template_folder="pages")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
# Old sessions may contain test-database user IDs. Require a fresh sign-in.
app.config["SESSION_COOKIE_NAME"] = "buildbetter_session"
# Lax stops other sites from sending this cookie with their form posts
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set SESSION_COOKIE_SECURE=true when using HTTPS.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true"
app.before_request(check_csrf)
app.before_request(refresh_logged_in_user)
app.teardown_request(close_database)


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["password_max_length"] = MAX_PASSWORD_LENGTH
app.jinja_env.filters["amount"] = format_amount

limiter.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(planner_bp)
app.register_blueprint(products_bp)
app.register_blueprint(shopping_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(crews_bp)


@app.errorhandler(DatabaseError)
def database_unavailable(error):
    app.logger.error("Database error", exc_info=error)
    return render_template("unavailable.html"), 503


@app.route("/")
def landing_page():
    return redirect(url_for("auth.login"))


@app.route("/home")
def home():
    return render_template("home.html")


@app.route("/reviews")
def reviews():
    return render_template("reviews.html")


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
    # Port 5000 is used by macOS AirPlay Receiver and can return an AirTunes 403.
    app.run(debug=True, port=5001)
