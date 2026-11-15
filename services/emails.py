import os
import smtplib
from email.message import EmailMessage


def send_order_email(to_address, first_name, order_id, items, total, address):
    """Email an order receipt. Does nothing if mail settings are missing from .env."""
    host = os.getenv("SMTP_HOST")
    if not host:
        print("SMTP_HOST is not set, so no order email was sent.")
        return

    lines = ["Hi " + first_name + ",", "", "Thanks for your order! Order number: " + str(order_id), ""]
    for item in items:
        line_total = item["price"] * item["itemQty"]
        lines.append(str(item["itemQty"]) + " x " + item["name"] + " - $" + format(line_total, ",.2f"))
    lines.append("")
    lines.append("Total: $" + format(total, ",.2f"))
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
