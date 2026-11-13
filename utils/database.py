import hashlib
import os
from contextlib import contextmanager
from threading import Lock

import mysql.connector
from flask import g, has_request_context
from mysql.connector.pooling import MySQLConnectionPool


_pool = None
_pool_pid = None
_pool_connections = 0
_pool_lock = Lock()


def using_local_database():
    # Use LOCAL_DB_* when DB_TARGET=local; otherwise use DB_*.
    return os.getenv("DB_TARGET", "remote").strip().lower() == "local"


def database_settings():
    if using_local_database():
        return {
            "host": os.getenv("LOCAL_DB_HOST", "127.0.0.1"),
            "port": os.getenv("LOCAL_DB_PORT", "3306"),
            "database": os.getenv("LOCAL_DB_NAME", "Construction_db"),
            "user": os.getenv("LOCAL_DB_USER", "root"),
            "password": os.getenv("LOCAL_DB_PASSWORD", "root"),
        }
    return {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }


def pooled_connection():
    # Get a connection from this process's pool.
    global _pool, _pool_pid, _pool_connections

    with _pool_lock:
        pid = os.getpid()
        if _pool is None or _pool_pid != pid:
            # Open pool connections as needed.
            pool = MySQLConnectionPool(
                pool_name="buildbetter",
                pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
                pool_reset_session=True,
            )
            pool.set_config(
                **database_settings(),
                # Local MySQL skips TLS; remote MySQL uses it.
                ssl_disabled=using_local_database(),
                time_zone="+00:00",
            )
            _pool = pool
            _pool_pid = pid
            _pool_connections = 0

        try:
            # The connector reconnects dropped connections.
            return _pool.get_connection()
        except mysql.connector.errors.PoolError:
            if _pool_connections >= _pool.pool_size:
                raise
            _pool.add_connection()
            _pool_connections += 1
            return _pool.get_connection()


def close_database(error=None):
    # Return the connection to the pool, even after an error.
    connection = g.pop("database_connection", None)
    if connection is not None:
        connection.close()


@contextmanager
def database_cursor(lock_name=None):
    in_request = has_request_context()
    connection = g.get("database_connection") if in_request else None
    if connection is None:
        connection = pooled_connection()
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
            # Release the lock after commit or rollback.
            if locked:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                    cursor.fetchone()
        finally:
            if not in_request:
                connection.close()
