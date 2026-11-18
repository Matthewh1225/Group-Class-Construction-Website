from flask import Blueprint, abort, current_app, render_template, request
from mysql.connector import Error

from services.products import CATALOG_SORTS, DEFAULT_PAGE_SIZE, PAGE_SIZES, get_manufacturer, get_subcategories, search_products

products_bp = Blueprint("products", __name__)

# url_name matches the database category and URL filter.
PRODUCT_CATEGORIES = [
    {"url_name": "lumber", "name": "Lumber & Wood", "code": "MAT-01"},
    {"url_name": "fasteners", "name": "Hardware & Fasteners", "code": "MAT-02"},
    {"url_name": "concrete", "name": "Concrete & Masonry", "code": "MAT-03"},
    {"url_name": "tools", "name": "Tools", "code": "MAT-06"},
    {"url_name": "electrical", "name": "Electrical", "code": "MAT-07"},
    {"url_name": "drywall", "name": "Drywall & Insulation", "code": "MAT-04"},
    {"url_name": "roofing", "name": "Roofing & Siding", "code": "MAT-05"},
    {"url_name": "plumbing", "name": "Plumbing", "code": "MAT-08"},
    {"url_name": "hvac", "name": "HVAC", "code": "MAT-09"},
    {"url_name": "flooring", "name": "Flooring & Tile", "code": "MAT-10"},
    {"url_name": "paint", "name": "Paint & Finishes", "code": "MAT-11"},
    {"url_name": "doors-windows", "name": "Doors & Windows", "code": "MAT-12"},
    {"url_name": "structural-metals", "name": "Structural Metals", "code": "MAT-13"},
    {"url_name": "facility-equipment", "name": "Facility Equipment", "code": "MAT-14"},
    {"url_name": "fire-safety", "name": "Fire Safety", "code": "MAT-15"},
    {"url_name": "vertical-transportation", "name": "Vertical Transportation", "code": "MAT-16"},
    {"url_name": "sitework", "name": "Sitework & Drainage", "code": "MAT-17"},
    {"url_name": "automotive", "name": "Automotive", "code": "MAT-18"},
]

# Products share a category image; paths are relative to static/.
PLACEHOLDER_IMAGE = "images/placeholder.png"
CATEGORY_IMAGES = {
    "lumber": "images/Lumber & Building Materials.webp",
    "fasteners": "images/Hardware & Fasteners.webp",
    "concrete": "images/Concrete & Masonry.webp",
    "tools": "images/Tools.webp",
    "electrical": "images/Electrical.webp",
    "drywall": "images/drywall & insulation.webp",
    "roofing": "images/roofing.webp",
    "plumbing": "images/Plumbing.webp",
    "hvac": "images/HVAC.webp",
    "flooring": "images/Flooring & Tile.webp",
    "paint": "images/Paint & Supplies.webp",
    "doors-windows": "images/Doors & Windows.webp",
    "heavy-machinery": "images/Heavy Machinery.webp",
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
    sort = request.args.get("sort")
    if sort not in CATALOG_SORTS:
        sort = None
    first_page = 1 if (category_url_name or search or manufacturer_id or sort) else 0
    page = max(first_page, request.args.get("page", first_page, type=int))
    # Only the dropdown choices are allowed; anything else uses the default.
    requested_size = request.args.get("per_page", type=int)
    per_page = requested_size if requested_size in PAGE_SIZES else DEFAULT_PAGE_SIZE

    manufacturer = None
    product_list = []
    total_pages = 1
    catalog_error = False
    subcategory = request.args.get('subcategory', '').strip()[:60] or None
    subcategories = []
    # Keep category links visible if loading products fails.
    try:
        subcategories = get_subcategories(category_url_name)
        if subcategory and subcategory not in subcategories:
            abort(404)
        if manufacturer_id is not None:
            manufacturer = get_manufacturer(manufacturer_id)
            if manufacturer is None:
                abort(404)
        product_list, total_pages = search_products(search=search, category_url_name=category_url_name,
                                                 page=page, manufacturer_id=manufacturer_id, sort=sort, per_page=per_page, subcategory=subcategory)
        if page > total_pages:
            abort(404)
    except Error:
        current_app.logger.exception("Product search failed")
        catalog_error = True

    for product in product_list:
        product["image"] = CATEGORY_IMAGES.get(product["category"], PLACEHOLDER_IMAGE)
        if product["category"] == "heavy-machinery":
            product["category_name"] = "Heavy Machinery"
        stock = product["available_quantity"]
        product["can_buy"] = stock >= 1
        if product["can_buy"]:
            product["availability_status"] = "available"
            product["availability_label"] = "In stock"
        else:
            product["availability_status"] = "out_of_stock"
            product["availability_label"] = "Out of stock"

    return {
        "products": product_list,
        "subcategory": subcategory,
        "subcategories": subcategories,
        "has_next": page < total_pages,
        "total_pages": total_pages,
        "catalog_error": catalog_error,
        "manufacturer": manufacturer,
        "manufacturer_id": manufacturer_id,
        "search": search,
        "sort": sort,
        "sort_options": CATALOG_SORTS,
        "page": page,
        "first_page": first_page,
        "per_page": per_page,
        "page_sizes": PAGE_SIZES,
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
    return render_template("heavy_machinery.html", **catalog)
