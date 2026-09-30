from flask import Blueprint, render_template

products_bp = Blueprint("products", __name__)

@products_bp.route("/products")
def products():
    return render_template("products.html")

#need functions to fetch products info and pass it to be renderd in