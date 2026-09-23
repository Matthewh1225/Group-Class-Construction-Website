import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for

load_dotenv()

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.planner import planner_bp
from routes.products import products_bp
from utils.ratelimits import limiter

app = Flask(__name__, template_folder="pages")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

limiter.init_app(app)
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


if __name__ == "__main__":
    app.run(debug=True)
