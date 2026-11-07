import secrets

from utils.database import database_cursor
from utils.passwords import check_password, hash_password, validate_password

# Match the User table's field limits.
MAX_NAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100


def looks_like_email(email):
    name, at, domain = email.partition("@")
    if name == "" or at == "":
        return False
    if "." not in domain or "@" in domain:
        return False
    if " " in email:
        return False
    return True


def full_name(first_name, last_name):
    return (first_name + " " + last_name).strip()


def get_account(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.firstName, u.lastName, u.permissions AS role, c.accountStatus FROM `User` u
            JOIN Customer c ON c.userId = u.id WHERE u.id = %s""",
            (user_id,),
        )
        return cursor.fetchone()


# Check the password before the route reveals whether the account is disabled.
def check_login(email, password):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.id, u.firstName, u.lastName, u.passkey AS password_hash, u.permissions AS role, c.accountStatus
               FROM `User` u
               JOIN Customer c ON c.userId = u.id
               WHERE u.email = %s""",
            (email,),
        )
        user = cursor.fetchone()
    if user is None or not check_password(user["password_hash"], password):
        return None
    return user


def create_user(data, role="user"):
    first_name = data.get("firstName", "")
    last_name = data.get("lastName", "")
    email = data.get("email", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    fields = (first_name, last_name, email, password, confirm_password)
    for field in fields:
        if not isinstance(field, str):
            raise ValueError("Invalid form data.")

    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip()

    if not first_name or not last_name or not email or not password:
        raise ValueError("Complete all fields.")
    if len(first_name) > MAX_NAME_LENGTH or len(last_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Names can be at most {MAX_NAME_LENGTH} characters each.")
    if len(email) > MAX_EMAIL_LENGTH or not looks_like_email(email):
        raise ValueError("Enter a valid email.")
    if password != confirm_password:
        raise ValueError("Passwords do not match.")
    validate_password(password)
    if role not in {"user", "admin"}:
        raise ValueError("Choose user or admin.")
    password_hash = hash_password(password)
    with database_cursor() as cursor:
        cursor.execute(
            """INSERT INTO `User` (firstName, lastName, email, passkey, permissions, dateCreated)
               VALUES (%s, %s, %s, %s, %s, CURDATE())""",
            (first_name, last_name, email, password_hash, role),
        )
        user_id = cursor.lastrowid
        if role == "admin":
            cursor.execute("INSERT INTO Administrator (userId) VALUES (%s)", (user_id,))
        cursor.execute("INSERT INTO Customer (userId) VALUES (%s)", (user_id,))
    return user_id

def find_or_create_google_user(email, first_name, last_name):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.id, u.firstName, u.lastName, u.permissions AS role, c.accountStatus
               FROM `User` u
               JOIN Customer c ON c.userId = u.id
               WHERE u.email = %s""",
            (email,),
        )
        user = cursor.fetchone()
        if user is not None:
            return user
        password_hash = hash_password(secrets.token_urlsafe(32))
        cursor.execute(
            """INSERT INTO `User` (firstName, lastName, email, passkey, permissions, dateCreated)
               VALUES (%s, %s, %s, %s, 'user', CURDATE())""",
            (first_name[:MAX_NAME_LENGTH], last_name[:MAX_NAME_LENGTH], email, password_hash),
        )
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO Customer (userId) VALUES (%s)", (user_id,))
    return {
        "id": user_id,
        "firstName": first_name[:MAX_NAME_LENGTH],
        "lastName": last_name[:MAX_NAME_LENGTH],
        "role": "user",
        "accountStatus": "active",
    }


def get_all_users():
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.id, CONCAT_WS(' ', u.firstName, NULLIF(u.lastName, '')) AS display_name,
                      u.email, u.permissions AS role, u.dateCreated, c.accountStatus
               FROM `User` u
               JOIN Customer c ON c.userId = u.id
               ORDER BY u.id"""
        )
        return cursor.fetchall()


def set_user_status(user_id, status):
    if status not in {"active", "disabled"}:
        raise ValueError("Choose active or disabled.")
    with database_cursor() as cursor:
        cursor.execute("SELECT id FROM `User` WHERE id = %s", (user_id,))
        if cursor.fetchone() is None:
            return False
        cursor.execute("UPDATE Customer SET accountStatus = %s WHERE userId = %s", (status, user_id))
    return True


def delete_user_completely(user_id): 
    with database_cursor() as cursor:
        # Foreign keys remove this user's related records in the same transaction.
        cursor.execute("DELETE FROM `User` WHERE id = %s", (user_id,))
        return cursor.rowcount == 1
