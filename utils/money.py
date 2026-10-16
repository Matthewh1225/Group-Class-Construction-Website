

from decimal import Decimal, ROUND_HALF_UP

def round_money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_cents(amount):
    return int(round_money(amount) * 100)


def from_cents(cents):
    return Decimal(cents) / 100


def format_dollars(amount):
    return "${:,.2f}".format(amount)


def show_quantity(value):
    text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
