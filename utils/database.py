import hashlib
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
def database_cursor(lock_name=None):
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
    locked = False
    if lock_name:
        lock_name = hashlib.sha256(f"{connection.database}:{lock_name}".encode()).hexdigest()
    try:
        with connection.cursor(dictionary=True) as cursor:
            if lock_name:
                cursor.execute("SELECT GET_LOCK(%s, 10) AS acquired", (lock_name,))
                locked = cursor.fetchone()["acquired"] == 1
                if not locked:
                    raise mysql.connector.Error("The planner queue is busy. Try again shortly.")
            yield cursor
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            # Named locks must stay held until after commit or rollback.
            if locked:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                    cursor.fetchone()
        finally:
            if not in_request:
                connection.close()
