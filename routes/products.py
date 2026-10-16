from flask import Blueprint, current_app, render_template, request
from mysql.connector import Error

from services.products import search_products

products_bp = Blueprint("products", __name__)

# "slug" is used in the page address (/products?category=lumber) and matches the icon_key column of the categories table (see sql/buildbetter_test_setup.sql).
PRODUCT_CATEGORIES = [
    {"slug": "lumber", "code": "MAT-01", "name": "Lumber & Building Materials",
     "note": "Framing, decking, sheathing",
     "art": "M26 26h76v12H26zM20 40h76v12H20zM14 54h76v12H14zM94 32a3 3 0 1 0 6 0a3 3 0 1 0-6 0M88 46a3 3 0 1 0 6 0a3 3 0 1 0-6 0M82 60a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
     "marks": "M26 16H102M26 12V20M102 12V20M6 72H112"},
    {"slug": "fasteners", "code": "MAT-02", "name": "Hardware & Fasteners",
     "note": "Screws, nails, connectors",
     "art": "M28 16h24v7H28zM35 23v34l5 9 5-9V23M35 30l10 4M35 38l10 4M35 46l10 4M35 54l10 3M72 32l9-7h14l9 7v14l-9 7H81l-9-7zM82 39a6 6 0 1 0 12 0a6 6 0 1 0-12 0",
     "marks": "M40 8V74M88 14V64M6 74H112"},
    {"slug": "concrete", "code": "MAT-03", "name": "Concrete & Masonry",
     "note": "Mixes, block, rebar",
     "art": "M16 20h88v44H16zM29 34a3 3 0 1 0 6 0a3 3 0 1 0-6 0M57 34a3 3 0 1 0 6 0a3 3 0 1 0-6 0M85 34a3 3 0 1 0 6 0a3 3 0 1 0-6 0M29 50a3 3 0 1 0 6 0a3 3 0 1 0-6 0M57 50a3 3 0 1 0 6 0a3 3 0 1 0-6 0M85 50a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
     "marks": "M16 40l20-20M16 60l40-40M32 64l44-44M52 64l44-44M72 64l32-32M92 64l12-12M16 12H104M16 8V16M104 8V16"},
    {"slug": "drywall", "code": "MAT-04", "name": "Drywall & Insulation",
     "note": "Drywall, tape, compound, insulation",
     "art": "M14 14h44v52H14zM62 14h44v52H62zM22 22h2M22 58h2M48 22h2M48 58h2M70 22h2M70 58h2M96 22h2M96 58h2",
     "marks": "M56 10h8v60h-8zM6 74H114"},
    {"slug": "roofing", "code": "MAT-05", "name": "Roofing & Siding",
     "note": "Shingles, underlayment, trim",
     "art": "M12 20H108M12 34H108M12 48H108M12 62H108M24 20v14M44 20v14M64 20v14M84 20v14M104 20v14M34 34v14M54 34v14M74 34v14M94 34v14M24 48v14M44 48v14M64 48v14M84 48v14M104 48v14",
     "marks": "M12 72H108M80 72L108 58M12 12H108M12 8V16M108 8V16"},
    {"slug": "tools", "code": "MAT-06", "name": "Tools & Equipment",
     "note": "Power tools and machinery",
     "art": "M30 16h34l6 6v10H30zM64 16c12 0 20 6 24 16M46 32v38h8V32M78 52h22v18H78zM84 52v-8h10v8",
     "marks": "M50 8V76M6 74H114"},
    {"slug": "electrical", "code": "MAT-07", "name": "Electrical",
     "note": "Wire, boxes, breakers, lighting",
     "art": "M20 14h34v52H20zM31 28v8M43 28v8M34 48a3 3 0 1 0 6 0a3 3 0 1 0-6 0M72 14h30v52H72zM78 22h18v40H78zM78 32h18M78 42h18M78 52h18",
     "marks": "M37 6V74M6 74H114"},
    {"slug": "plumbing", "code": "MAT-08", "name": "Plumbing",
     "note": "Pipe, fittings, valves, fixtures",
     "art": "M10 26H52Q66 26 66 40V70M10 38H50Q54 38 54 42V70M28 20h8v24h-8zM32 20v-8M24 12h16M80 26h30v12H80zM89 38v32h12V38",
     "marks": "M6 74H114M10 18V46"},
    {"slug": "hvac", "code": "MAT-09", "name": "HVAC",
     "note": "Ductwork, vents, heating and cooling",
     "art": "M14 16h46v48H14zM23 40a14 14 0 1 0 28 0a14 14 0 1 0-28 0M37 40l8-10M37 40l-10-4M37 40l2 12M60 28h48v24H60zM72 28v24M84 28v24M96 28v24",
     "marks": "M6 74H114M14 8H60M14 4V12M60 4V12"},
    {"slug": "flooring", "code": "MAT-10", "name": "Flooring & Tile",
     "note": "Plank, tile, underlayment, grout",
     "art": "M14 18h44v44H14zM36 18v44M14 40h44M66 18h42v44H66zM66 29h42M66 40h42M66 51h42M86 18v11M76 29v11M96 40v11M84 51v11",
     "marks": "M6 74H114M14 10H58M14 6V14M58 6V14"},
    {"slug": "paint", "code": "MAT-11", "name": "Paint & Supplies",
     "note": "Paint, primer, brushes, rollers",
     "art": "M16 28h34v38H16zM16 36h34M26 28V20h14v8M66 16h40v14H66zM106 23h6v18H86v8M84 49h4v22h-4z",
     "marks": "M6 74H114"},
    {"slug": "doors-windows", "code": "MAT-12", "name": "Doors & Windows",
     "note": "Doors, windows, frames, trim",
     "art": "M16 10h32v62H16zM22 16h20v24H22zM22 46h20v20H22zM42 42h2M64 18h44v40H64zM86 18v40M64 38h44M60 58h52",
     "marks": "M6 74H114M64 10H108M64 6V14M108 6V14"},
]


def find_category(slug):
    for category in PRODUCT_CATEGORIES:
        if category["slug"] == slug:
            return category
    return None


@products_bp.get("/products")
def products():
    # List active products, filtered by the category tile and the search box.
    selected = find_category(request.args.get("category", ""))
    search = request.args.get("q", "").strip()[:200]
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1

    category_slug = None
    if selected is not None:
        category_slug = selected["slug"]

    # If the catalog cannot be read (for example the production database has no product tables), the page still shows the category tiles with a "temporarily unavailable" notice.
    catalog_error = False
    product_list = []
    has_next = False
    try:
        product_list, has_next = search_products(search=search, category_slug=category_slug, page=page)
    except Error:
        current_app.logger.exception("Product search failed")
        catalog_error = True

    return render_template(
        "products.html", categories=PRODUCT_CATEGORIES, selected=selected,
        products=product_list, search=search, page=page, has_next=has_next,
        catalog_error=catalog_error,
    )
