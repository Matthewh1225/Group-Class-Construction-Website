from flask import Blueprint, current_app, render_template, request
from mysql.connector import Error

from services.products import search_products

products_bp = Blueprint("products", __name__)

# url_name matches Product.category and the category URL parameter.
PRODUCT_CATEGORIES = [
    {"url_name": "lumber", "code": "MAT-01", "name": "Lumber & Building Materials"},
    {"url_name": "fasteners", "code": "MAT-02", "name": "Hardware & Fasteners"},
    {"url_name": "concrete", "code": "MAT-03", "name": "Concrete & Masonry"},
    {"url_name": "tools", "code": "MAT-06", "name": "Tools"},
    {"url_name": "electrical", "code": "MAT-07", "name": "Electrical"},
    {"url_name": "drywall", "code": "MAT-04", "name": "Drywall & Insulation"},
    {"url_name": "roofing", "code": "MAT-05", "name": "Roofing & Siding"},
    {"url_name": "plumbing", "code": "MAT-08", "name": "Plumbing"},
    {"url_name": "hvac", "code": "MAT-09", "name": "HVAC"},
    {"url_name": "flooring", "code": "MAT-10", "name": "Flooring & Tile"},
    {"url_name": "paint", "code": "MAT-11", "name": "Paint & Supplies"},
    {"url_name": "doors-windows", "code": "MAT-12", "name": "Doors & Windows"},
]


def find_category(url_name):
    for category in PRODUCT_CATEGORIES:
        if category["url_name"] == url_name:
            return category
    return None


@products_bp.get("/products")
def products():
    selected = find_category(request.args.get("category", ""))
    search = request.args.get("q", "").strip()[:200]
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1

    category_url_name = None
    if selected is not None:
        category_url_name = selected["url_name"]

    # Keep the category links visible if the catalog cannot be read.
    catalog_error = False
    product_list = []
    has_next = False
    try:
        product_list, has_next = search_products(search=search, category_url_name=category_url_name, page=page)
    except Error:
        current_app.logger.exception("Product search failed")
        catalog_error = True

    for product in product_list:
        category = find_category(product["category"])
        if category is not None:
            product["category_name"] = category["name"]

    return render_template(
        "products.html", categories=PRODUCT_CATEGORIES, selected=selected,
        products=product_list, search=search, page=page, has_next=has_next,
        catalog_error=catalog_error,
    )


@products_bp.get("/heavy-machinery")
def heavy_machinery():
    search = request.args.get("q", "").strip()[:200]
    page = max(1, request.args.get("page", 1, type=int))
    catalog_error = False
    machines = []
    has_next = False
    try:
        machines, has_next = search_products(search=search, category_url_name="heavy-machinery", page=page)
    except Error:
        current_app.logger.exception("Heavy machinery search failed")
        catalog_error = True
    for machine in machines:
        machine["category_name"] = "Heavy Machinery"
    return render_template("heavy_machinery.html", products=machines, search=search,
                           page=page, has_next=has_next, catalog_error=catalog_error)
