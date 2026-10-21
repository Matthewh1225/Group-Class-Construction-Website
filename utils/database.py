import os
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import dotenv_values
from flask import current_app, has_app_context


# Test mode reads .env.test by default; other runs use .env.
def database_settings():
    testing = os.getenv("DATABASE_ENV") == "test"
    if has_app_context() and current_app.testing:
        testing = True

    if testing:
        test_file = Path(os.getenv("TEST_DB_ENV_FILE", ".env.test"))
        if not test_file.is_absolute():
            test_file = Path(__file__).resolve().parents[1] / test_file
        values = dotenv_values(test_file)
        names = ("TEST_DB_HOST", "TEST_DB_PORT", "TEST_DB_NAME", "TEST_DB_USER", "TEST_DB_PASSWORD")
        if any(not values.get(name) for name in names):
            raise RuntimeError(f"Complete TEST_DB_* settings are required in {test_file}.")
        return {
            "host": values["TEST_DB_HOST"],
            "port": values["TEST_DB_PORT"],
            "database": values["TEST_DB_NAME"],
            "user": values["TEST_DB_USER"],
            "password": values["TEST_DB_PASSWORD"],
        }

    return {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

# Commit on success; roll back on error.
@contextmanager
def database_cursor():
    connection = mysql.connector.connect(
        **database_settings(),
        ssl_disabled=False,
    )
    try:
        with connection.cursor(dictionary=True) as cursor:
            yield cursor
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
