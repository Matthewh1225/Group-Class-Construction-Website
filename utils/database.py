import os
from contextlib import contextmanager

import mysql.connector


@contextmanager
def database_cursor():
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
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
