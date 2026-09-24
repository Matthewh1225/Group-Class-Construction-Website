from utils.database import database_cursor
from utils.passwords import hash_password


def create_user(data, permission_level="user"):
    username = data.get("username", "")
    email = data.get("email", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    fields = (username, email, password, confirm_password)

    if not all(isinstance(field, str) for field in fields):
        raise ValueError("Enter valid text fields.")
    username = username.strip()
    email = email.strip()

    if not username or not email or not password:
        raise ValueError("All fields are required.")
    if password != confirm_password:
        raise ValueError("Passwords do not match.")
    if permission_level not in {"user", "admin"}:
        raise ValueError("Choose user or admin permission.")
    password_hash = hash_password(password)
    with database_cursor() as cursor:
        cursor.execute(
            """INSERT INTO users (username, email, password_hash, permission_level)
               VALUES (%s, %s, %s, %s)""",
            (username, email, password_hash, permission_level),
        )
