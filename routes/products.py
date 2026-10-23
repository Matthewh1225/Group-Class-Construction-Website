from flask import Blueprint, abort, current_app, render_template, request
from mysql.connector import Error

from services.products import get_manufacturer, search_products

products_bp = Blueprint("products", __name__)

# url_name matches Product.category and the category URL parameter.
PRODUCT_CATEGORIES = [
    {"url_name": "lumber", "code": "MAT-01", "name": " Lumber & Building Materials"},
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

# Products share a category image; paths are relative to static/.
PLACEHOLDER_IMAGE = "images/placeholder.png"
CATEGORY_IMAGES = {
    "lumber": "images/Lumber & Building Materials.png",
    "fasteners": "images/Hardware & Fasteners.png",
    "concrete": "images/Concrete & Masonry.png",
    "tools": "images/Tools.png",
    "electrical": "images/Electrical.png",
    "drywall": "images/drywall & insulation.png",
    "roofing": PLACEHOLDER_IMAGE,
    "plumbing": "images/Plumbing.png",
    "hvac": "images/HVAC.png",
    "flooring": "images/Flooring & Tile.png",
    "paint": "images/Paint & Supplies.png",
    "doors-windows": "images/Doors & Windows.png",
    "heavy-machinery": "images/Heavy Machinery.png",
}


def find_category(url_name):
    for category in PRODUCT_CATEGORIES:
        if category["url_name"] == url_name:
            return category
    return None


def load_product_page(category_url_name):
    manufacturer_id = request.args.get("manufacturer", type=int)
    if "manufacturer" in request.args and (manufacturer_id is None or manufacturer_id < 1):
        abort(404)
    search = request.args.get("query", "").strip()[:200]
    page = max(1, request.args.get("page", 1, type=int))

    manufacturer = None
    product_list = []
    total_pages = 1
    catalog_error = False
    # Keep category links visible  when the product query fails.
    try:
        if manufacturer_id is not None:
            manufacturer = get_manufacturer(manufacturer_id)
            if manufacturer is None:
                abort(404)
        product_list, total_pages = search_products(search=search, category_url_name=category_url_name,
                                                 page=page, manufacturer_id=manufacturer_id)
        if page > total_pages:
            abort(404)
    except Error:
        current_app.logger.exception("Product search failed")
        catalog_error = True

    for product in product_list:
        product["image"] = CATEGORY_IMAGES.get(product["category"], PLACEHOLDER_IMAGE)
        stock = product["available_quantity"]
        product["can_buy"] = False
        product["availability_status"] = "unavailable"
        product["availability_label"] = "Unavailable"
        if product["unit_price"] is not None:
            if stock is None or stock <= 0:
                product["availability_status"] = "out_of_stock"
                product["availability_label"] = "Out of stock"
            else:
                product["availability_status"] = "available"
                product["availability_label"] = "In stock"
                product["can_buy"] = stock >= 1

    return {
        "products": product_list,
        "has_next": page < total_pages,
        "total_pages": total_pages,
        "catalog_error": catalog_error,
        "manufacturer": manufacturer,
        "manufacturer_id": manufacturer_id,
        "search": search,
        "page": page,
        "placeholder_image": PLACEHOLDER_IMAGE,
    }


@products_bp.get("/products")
def products():
    selected = find_category(request.args.get("category", ""))
    category_url_name = None
    if selected is not None:
        category_url_name = selected["url_name"]

    catalog = load_product_page(category_url_name)

    for product in catalog["products"]:
        category = find_category(product["category"])
        if category is not None:
            product["category_name"] = category["name"]

    return render_template("products.html", categories=PRODUCT_CATEGORIES, selected=selected, **catalog)


@products_bp.get("/heavy-machinery")
def heavy_machinery():
    catalog = load_product_page("heavy-machinery")

    for machine in catalog["products"]:
        machine["category_name"] = "Heavy Machinery"

    return render_template("heavy_machinery.html", **catalog)
