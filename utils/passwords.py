import sys

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Share Python's accepted digits with the browser.
PASSWORD_DIGITS = "".join(chr(code) for code in range(sys.maxunicode + 1) if chr(code).isdigit())

MIN_PASSWORD_LENGTH = 3
MAX_PASSWORD_LENGTH = 128

password_hasher = PasswordHasher()


def validate_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one number.")


def hash_password(password):
    return password_hasher.hash(password)


def check_password(stored_hash, entered_password):
    try:
        return password_hasher.verify(stored_hash, entered_password)
    except (VerificationError, InvalidHashError):
        return False


def needs_new_hash(stored_hash):
    return password_hasher.check_needs_rehash(stored_hash)
