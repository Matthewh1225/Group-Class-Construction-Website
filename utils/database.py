import os
from contextlib import contextmanager

import mysql.connector
from flask import g, has_request_context


def database_settings():
    return {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

def close_database(error=None):
    """Flask calls this after each request, even if the request fails."""
    connection = g.pop("database_connection", None)
    if connection is not None:
        connection.close()


@contextmanager
def database_cursor():
    in_request = has_request_context()
    connection = g.get("database_connection") if in_request else None
    if connection is None:
        connection = mysql.connector.connect(
            **database_settings(),
            ssl_disabled=False,
            time_zone="+00:00",
        )
        if in_request:
            g.database_connection = connection
    try:
        with connection.cursor(dictionary=True) as cursor:
            yield cursor
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if not in_request:
            connection.close()
