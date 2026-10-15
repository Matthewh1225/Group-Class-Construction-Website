from flask import Blueprint, render_template

products_bp = Blueprint("products", __name__)


@products_bp.get("/products")
def products():
    # Page shell only. Connect the catalog service when it is implemented.
    return render_template(
        "products.html", products=[], search="", page=1,
        has_next=False, catalog_error=False,
    )
