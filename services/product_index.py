"""Keeps product search text and vectors in sync with the catalog.

After editing products, run python -m services.product_index. Use --check to only report
stale text, or --rebuild to re-embed everything.
"""
import argparse
from pathlib import Path

from services import product_specs

FACT_COLUMNS = "id AS product_id, name AS product_name, category, subCategory AS subcategory, " \
               "details, description, dimensions, materials, keywords, specs, itemQty, sale_unit, content_quantity, content_unit, " \
               "search_text, search_hash"


def search_fields_for(product):
    """The generated search text and its fingerprint (text_hash) for one product dictionary."""
    segments = product_specs.embedding_segments_for(product)
    return product_specs.search_text_for(product, segments), product_specs.text_hash(product, segments)


def ensure_catalog_filter_index(cursor):
    """Support category/type filters without changing category keys or FULLTEXT indexes."""
    cursor.execute("SHOW INDEX FROM Product WHERE Key_name = 'product_category_active_type'")
    if not cursor.fetchall():
        cursor.execute('CREATE INDEX product_category_active_type ON Product (category, isActive, subCategory)')


def load_facts(cursor):
    cursor.execute("SELECT " + FACT_COLUMNS + " FROM Product ORDER BY id")
    return [product_specs.product_from_row(row) for row in cursor.fetchall()]


def find_out_of_date(cursor):
    """Products whose stored search text or hash no longer matches their facts."""
    out_of_date = []
    for product in load_facts(cursor):
        search_text, search_hash = search_fields_for(product)
        if product["search_hash"] != search_hash or product["search_text"] != search_text:
            out_of_date.append((product, search_text, search_hash))
    return out_of_date


def save_search_fields(cursor, changes):
    for start in range(0, len(changes), 100):
        batch = changes[start:start + 100]
        cases = " ".join(["WHEN %s THEN %s"] * len(batch))
        # Only write rows whose hash (including NULL) is still the one we read.
        where = " OR ".join(["(id = %s AND search_hash <=> %s)"] * len(batch))
        values = []
        for index in (1, 2):
            for product, *fields in batch:
                values.extend((product["product_id"], fields[index - 1]))
        for product, _, _ in batch:
            values.extend((product["product_id"], product["search_hash"]))
        cursor.execute(f"UPDATE Product SET search_text = CASE id {cases} ELSE search_text END, "
                       f"search_hash = CASE id {cases} ELSE search_hash END WHERE {where}", values)


def refresh_search_fields(cursor):
    """Regenerate search text for every product whose facts changed. Returns the updated product IDs."""
    changes = find_out_of_date(cursor)
    save_search_fields(cursor, changes)
    return [product["product_id"] for product, _, _ in changes]


def main():
    from dotenv import load_dotenv
    from services import vector_search
    from utils.database import database_cursor

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Refresh product search text and the vector cache.")
    parser.add_argument("--check", action="store_true", help="Only report products whose search text is out of date.")
    parser.add_argument("--rebuild", action="store_true", help="Re-embed every product, not just changed ones.")
    options = parser.parse_args()

    with database_cursor() as cursor:
        if options.check:
            out_of_date = find_out_of_date(cursor)
            print(f"{len(out_of_date)} products have out-of-date search text.")
            for product, _, _ in out_of_date[:20]:
                print("  ", product["product_id"], product["product_name"])
            return
        ensure_catalog_filter_index(cursor)
        updated = refresh_search_fields(cursor)
    print(f"Refreshed search text for {len(updated)} products.")
    vector_search.build_cache(rebuild_all=options.rebuild)


if __name__ == "__main__":
    main()
