import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for
from mysql.connector import Error as DatabaseError

# Load .env before routes create their AI clients.
load_dotenv()

from routes.auth import auth_bp, check_logged_in_user
from routes.crews import crews_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import products_bp
from routes.subscription import subscription_bp
from utils.csrf import check_csrf, csrf_token
from utils.rate_limits import limiter
from utils.passwords import MAX_PASSWORD_LENGTH, PASSWORD_DIGITS
from services.products import get_manufacturers

app = Flask(__name__, template_folder="pages")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
# Lax stops other sites from sending this cookie with their form posts
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set SESSION_COOKIE_SECURE=true when using HTTPS.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true"
app.before_request(check_csrf)
app.before_request(check_logged_in_user)


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["password_digits"] = PASSWORD_DIGITS
app.jinja_env.globals["password_max_length"] = MAX_PASSWORD_LENGTH

limiter.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(planner_bp)
app.register_blueprint(products_bp)
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
    return render_template("manufacturers.html", manufacturers=get_manufacturers())


from routes import shopping

app.add_url_rule("/cart", "cart", shopping.cart)
app.add_url_rule("/cart/add", "cart_add", shopping.cart_add, methods=["POST"])
app.add_url_rule("/cart/update", "cart_update", shopping.cart_update, methods=["POST"])
app.add_url_rule("/cart/remove", "cart_remove", shopping.cart_remove, methods=["POST"])
app.add_url_rule("/checkout", "checkout", shopping.checkout, methods=["GET", "POST"])
app.add_url_rule("/order-confirmation", "order_confirmation", shopping.order_confirmation, defaults={"order_id": None})
app.add_url_rule("/order-confirmation/<int:order_id>", "order_confirmation", shopping.order_confirmation)


if __name__ == "__main__":
    app.run(debug=True)
