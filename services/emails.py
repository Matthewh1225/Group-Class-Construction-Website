import os
import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi


def send_order_email(to_address, first_name, order_id, items, preorders, crews, totals, address):
    """Email an order receipt through Resend, or SMTP when Resend isn't configured."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    host = os.getenv("SMTP_HOST")
    if not api_key and not host:
        print("Receipt email is not configured; set RESEND_API_KEY and EMAIL_FROM.")
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

    subject = "Your BuildBetter order #" + str(order_id)
    sender = os.getenv("EMAIL_FROM") or os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    text = "\n".join(lines)
    if api_key:
        if not sender:
            raise ValueError("Set EMAIL_FROM to a sender authorized in Resend.")
        request = Request(
            "https://api.resend.com/emails",
            data=json.dumps({"from": sender, "to": [to_address], "subject": subject, "text": text}).encode("utf-8"),
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json",
                     "User-Agent": "BuildBetter/1.0", "Idempotency-Key": f"buildbetter-order-receipt-{order_id}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10, context=ssl.create_default_context(cafile=certifi.where())) as response:
                result = json.load(response)
        except HTTPError as error:
            # Avoid logging request credentials or customer details.
            status = error.code
            error.close()
            raise RuntimeError(f"Resend rejected the receipt (HTTP {status}). Check the Resend dashboard.") from None
        if not result.get("id"):
            raise RuntimeError("Resend did not return a receipt email ID.")
        return result["id"]

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_address
    message.set_content(text)

    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(message)
