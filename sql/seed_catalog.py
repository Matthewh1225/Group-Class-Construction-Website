"""Preview or seed the fictional development catalog: python sql/seed_catalog.py --help."""
import argparse
import csv
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGETS = {
    "lumber": 50, "fasteners": 35, "concrete": 25, "tools": 20,
    "electrical": 45, "drywall": 20, "roofing": 30, "plumbing": 50,
    "hvac": 25, "flooring": 25, "paint": 25, "doors-windows": 25,
}
PRODUCT_COLUMNS = (
    "sku", "name", "category", "subCategory", "details", "dimensions",
    "materials", "unit", "itemQty", "price", "stockQty", "keywords", "isActive",
)


def load_products(path=ROOT / "sql" / "catalog_products.csv"):
    """Check the editable CSV before connecting to the database."""
    with path.open(encoding="utf-8", newline="") as source:
        products = list(csv.DictReader(source))
    schema = (ROOT / "sql" / "erd_schema.sql").read_text(encoding="utf-8")
    enum_text = re.search(r"subCategory ENUM\((.*?)\) NOT NULL", schema, re.S).group(1)
    subcategories = set(re.findall(r"'([^']+)'", enum_text))
    limits = {"sku": 80, "name": 100, "dimensions": 100, "materials": 100,
              "unit": 50, "keywords": 512, "manufacturer": 50}
    for number, product in enumerate(products, 2):
        label = f"CSV line {number}"
        if set(product) != set(PRODUCT_COLUMNS) | {"manufacturer"}:
            raise ValueError(f"{label}: unexpected or missing columns")
        if any(not value or not value.strip() for value in product.values()):
            raise ValueError(f"{label}: all fields must have a value")
        for field, limit in limits.items():
            if len(product[field]) > limit:
                raise ValueError(f"{label}: {field} exceeds {limit} characters")
        if len(product["details"].encode("utf-8")) > 65535:
            raise ValueError(f"{label}: details exceeds TEXT capacity")
        if product["subCategory"] not in subcategories:
            raise ValueError(f"{label}: invalid subcategory")
        if product["category"] not in TARGETS:
            raise ValueError(f"{label}: invalid category")
        if product["dimensions"] not in product["details"] or product["materials"] not in product["details"]:
            raise ValueError(f"{label}: include dimensions and materials in details for the auditor")
        try:
            product["price"] = Decimal(product["price"])
            for field in ("itemQty", "stockQty", "isActive"):
                product[field] = int(product[field])
        except (ValueError, InvalidOperation) as error:
            raise ValueError(f"{label}: invalid price or quantity") from error
        price = product["price"]
        if not price.is_finite() or not Decimal("0") < price <= Decimal("9999999999.99"):
            raise ValueError(f"{label}: price must fit DECIMAL(12,2) and be positive")
        if price != price.quantize(Decimal("0.01")):
            raise ValueError(f"{label}: price must have at most two decimal places")
        if not 0 < product["itemQty"] <= 2147483647 or not 0 < product["stockQty"] <= 2147483647:
            raise ValueError(f"{label}: package quantity and stock must be positive INT values")
        if product["isActive"] != 1:
            raise ValueError(f"{label}: seed products must be active")
    for field in ("sku", "name"):
        counts = Counter(product[field].casefold() for product in products)
        if any(count > 1 for count in counts.values()):
            raise ValueError(f"Duplicate {field} in catalog")
    if Counter(product["category"] for product in products) != Counter(TARGETS):
        raise ValueError("Product counts do not match the 375-product category targets")
    return products


def seed_catalog(cursor, products, apply=False):
    """Preserve existing IDs and unrelated products; the caller owns the transaction."""
    cursor.execute("SELECT id, sku, name, category, unit, isActive FROM Product")
    existing = cursor.fetchall()
    by_sku = {}
    names = {}
    for row in existing:
        if row["sku"]:
            by_sku[row["sku"].casefold()] = row
        names[row["name"].casefold()] = row
    managed_skus = {product["sku"].casefold() for product in products}
    for product in products:
        old = by_sku.get(product["sku"].casefold())
        if old and (old["category"] != product["category"] or old["unit"] != product["unit"]):
            raise ValueError(f"Refusing to change category or selling unit of {product['sku']}")
        same_name = names.get(product["name"].casefold())
        if same_name and (same_name["sku"] or "").casefold() != product["sku"].casefold():
            raise ValueError(f"Existing product with a different SKU has name: {product['name']}")
    counts = Counter(row["category"] for row in existing
                     if row["isActive"] and (row["sku"] or "").casefold() not in managed_skus)
    counts.update(product["category"] for product in products)
    if not 350 <= sum(counts.values()) <= 400:
        raise ValueError(f"Projected active total is {sum(counts.values())}; expected 350-400. No products were deleted.")
    report = {"counts": dict(counts), "current_active": sum(bool(row["isActive"]) for row in existing),
              "reused": sum(product["sku"].casefold() in by_sku for product in products),
              "new": sum(product["sku"].casefold() not in by_sku for product in products)}
    if not apply:
        return report

    cursor.execute("SELECT id, name FROM Manufacturer ORDER BY id")
    manufacturers = {}
    for row in cursor.fetchall():
        manufacturers.setdefault(row["name"].casefold(), row["id"])
    for name in sorted({product["manufacturer"] for product in products}):
        if name.casefold() not in manufacturers:
            cursor.execute("INSERT INTO Manufacturer (name) VALUES (%s)", (name,))
            manufacturers[name.casefold()] = cursor.lastrowid

    columns = ", ".join(PRODUCT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(PRODUCT_COLUMNS))
    updates = ", ".join(f"{column} = VALUES({column})" for column in PRODUCT_COLUMNS if column != "sku")
    product_values = []
    for product in products:
        values = []
        for column in PRODUCT_COLUMNS:
            values.append(product[column])
        product_values.append(tuple(values))
    cursor.executemany(
        f"INSERT INTO Product ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}",
        product_values,
    )
    cursor.execute("SELECT id, sku FROM Product WHERE sku IS NOT NULL")
    product_ids = {row["sku"].casefold(): row["id"] for row in cursor.fetchall()}
    manufacturer_links = []
    for product in products:
        manufacturer_id = manufacturers[product["manufacturer"].casefold()]
        product_id = product_ids[product["sku"].casefold()]
        manufacturer_links.append((manufacturer_id, product_id))
    cursor.executemany(
        "INSERT IGNORE INTO Manufacturer_products (manid, productId) VALUES (%s, %s)",
        manufacturer_links,
    )
    cursor.execute("SELECT category, COUNT(*) AS total FROM Product WHERE isActive = 1 GROUP BY category")
    actual = {row["category"]: row["total"] for row in cursor.fetchall()}
    if actual != dict(counts):
        raise ValueError("Active product counts did not match the preview; rolling back")
    cursor.execute("""
        SELECT COUNT(*) AS total FROM Manufacturer_products mp
        LEFT JOIN Manufacturer m ON m.id = mp.manid
        LEFT JOIN Product p ON p.id = mp.productId
        WHERE m.id IS NULL OR p.id IS NULL
    """)
    if cursor.fetchone()["total"]:
        raise ValueError("Invalid manufacturer relationship; rolling back")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate CSV without a database connection")
    mode.add_argument("--apply", action="store_true", help="write catalog and fictional prices/stock to the configured database")
    args = parser.parse_args()
    products = load_products()
    print(f"CSV valid: {len(products)} distinct active products")
    counts = TARGETS
    if not args.check:
        from dotenv import load_dotenv
        from utils.database import database_cursor

        load_dotenv(ROOT / ".env")
        with database_cursor() as cursor:
            report = seed_catalog(cursor, products, apply=args.apply)
        counts = report["counts"]
        print("Applied." if args.apply else "Dry run: no database changes.")
        print(f"Currently active before seed: {report['current_active']}; existing SKUs reused: {report['reused']}; new: {report['new']}")
    for category, total in counts.items():
        print(f"{category:20} {total:3}")
    print(f"{'Total active':20} {sum(counts.values()):3}")


if __name__ == "__main__":
    main()
