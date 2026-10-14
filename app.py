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


@app.get("/cart")
def cart():
    # No cart storage exists yet; never treat a pass stub as saved cart data.
    return render_template("cart/cart.html", cart_items=[])


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "POST":
        return {"error": "Checkout and payment processing are not connected yet."}, 501

    return render_template(
        "cart/checkout.html", cart_items=[],
        contact_email=session.get("email", ""),
    )


@app.get("/order-confirmation")
def order_confirmation():
    # URL parameters cannot verify a payment or establish order ownership.
    return render_template("cart/confirmation.html", verified_order=None)


if __name__ == "__main__":
    app.run(debug=True)
