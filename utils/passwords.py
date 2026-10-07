import bcrypt


def validate_password(password):
    if not isinstance(password, str) or len(password) < 3:
        raise ValueError("Password must be at least 3 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one number.")
    has_special_character = False
    for char in password:
        if not char.isalnum() and not char.isspace():
            has_special_character = True
            break
    if not has_special_character:
        raise ValueError("Password must contain at least one special character.")


def hash_password(password):
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


<<<<<<< HEAD
def verify_password(password, stored_pass):
=======
def verify_password_hash(password, stored_hash):
>>>>>>> 87186c98e2d72fdd9d92167d2ebf9a525398ddf9
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_pass.encode("utf-8"))
    except ValueError:
        return False
