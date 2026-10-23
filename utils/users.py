from planning.jobs import delete_planner_jobs
from utils.database import database_cursor
from utils.passwords import check_password, hash_password, validate_password

# match the User table.
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


# A last name is optional in old data, so this never leaves a trailing space.
def full_name(first_name, last_name):
    return (first_name + " " + last_name).strip()


# The signed-in user's name, role and account status, or None if the account no longer exists.
def get_account(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.firstName, u.lastName, u.permissions, c.accountStatus FROM `User` u
            JOIN Customer c ON c.userId = u.id WHERE u.id = %s""",
            (user_id,),
        )
        return cursor.fetchone()


# Returns the user if the email and password are both right, otherwise None.
# It does not look at accountStatus. The caller checks that afterwards, so a disabled
# account is only revealed to someone who knows the password.
def check_login(email, password):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.id, u.firstName, u.lastName, u.passkey, u.permissions, c.accountStatus
               FROM `User` u
               JOIN Customer c ON c.userId = u.id
               WHERE u.email = %s""",
            (email,),
        )
        user = cursor.fetchone()
    if user is None or not check_password(user["passkey"], password):
        return None
    return user


def create_user(data, permission_level="user"):
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

def get_all_users():
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.id, CONCAT_WS(' ', u.firstName, NULLIF(u.lastName, '')) AS display_name,
                      u.email, u.permissions, u.dateCreated, c.accountStatus
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
        cursor.execute("DELETE FROM `User` WHERE id = %s", (user_id,))
        if cursor.rowcount == 0:
            return False
        # If deleting the planner jobs fails, the MySQL delete is rolled back too.
        delete_planner_jobs(user_id)
    return True
