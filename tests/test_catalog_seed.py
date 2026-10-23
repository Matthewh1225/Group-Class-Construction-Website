"""Offline seed checks, plus an opt-in test using session-local MySQL tables."""
import csv
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from sql.seed_catalog import ROOT, load_products, seed_catalog


class CatalogSeedTests(unittest.TestCase):
    def test_complete_catalog_has_auditor_specifications(self):
        products = load_products()
        self.assertEqual(len(products), 375)
        for product in products:
            self.assertIn(product["dimensions"], product["details"])
            self.assertIn(product["materials"], product["details"])
            specification = product["details"].replace(product["dimensions"], "").replace(product["materials"], "")
            self.assertGreater(len(specification), 40, product["sku"])

    def test_rejects_bad_data_before_database_access(self):
        with (ROOT / "sql/catalog_products.csv").open(encoding="utf-8", newline="") as source:
            original = list(csv.DictReader(source))
        changes = (("sku", original[1]["sku"]), ("stockQty", "-1"),
                   ("price", "NaN"), ("price", "3.999"),
                   ("subCategory", "Not a subcategory"), ("details", "Generic item"),
                   ("name", "x" * 101), ("isActive", "0"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.csv"
            for field, value in changes:
                with self.subTest(field=field, value=value):
                    rows = [dict(row) for row in original]
                    rows[0][field] = value
                    with path.open("w", encoding="utf-8", newline="") as target:
                        writer = csv.DictWriter(target, fieldnames=original[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)
                    with self.assertRaises(ValueError):
                        load_products(path)


@unittest.skipUnless(os.getenv("RUN_CATALOG_DB_TESTS") == "1", "Opt-in temporary-table MySQL test")
class CatalogDatabaseTests(unittest.TestCase):
    def test_repeat_seed_preserves_ids_and_planner_retrieves_every_product(self):
        import mysql.connector
        from dotenv import load_dotenv
        from utils.database import database_settings
        from services.products import get_planner_catalog

        load_dotenv(ROOT / ".env")
        connection = mysql.connector.connect(**database_settings(), ssl_disabled=False, time_zone="+00:00")
        products = load_products()
        tables = ("Product", "Manufacturer", "Manufacturer_products")
        before = {}
        try:
            with connection.cursor(dictionary=True) as cursor:
                # Copy each real table before creating a temporary table with its name.
                # Every write below targets session-local temporary tables only.
                for table in tables:
                    cursor.execute(f"SELECT * FROM `{table}`")
                    before[table] = cursor.fetchall()
                    cursor.execute(f"CREATE TEMPORARY TABLE `catalog_test_{table}` LIKE `{table}`")
                    cursor.execute(f"INSERT INTO `catalog_test_{table}` SELECT * FROM `{table}`")
                    cursor.execute(f"CREATE TEMPORARY TABLE `{table}` LIKE `catalog_test_{table}`")
                    cursor.execute(f"INSERT INTO `{table}` SELECT * FROM `catalog_test_{table}`")
                preview = seed_catalog(cursor, products)
                first = seed_catalog(cursor, products, apply=True)
                cursor.execute("SELECT id, sku FROM Product WHERE sku IS NOT NULL")
                first_ids = {row["sku"]: row["id"] for row in cursor.fetchall()}
                second = seed_catalog(cursor, products, apply=True)
                cursor.execute("SELECT id, sku FROM Product WHERE sku IS NOT NULL")
                second_ids = {row["sku"]: row["id"] for row in cursor.fetchall()}
                self.assertEqual(preview["counts"], first["counts"])
                self.assertEqual(first_ids, second_ids)
                self.assertEqual(second["new"], 0)
                for row in before["Product"]:
                    if row["sku"]:
                        self.assertEqual(second_ids[row["sku"]], row["id"])
                managed = {product["sku"] for product in products}
                for row in before["Product"]:
                    if row["sku"] not in managed:
                        cursor.execute("SELECT * FROM Product WHERE id = %s", (row["id"],))
                        self.assertEqual(cursor.fetchone(), row)

                @contextmanager
                def temporary_cursor():
                    yield cursor

                with patch("services.products.database_cursor", temporary_cursor):
                    catalog = get_planner_catalog()
                self.assertEqual(len(catalog), sum(first["counts"].values()))
                returned_ids = {row["product_id"] for row in catalog}
                self.assertTrue({second_ids[sku] for sku in managed} <= returned_ids)
                self.assertTrue(all(row["specification"] for row in catalog))
                # Check both endpoints and one canonical manufacturer link per seed row.
                cursor.execute("""
                    SELECT p.sku, m.name FROM Manufacturer_products mp
                    JOIN Product p ON p.id = mp.productId
                    JOIN Manufacturer m ON m.id = mp.manid
                """)
                links = {(row["sku"], row["name"]) for row in cursor.fetchall()}
                self.assertTrue({(row["sku"], row["manufacturer"]) for row in products} <= links)
                cursor.execute("SELECT COUNT(*) AS total FROM Product")
                print(f"Temporary MySQL validation: {len(catalog)} active, {cursor.fetchone()['total']} total; both seeds passed")
        finally:
            connection.rollback()
            connection.close()  # MySQL drops all the temporary tables here.
        # A fresh connection must still see exactly the original real catalog.
        connection = mysql.connector.connect(**database_settings(), ssl_disabled=False, time_zone="+00:00")
        try:
            with connection.cursor(dictionary=True) as cursor:
                for table in tables:
                    cursor.execute(f"SELECT * FROM `{table}`")
                    after = cursor.fetchall()
                    self.assertCountEqual(after, before[table])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
