import os
from contextlib import contextmanager

import mysql.connector

# lets other files use this with a with statement
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
