from flask import Flask, render_template
from routes.auth import auth_bp
from routes.planner import planner_bp
from routes.products import products_bp
from routes.dashboard import dashboard_bp
from Ratelimits  import limiter
app = Flask(__name__, template_folder="pages")
limiter.init_app(app)
app.register_blueprint(auth_bp)
app.register_blueprint(planner_bp)
app.register_blueprint(products_bp)
app.register_blueprint(dashboard_bp)

@app.route("/")
def home():
    return render_template("home.html")

if __name__ == "__main__":
    app.run(debug=True)
