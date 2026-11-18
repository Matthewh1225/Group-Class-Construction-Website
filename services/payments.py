from flask import abort
from utils.database import database_cursor

# Store only the last four digits; no full number or CVV.
CARD_TYPES = ("Card", "Visa", "Mastercard", "American Express", "Discover")


def validate_card(form, existing_card=None):
    """Read card details; a blank number keeps the saved card when editing."""
    name = (form.get("cardholder") or "").strip()
    number = (form.get("card_number") or "").replace(" ", "").replace("-", "")
    expiration = form.get("expiration") or ""
    card_type = form.get("card_type") or (existing_card or {}).get("card_type", "Card")
    if card_type not in CARD_TYPES:
        card_type = "Card"
    if not name or len(name) > 100:
        raise ValueError("Enter a name of up to 100 characters.")

    if number == "" and existing_card is not None:
        last4 = existing_card["card_number"][-4:]
    else:
        if not number.isascii() or not number.isdigit():
            raise ValueError("Enter a card number using digits.")
        last4 = number[-4:]

    return dict(cardholder=name, card_number=last4, expiration=expiration,
                card_type=card_type, is_default=form.get("is_default") == "1")


def list_cards(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT * FROM saved_payment_methods WHERE userId=%s ORDER BY is_default DESC,id", (user_id,))
        return cursor.fetchall()


def get_card(user_id, card_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT * FROM saved_payment_methods WHERE id=%s AND userId=%s", (card_id, user_id))
        card = cursor.fetchone()
    if card is None:
        abort(404)
    return card


def save_card(user_id, card, card_id=None, cursor=None):
    """Save a card and return its ID, reusing the given transaction if supplied."""
    if cursor is not None:
        return save_card_with_cursor(cursor, user_id, card, card_id)
    with database_cursor() as new_cursor:
        return save_card_with_cursor(new_cursor, user_id, card, card_id)


def save_card_with_cursor(cursor, user_id, card, card_id):
    # Lock the account so two requests cannot choose different default cards.
    cursor.execute("SELECT id FROM User WHERE id=%s FOR UPDATE", (user_id,))
    cursor.fetchone()
    if card_id is not None:
        cursor.execute("SELECT id FROM saved_payment_methods WHERE id=%s AND userId=%s", (card_id, user_id))
        if cursor.fetchone() is None:
            abort(404)
    cursor.execute("SELECT id FROM saved_payment_methods WHERE userId=%s AND is_default=1", (user_id,))
    existing_default = cursor.fetchone()
    make_default = card["is_default"] or existing_default is None
    if make_default:
        cursor.execute("UPDATE saved_payment_methods SET is_default=0 WHERE userId=%s", (user_id,))
    values = (card["cardholder"], card["card_number"], card["expiration"], card["card_type"], make_default)
    if card_id is None:
        cursor.execute("INSERT INTO saved_payment_methods (cardholder,card_number,expiration,card_type,is_default,userId) VALUES (%s,%s,%s,%s,%s,%s)", values + (user_id,))
        return cursor.lastrowid
    cursor.execute("UPDATE saved_payment_methods SET cardholder=%s,card_number=%s,expiration=%s,card_type=%s,is_default=%s WHERE id=%s AND userId=%s", values + (card_id,user_id))
    return card_id


def delete_card(user_id, card_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT id FROM User WHERE id=%s FOR UPDATE", (user_id,))
        cursor.fetchone()
        cursor.execute("DELETE FROM saved_payment_methods WHERE id=%s AND userId=%s", (card_id,user_id))
        if cursor.rowcount == 0:
            abort(404)
        cursor.execute("SELECT id FROM saved_payment_methods WHERE userId=%s ORDER BY is_default DESC,id LIMIT 1", (user_id,))
        remaining = cursor.fetchone()
        if remaining:
            cursor.execute("UPDATE saved_payment_methods SET is_default=1 WHERE id=%s AND userId=%s", (remaining["id"],user_id))


def checkout_payment(user_id, form):
    selected = form.get("payment_method", "new")
    if selected != "new":
        try:
            card_id = int(selected)
        except ValueError:
            raise ValueError("Choose a saved payment or a new card.")
        card = get_card(user_id, card_id)
        card["is_default"] = False
        return card, False
    return validate_card(form), form.get("save_card") == "1"
