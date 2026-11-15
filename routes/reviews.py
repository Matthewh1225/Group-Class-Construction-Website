from flask import current_app, flash, redirect, render_template, request, session, url_for
from mysql.connector import Error

from services.reviews import SORT_ORDERS, create_review, get_review_products, get_reviews


def reviews():
    form_data = {}
    error = None
    status = 200
    if request.method == "POST":
        form_data = request.form.to_dict()
        if "user_id" not in session:
            error = "Please log in before publishing your review. Your draft is still below."
            status = 401
        else:
            try:
                review_id = create_review(session["user_id"], request.form)
            except ValueError as problem:
                error = str(problem)
                status = 400
            except Error:
                current_app.logger.exception("Could not save customer review")
                error = "We couldn't save your review. Your draft is still below. Please try again."
                status = 503
            else:
                flash("Thanks for sharing! Your review has been published.", "success")
                return redirect(url_for("reviews", _anchor=f"review-{review_id}"), code=303)

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
    products = []
    data = {"items": [], "total": 0, "average": 0, "counts": {}, "matching": 0,
            "page": 1, "total_pages": 1, "start": 0, "end": 0}
    load_error = False
    try:
        products = get_review_products()
        data = get_reviews(kind=kind, rating=rating, search=search, sort=sort, page=page,
                           product_id=product_id)
    except Error:
        current_app.logger.exception("Could not load customer reviews")
        load_error = True
        status = 503
    selected_product = next((p for p in products if p["id"] == product_id), None)
    if request.method != "POST" and selected_product:
        form_data = {"review_type": "product", "product_id": str(selected_product["id"])}

    def page_url(page_number):
        return url_for("reviews", type=kind, rating=rating or None, q=search or None,
                       sort=sort, product=product_id, page=page_number, _anchor="community-reviews")

    return render_template("reviews.html", review_data=data, products=products, form_data=form_data,
                           error=error, load_error=load_error, kind=kind, rating=rating, sort=sort,
                           search=search, product_id=product_id, selected_product=selected_product,
                           page_url=page_url), status
