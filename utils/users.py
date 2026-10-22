from planning.jobs import delete_planner_jobs
from utils.database import database_cursor
from utils.passwords import hash_password, validate_password

# match the User table.
MAX_NAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100


def looks_like_email(email):
    name, at, domain = email.partition("@")
    return bool(name) and at == "@" and "." in domain and "@" not in domain and " " not in email

def create_user(data, permission_level="user"):
    first_name = data.get("firstName", "")
    last_name = data.get("lastName", "")
    email = data.get("email", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    fields = (first_name, last_name, email, password, confirm_password)
    if not all(isinstance(field, str) for field in fields):
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
    if permission_level not in {"user", "admin"}:
        raise ValueError("Choose user or admin.")
    password_hash = hash_password(password)
    with database_cursor() as cursor:
        cursor.execute(
            """INSERT INTO `User` (firstName, lastName, email, passkey, permissions, dateCreated)
               VALUES (%s, %s, %s, %s, %s, CURDATE())""",
            (first_name, last_name, email, password_hash, permission_level),
        )
        user_id = cursor.lastrowid
        if permission_level == "admin":
            cursor.execute("INSERT INTO Administrator (userId) VALUES (%s)", (user_id,))
        cursor.execute("INSERT INTO Customer (userId) VALUES (%s)", (user_id,))
    return user_id

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
        cursor.execute("DELETE FROM `User` WHERE id = %s", (user_id,))
        if cursor.rowcount == 0:
            return False
        # If deleting the planner jobs fails, the MySQL delete is rolled back too.
        delete_planner_jobs(user_id)
    return True
