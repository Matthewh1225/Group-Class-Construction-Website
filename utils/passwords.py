import bcrypt
import sys


# Share Python's exact Unicode digit set with browser validation.
PASSWORD_DIGITS = "".join(chr(code) for code in range(sys.maxunicode + 1) if chr(code).isdigit())


# Raises ValueError if the password breaks a rule (3+ characters, at most 72 bytes, has a number).
def validate_password(password):
    if not isinstance(password, str) or len(password) < 3:
        raise ValueError("Password must be at least 3 characters.")
    # bcrypt counts bytes, so some characters take up more than one
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password is too long.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one number.")


# Scrambles the password with bcrypt so the real password is never stored in the database.
def hash_password(password):
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Used at login: True if the typed password matches the stored hash, False otherwise.
def verify_password_hash(password, stored_pass):
    if not isinstance(password, str) or not isinstance(stored_pass, str):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_pass.encode("utf-8"))
    except ValueError:
        return False
