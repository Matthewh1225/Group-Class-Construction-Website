import os
import smtplib
from email.message import EmailMessage


def send_order_email(to_address, first_name, order_id, items, preorders, crews, totals, address):
    """Email an order receipt. Does nothing if mail settings are missing from .env."""
    host = os.getenv("SMTP_HOST")
    if not host:
        print("SMTP_HOST is not set, so no order email was sent.")
        return

    lines = ["Hi " + first_name + ",", "", "Thanks for your order! Order number: " + str(order_id), ""]
    for item in items:
        line_total = item["price"] * item["itemQty"]
        lines.append(str(item["itemQty"]) + " x " + item["name"] + " - $" + format(line_total, ",.2f"))
    for preorder in preorders:
        line_total = preorder["unitPrice"] * preorder["quantity"]
        lines.append(format(preorder["quantity"].normalize(), "f") + " " + preorder["unit"] + " x "
                     + preorder["name"] + " - $" + format(line_total, ",.2f") + " (pre-order, estimated price)")
    for crew in crews:
        lines.append("Crew: " + crew["label"] + " (" + str(crew["workers"]) + " workers, " + crew["days"]
                     + ") - $" + format(crew["price_cents"] / 100, ",.2f"))
    lines.append("")
    # totals is in cents, so divide by 100 to show dollars
    lines.append("Subtotal: $" + format(totals["subtotal_cents"] / 100, ",.2f"))
    lines.append("Shipping: $" + format(totals["shipping_cents"] / 100, ",.2f"))
    lines.append("Estimated tax (8.5%): $" + format(totals["tax_cents"] / 100, ",.2f"))
    lines.append("Total: $" + format(totals["total_cents"] / 100, ",.2f"))
    lines.append("Shipping to: " + address)

    message = EmailMessage()
    message["Subject"] = "Your BuildBetter order #" + str(order_id)
    message["From"] = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    message["To"] = to_address
    message.set_content("\n".join(lines))

    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(message)
