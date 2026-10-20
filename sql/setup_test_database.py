"""Rebuilds the LOCAL test database from scratch:
  1. deletes every table in it (all test data is lost),
  2. creates the ERD tables (sql/erd_schema.sql),
  3. loads the test rows (sql/erd_test_data.sql).

Run from the project folder:
    python sql/setup_test_database.py --confirm construction_db_test

It uses the settings in .env.test and stops without changing anything if they do not point
at construction_db_test. Never point .env.test at the production database.
"""

import os
import sys
from pathlib import Path

PROJECT_FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_FOLDER))
# utils.database reads .env.test when DATABASE_ENV is "test"
os.environ["DATABASE_ENV"] = "test"

from utils.database import database_cursor

TEST_DATABASE = "construction_db_test"


# Splits a .sql file into separate statements. A statement ends with ";" at the end of a line.
# Lines starting with "--" are comments and are skipped.
def read_statements(file_name):
    statements = []
    current_lines = []
    text = (PROJECT_FOLDER / "sql" / file_name).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("--"):
            continue
        current_lines.append(line)
        if line.rstrip().endswith(";"):
            statements.append("\n".join(current_lines))
            current_lines = []
    return statements


def main():
    if sys.argv[1:] != ["--confirm", TEST_DATABASE]:
        sys.exit(f"This deletes all data in the test database. To go ahead, run:\n"
                 f"    python sql/setup_test_database.py --confirm {TEST_DATABASE}")

    with database_cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS name")
        name = cursor.fetchone()["name"]
        # MySQL on Windows reports the name in lowercase, so compare without case
        if (name or "").lower() != TEST_DATABASE:
            sys.exit(f"Stopped: .env.test points at {name!r}, not {TEST_DATABASE}. Nothing was changed.")

        cursor.execute("SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE()")
        tables = [row["name"] for row in cursor.fetchall()]
        # Foreign key checks are turned off so the tables can be dropped in any order.
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in tables:
            cursor.execute(f"DROP TABLE `{table}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        print(f"Dropped {len(tables)} tables from {name}.")

        for file_name in ["erd_schema.sql", "erd_test_data.sql"]:
            statements = read_statements(file_name)
            for statement in statements:
                cursor.execute(statement)
            print(f"Ran {len(statements)} statements from sql/{file_name}.")


if __name__ == "__main__":
    main()
