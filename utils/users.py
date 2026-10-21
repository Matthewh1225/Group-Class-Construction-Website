from planning.jobs import delete_planner_jobs
from utils.database import database_cursor
from utils.passwords import hash_password, validate_password

# Keep these limits in line with the User table.
MAX_USERNAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100


def looks_like_email(email):
    name, at, domain = email.partition("@")
    return bool(name) and at == "@" and "." in domain and "@" not in domain and " " not in email

def create_user(data, permission_level="user"):
    username = data.get("username", "")
    email = data.get("email", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    fields = (username, email, password, confirm_password)
    if not all(isinstance(field, str) for field in fields):
        raise ValueError("Invalid form data.")

    username = username.strip()
    email = email.strip()

    if not username or not email or not password:
        raise ValueError("Complete all fields.")
    if len(username) > MAX_USERNAME_LENGTH:
        raise ValueError(f"Usernames can be at most {MAX_USERNAME_LENGTH} characters.")
    # Login accepts usernames and emails, so usernames cannot contain @.
    if "@" in username:
        raise ValueError("Usernames cannot contain @.")
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
            "INSERT INTO `User` (username, email, password) VALUES (%s, %s, %s)",
            (username, email, password_hash),
        )
        user_id = cursor.lastrowid
        if permission_level == "admin":
            cursor.execute("INSERT INTO Administrator (user_Id) VALUES (%s)", (user_id,))
        else:
            cursor.execute("INSERT INTO Customer (user_Id) VALUES (%s)", (user_id,))
    return user_id

def set_user_status(user_id, status):
    if status not in {"active", "disabled"}:
        raise ValueError("Choose active or disabled.")
    with database_cursor() as cursor:
        cursor.execute("SELECT Id FROM `User` WHERE Id = %s", (user_id,))
        if cursor.fetchone() is None:
            return False
        cursor.execute("UPDATE `User` SET status = %s WHERE Id = %s", (status, user_id))
    return True


def delete_user_completely(user_id): 
    with database_cursor() as cursor:
        cursor.execute("DELETE FROM `User` WHERE Id = %s", (user_id,))
        if cursor.rowcount == 0:
            return False
        delete_planner_jobs(user_id)
    return True
