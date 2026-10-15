import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

# load .env before the route imports set up their clients
load_dotenv()

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import products_bp
from utils.rate_limits import limiter

app = Flask(__name__, template_folder="pages")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

limiter.init_app(app)
# blueprints keep each group of routes in its own file
app.register_blueprint(auth_bp)
app.register_blueprint(planner_bp)
app.register_blueprint(products_bp)
app.register_blueprint(dashboard_bp)


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
    return render_template("manufacturers.html")


# Keep the existing endpoint names used by the shopping templates.
from routes import shopping

app.add_url_rule("/cart", "cart", shopping.cart)
app.add_url_rule("/checkout", "checkout", shopping.checkout)
app.add_url_rule("/order-confirmation", "order_confirmation", shopping.order_confirmation)


if __name__ == "__main__":
    app.run(debug=True)
