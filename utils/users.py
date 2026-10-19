from planning.jobs import delete_planner_jobs
from utils.database import database_cursor
from utils.passwords import hash_password

MAX_USERNAME_LENGTH = 50
MAX_EMAIL_LENGTH = 254


# A simple check that the text has a name, one "@", and a "." in the domain.
def looks_like_email(email):
    name, at, domain = email.partition("@")
    return bool(name) and at == "@" and "." in domain and "@" not in domain and " " not in email


# Checks the sign-up form, saves a new user with a hashed password, and returns the new user id.
# Raises ValueError with a message the user can read if something is wrong.
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
    # login accepts a username or an email, so a username must never look like an email
    if "@" in username:
        raise ValueError("Usernames cannot contain @.")
    if len(email) > MAX_EMAIL_LENGTH or not looks_like_email(email):
        raise ValueError("Enter a valid email.")
    if password != confirm_password:
        raise ValueError("Passwords do not match.")
    if permission_level not in {"user", "admin"}:
        raise ValueError("Choose user or admin.")
    password_hash = hash_password(password)
    with database_cursor() as cursor:
        # pass values separately so user input stays out of the SQL code
        cursor.execute(
            """INSERT INTO users (username, email, password_hash, permission_level)
               VALUES (%s, %s, %s, %s)""",
            (username, email, password_hash, permission_level),
        )
        user_id = cursor.lastrowid
        # ADD send the welcome notification after the account transaction commits.
    return user_id

# Admin tool: turns an account "active" or "disabled". Returns False if the user does not exist.
def set_user_status(user_id, status):
    if status not in {"active", "disabled"}:
        raise ValueError("Choose active or disabled.")
    with database_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if cursor.fetchone() is None:
            return False
        cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
    return True


def delete_user_completely(user_id): 
    # Everything runs in one database transaction: if any step fails, nothing is deleted and rturns False when there is no user with this id.
    with database_cursor() as cursor:
        # ON DELETE CASCADE removes everything else under the the user 

        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cursor.rowcount == 0:
            return False


        delete_planner_jobs(user_id)
    return True
