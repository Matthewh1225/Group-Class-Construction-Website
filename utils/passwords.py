from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type, verify_secret

MIN_PASSWORD_LENGTH = 3
MAX_PASSWORD_LENGTH = 50

password_hasher = PasswordHasher(type=Type.ID)


def validate_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    # Match the registration form's 0-9 rule.
    if not any(char in "0123456789" for char in password):
        raise ValueError("Password must contain at least one number.")


def hash_password(password):
    return password_hasher.hash(password)


def check_password(stored_hash, entered_password):
    try:
        return verify_secret(stored_hash.encode("utf-8"), entered_password.encode("utf-8"), Type.ID)
    except (VerificationError, ValueError):
        return False
