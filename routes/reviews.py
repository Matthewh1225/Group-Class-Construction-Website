from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error

from services.reviews import (PRODUCT_SEARCH_LIMIT, SORT_ORDERS, create_review, get_review_product, get_reviews,
                              search_review_products)

reviews_bp = Blueprint("reviews", __name__)


@reviews_bp.route("/reviews", methods=["GET", "POST"])
def reviews():
    form_data = {}
    error = None
    status = 200
    if request.method == "POST":
        form_data = request.form.to_dict()
        if "user_id" not in session:
            error = "Log in to publish your review."
            status = 401
        else:
            try:
                review_id = create_review(session["user_id"], request.form)
            except ValueError as problem:
                error = str(problem)
                status = 400
            except Error:
                current_app.logger.exception("Could not save customer review")
                error = "Couldn't save your review. Try again."
                status = 503
            else:
                flash("Review published.", "success")
                return redirect(url_for("reviews.reviews", _anchor=f"review-{review_id}"), code=303)

    kind = request.args.get("type", "all")
    if kind not in {"all", "general", "product"}:
        kind = "all"
    rating = request.args.get("rating", 0, type=int)
    if rating not in range(1, 6):
        rating = 0
    sort = request.args.get("sort", "newest")
    if sort not in SORT_ORDERS:
        sort = "newest"
    search = request.args.get("q", "").strip()[:200]
    page = max(1, request.args.get("page", 1, type=int))
    product_id = request.args.get("product", type=int)
    selected_product = None  # the product whose reviews are listed (?product=ID)
    chosen_product = None    # the product already picked in the review form
    data = {"items": [], "total": 0, "average": 0, "counts": {}, "matching": 0,
            "page": 1, "total_pages": 1, "start": 0, "end": 0}
    load_error = False
    try:
        selected_product = get_review_product(product_id)
        data = get_reviews(kind=kind, rating=rating, search=search, sort=sort, page=page,
                           product_id=product_id)
        if request.method == "POST":
            # The form is shown again after an error: keep the product the user picked.
            posted_id = form_data.get("product_id", "")
            if posted_id.isdigit():
                chosen_product = get_review_product(int(posted_id))
        else:
            chosen_product = selected_product
    except Error:
        current_app.logger.exception("Could not load customer reviews")
        load_error = True
        status = 503
    if request.method != "POST" and selected_product:
        form_data = {"review_type": "product", "product_id": str(selected_product["id"])}

    def page_url(page_number):
        return url_for("reviews.reviews", type=kind, rating=rating or None, q=search or None,
                       sort=sort, product=product_id, page=page_number, _anchor="community-reviews")

    return render_template("reviews.html", review_data=data, chosen_product=chosen_product, form_data=form_data,
                           error=error, load_error=load_error, kind=kind, rating=rating, sort=sort,
                           search=search, product_id=product_id, selected_product=selected_product,
                           page_url=page_url), status


@reviews_bp.get("/reviews/products")
def review_product_search():
    """Products for the review form's search box, as JSON (at most PRODUCT_SEARCH_LIMIT)."""
    search = request.args.get("q", "").strip()[:100]
    try:
        products = search_review_products(search)
    except Error:
        current_app.logger.exception("Could not search products for a review")
        return {"error": "Couldn't search products. Try again."}, 503
    return {"products": products, "limit": PRODUCT_SEARCH_LIMIT}
