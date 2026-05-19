"""
Email notification helpers for ISKCON Book Store.
Uses Python's built-in smtplib — no extra dependencies required.
Emails are sent in a background thread so they never block the response.
"""

import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import current_app, render_template


def _do_send(app, to_email, subject, html_body):
    """Runs in background thread — opens SMTP connection and sends."""
    with app.app_context():
        username = app.config.get("MAIL_USERNAME", "")
        password = app.config.get("MAIL_PASSWORD", "")
        from_addr = app.config.get("MAIL_FROM", username)
        server   = app.config.get("MAIL_SERVER", "smtp.gmail.com")
        port     = int(app.config.get("MAIL_PORT", 587))

        if not username or not password:
            app.logger.warning("[EMAIL] Credentials not set — skipping send.")
            return

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = from_addr
            msg["To"]      = to_email
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            ctx = ssl.create_default_context()
            with smtplib.SMTP(server, port) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.login(username, password)
                smtp.sendmail(username, to_email, msg.as_string())

            app.logger.info(f"[EMAIL] '{subject}' → {to_email}")
        except Exception as exc:
            app.logger.error(f"[EMAIL] Failed to send to {to_email}: {exc}")


def _send_async(to_email, subject, html_body):
    """Fire-and-forget: renders template synchronously, sends SMTP in background."""
    if not to_email:
        return
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_do_send,
        args=(app, to_email, subject, html_body),
        daemon=True,
    )
    t.start()


# ─── Public helpers ──────────────────────────────────────────────────────────

def send_order_confirmation(order):
    """Email customer when their order is confirmed / payment received."""
    if not order.customer_email:
        return
    subject   = f"Order Confirmed #{order.order_number} — Hare Krishna! 🙏"
    html_body = render_template("emails/order_confirmation.html", order=order)
    _send_async(order.customer_email, subject, html_body)


def send_order_shipped(order):
    """Email customer when order is shipped with tracking details."""
    if not order.customer_email:
        return
    subject   = f"Your Order #{order.order_number} Has Been Shipped! 📦"
    html_body = render_template("emails/order_shipped.html", order=order)
    _send_async(order.customer_email, subject, html_body)


def send_order_delivered(order):
    """Email customer when order is marked delivered."""
    if not order.customer_email:
        return
    subject   = f"Your Order #{order.order_number} Has Been Delivered! ✅"
    html_body = render_template("emails/order_delivered.html", order=order)
    _send_async(order.customer_email, subject, html_body)
