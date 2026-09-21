from flask import Flask, render_template
from routes.auth import auth_bp
app = Flask(__name__, template_folder="pages")


@app.route("/")
def home():
    return render_template("home.html")

if __name__ == "__main__":
    app.run(debug=True)
