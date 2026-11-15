import math

from utils.database import database_cursor

PAGE_SIZE = 8
SORT_ORDERS = {
    "newest": "r.createdAt DESC, r.id DESC",
    "highest": "r.rating DESC, r.createdAt DESC, r.id DESC",
    "lowest": "r.rating ASC, r.createdAt DESC, r.id DESC",
    "oldest": "r.createdAt ASC, r.id ASC",
}


def get_review_products():
    with database_cursor() as cursor:
        cursor.execute("SELECT id, name, sku FROM Product WHERE isActive = 1 ORDER BY name, id")
        return cursor.fetchall()


def validate_review(data):
    review_type = data.get("review_type", "")
    if review_type not in {"general", "product"}:
        raise ValueError("Choose a general or product review.")
    rating = data.get("rating", "")
    if rating not in {"1", "2", "3", "4", "5"}:
        raise ValueError("Choose a star rating from 1 to 5.")
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    if not 1 <= len(title) <= 100:
        raise ValueError("Add a review title of up to 100 characters.")
    if not 10 <= len(body) <= 2000:
        raise ValueError("Write a review between 10 and 2,000 characters.")
    product_id = None
    if review_type == "product":
        try:
            product_id = int(data.get("product_id", ""))
        except (TypeError, ValueError):
            raise ValueError("Choose the product you want to review.") from None
        if product_id < 1:
            raise ValueError("Choose the product you want to review.")
    return {"review_type": review_type, "rating": int(rating), "title": title,
            "body": body, "product_id": product_id}


def create_review(user_id, data):
    review = validate_review(data)
    with database_cursor() as cursor:
        product_name = None
        if review["product_id"] is not None:
            cursor.execute("SELECT name FROM Product WHERE id = %s AND isActive = 1",
                           (review["product_id"],))
            product = cursor.fetchone()
            if product is None:
                raise ValueError("That product is no longer available. Please choose another.")
            product_name = product["name"]
        cursor.execute(
            """INSERT INTO Customer_review (userId, reviewType, productId, productName, rating, title, body)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, review["review_type"], review["product_id"], product_name,
             review["rating"], review["title"], review["body"]),
        )
        return cursor.lastrowid


def get_reviews(*, kind="all", rating=0, search="", sort="newest", page=1, product_id=None):
    # Summary follows the review type/product; text and rating filters narrow the list.
    scope = []
    scope_values = []
    if kind in {"general", "product"}:
        scope.append("r.reviewType = %s")
        scope_values.append(kind)
    if product_id is not None:
        scope.append("r.productId = %s")
        scope_values.append(product_id)
    scope_where = " WHERE " + " AND ".join(scope) if scope else ""
    filters = list(scope)
    values = list(scope_values)
    if rating in range(1, 6):
        filters.append("r.rating = %s")
        values.append(rating)
    if search:
        # LOCATE treats user-entered % and _ as literal text.
        filters.append("(LOCATE(%s, r.title) > 0 OR LOCATE(%s, r.body) > 0 OR LOCATE(%s, r.productName) > 0)")
        values.extend([search] * 3)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    with database_cursor() as cursor:
        cursor.execute("SELECT r.rating, COUNT(*) AS total FROM Customer_review r"
                       + scope_where + " GROUP BY r.rating", scope_values)
        counts = {row["rating"]: row["total"] for row in cursor.fetchall()}
        total = sum(counts.values())
        average = sum(stars * count for stars, count in counts.items()) / total if total else 0
        cursor.execute("SELECT COUNT(*) AS total FROM Customer_review r" + where, values)
        matching = cursor.fetchone()["total"]
        total_pages = max(1, math.ceil(matching / PAGE_SIZE))
        page = min(max(1, page), total_pages)
        order = SORT_ORDERS.get(sort, SORT_ORDERS["newest"])
        cursor.execute(
            """SELECT r.id, r.userId, r.reviewType, r.productName, r.rating, r.title, r.body, r.createdAt,
                      CONCAT_WS(' ', u.firstName, IF(u.lastName = '', NULL, CONCAT(LEFT(u.lastName, 1), '.'))) AS author
               FROM Customer_review r JOIN `User` u ON u.id = r.userId"""
            + where + " ORDER BY " + order + " LIMIT %s OFFSET %s",
            values + [PAGE_SIZE, (page - 1) * PAGE_SIZE],
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "average": average, "counts": counts,
            "matching": matching, "page": page, "total_pages": total_pages,
            "start": (page - 1) * PAGE_SIZE + 1 if matching else 0,
            "end": min(page * PAGE_SIZE, matching)}
