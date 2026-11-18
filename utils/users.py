import secrets
import time
from threading import Lock

from utils.database import database_cursor
from utils.passwords import MAX_PASSWORD_LENGTH, check_password, hash_password, validate_password

# Match the User table's field limits.
MAX_NAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100

# Cache account details and their expiry time by user ID.
ACCOUNT_CACHE_SECONDS = 30
account_cache = {}
account_cache_lock = Lock()


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


def clear_account_cache(user_id):
    with account_cache_lock:
        account_cache.pop(user_id, None)


def get_account(user_id, use_cache=True):
    # Lock while reading and updating cached accounts.
    with account_cache_lock:
        now = time.monotonic()
        for cached_id in list(account_cache):
            if account_cache[cached_id]["expires_at"] <= now:
                del account_cache[cached_id]

        if use_cache and user_id in account_cache:
            return account_cache[user_id]["user"].copy()

        user = read_account(user_id)
        if user is None:
            account_cache.pop(user_id, None)
            return None

        account_cache[user_id] = {
            "user": user.copy(),
            "expires_at": time.monotonic() + ACCOUNT_CACHE_SECONDS,
        }
        return user


def read_account(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            """SELECT u.firstName, u.lastName, u.permissions AS role, c.accountStatus FROM `User` u
            JOIN Customer c ON c.userId = u.id WHERE u.id = %s""",
            (user_id,),
        )
        return cursor.fetchone()


# Check the password before showing disabled-account errors.
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
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    # Reject non-text fields before validation calls string methods.
    fields = (data.get("firstName", ""), data.get("lastName", ""), data.get("email", ""), password, confirm_password)
    for field in fields:
        if not isinstance(field, str):
            raise ValueError("Invalid form data.")
    if not password:
        raise ValueError("Complete all fields.")

    profile = check_profile_form(data, missing_message="Complete all fields.")
    first_name = profile["firstName"]
    last_name = profile["lastName"]
    email = profile["email"]

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


def get_profile(user_id):
    with database_cursor() as cursor:
        cursor.execute(
            "SELECT firstName, lastName, email, dateCreated FROM `User` WHERE id = %s",
            (user_id,),
        )
        return cursor.fetchone()


def check_profile_form(form, missing_message="Enter your first name, last name, and email."):
    """Return cleaned profile fields, or raise ValueError with a form error."""
    first_name = form.get("firstName", "")
    last_name = form.get("lastName", "")
    email = form.get("email", "")
    for field in (first_name, last_name, email):
        if not isinstance(field, str):
            raise ValueError("Invalid form data.")

    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip()

    if not first_name or not last_name or not email:
        raise ValueError(missing_message)
    if len(first_name) > MAX_NAME_LENGTH or len(last_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Names can be at most {MAX_NAME_LENGTH} characters each.")
    if len(email) > MAX_EMAIL_LENGTH or not looks_like_email(email):
        raise ValueError("Enter a valid email.")
    return {"firstName": first_name, "lastName": last_name, "email": email}


def update_profile(user_id, profile):
    """Save this user's cleaned profile; a duplicate email raises IntegrityError."""
    with database_cursor() as cursor:
        cursor.execute(
            "UPDATE `User` SET firstName = %s, lastName = %s, email = %s WHERE id = %s",
            (profile["firstName"], profile["lastName"], profile["email"], user_id),
        )
    # The navigation shows the cached name, so drop the old copy.
    clear_account_cache(user_id)


def change_user_password(user_id, current_password, new_password, confirm_password):
    """Replace this user's password after checking the current one, or raise ValueError."""
    for field in (current_password, new_password, confirm_password):
        if not isinstance(field, str):
            raise ValueError("Invalid form data.")
    if not current_password:
        raise ValueError("Enter your current password.")
    if new_password != confirm_password:
        raise ValueError("The new passwords do not match.")
    validate_password(new_password)
    # A password longer than the limit can't be correct, so skip the slow hash check.
    if len(current_password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Your current password is incorrect.")

    with database_cursor() as cursor:
        # FOR UPDATE stops two password changes for this account from overlapping.
        cursor.execute("SELECT passkey FROM `User` WHERE id = %s FOR UPDATE", (user_id,))
        user = cursor.fetchone()
        if user is None or not check_password(user["passkey"], current_password):
            raise ValueError("Your current password is incorrect.")
        if new_password == current_password:
            raise ValueError("Choose a different password.")
        cursor.execute("UPDATE `User` SET passkey = %s WHERE id = %s", (hash_password(new_password), user_id))


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
    clear_account_cache(user_id)
    return True


def delete_user_completely(user_id):
    with database_cursor() as cursor:
        # Foreign keys delete related records in this transaction.
        cursor.execute("DELETE FROM `User` WHERE id = %s", (user_id,))
        deleted = cursor.rowcount == 1
    clear_account_cache(user_id)
    return deleted
