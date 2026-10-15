import os
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import dotenv_values
from flask import current_app, has_app_context


def database_settings():
    testing = os.getenv("DATABASE_ENV") == "test"
    if has_app_context() and current_app.testing:
        testing = True

    if testing:
        test_file = Path(__file__).resolve().parents[1] / ".env.test"
        values = dotenv_values(test_file)
        names = ("TEST_DB_HOST", "TEST_DB_PORT", "TEST_DB_NAME", "TEST_DB_USER", "TEST_DB_PASSWORD")
        if any(not values.get(name) for name in names):
            raise RuntimeError("Complete TEST_DB_* settings are required in .env.test.")
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

# lets other files use this with a with statement
@contextmanager
def database_cursor():
    connection = mysql.connector.connect(
        **database_settings(),
        ssl_disabled=False,
    )
    try:
        # dictionary=True lets us use column names instead of indexes
        with connection.cursor(dictionary=True) as cursor:
            # the code inside the caller's with block runs here
            yield cursor
            connection.commit()
    except Exception:
        # undo the changes if something failed
        connection.rollback()
        raise
    finally:
        # close the connection even if there was an error
        connection.close()
