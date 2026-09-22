from flask import Flask, redirect, render_template, url_for
from routes.auth import auth_bp
from routes.planner import planner_bp
from routes.products import products_bp
from routes.dashboard import dashboard_bp
from Ratelimits import limiter
app = Flask(__name__, template_folder="pages")
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

#popup for our cusatom rate limit on ai queries
@app.errorhandler(429)
def too_many_requests(error):
    return render_template(
        "planner.html",
        ai_response=None,
        metadata=None,
        popup_message=error.description,
    ), 429

if __name__ == "__main__":
    app.run(debug=True)
