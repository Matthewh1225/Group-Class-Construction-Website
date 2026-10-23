"""Create the three empty planner tables using the existing DB_* settings."""

from pathlib import Path

from dotenv import load_dotenv

from utils.database import database_cursor


def main():
    load_dotenv()
    schema = Path(__file__).with_name("planner_schema.sql").read_text(encoding="utf-8")
    schema = "\n".join(line for line in schema.splitlines() if not line.lstrip().startswith("--"))
    with database_cursor() as cursor:
        for statement in schema.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Planner tables are ready. No data was imported.")


if __name__ == "__main__":
    main()
