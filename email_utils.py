"""
Email notification helpers for ISKCON Book Store.
Uses Brevo (formerly Sendinblue) HTTP API — works on Railway/Render
where direct SMTP port 587/465 is blocked at the network level.
No new dependencies required — uses the `requests` library already installed.
"""

import threading
import requests as http

from flask import current_app, render_template

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _do_send(app, to_email, subject, html_body):
    """Runs in background thread — calls Brevo HTTP API."""
    with app.app_context():
        api_key   = app.config.get("BREVO_API_KEY", "")
        from_name = "ISKCON Book Store"
        from_email = app.config.get("MAIL_USERNAME", "iskconbooks.in@gmail.com")

        if not api_key:
            print("[EMAIL] BREVO_API_KEY not set — skipping send.")
            app.logger.warning("[EMAIL] BREVO_API_KEY not set — skipping send.")
            return

        payload = {
            "sender":      {"name": from_name, "email": from_email},
            "to":          [{"email": to_email}],
            "subject":     subject,
            "htmlContent": html_body,
        }
        headers = {
            "accept":       "application/json",
            "content-type": "application/json",
            "api-key":      api_key,
        }

        try:
            resp = http.post(_BREVO_URL, json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                print(f"[EMAIL] OK — '{subject}' → {to_email}")
                app.logger.info(f"[EMAIL] '{subject}' → {to_email}")
            else:
                msg = resp.text[:300]
                print(f"[EMAIL] Brevo error {resp.status_code}: {msg}")
                app.logger.error(f"[EMAIL] Brevo error {resp.status_code}: {msg}")
        except Exception as exc:
            print(f"[EMAIL] FAILED to send to {to_email}: {exc}")
            app.logger.error(f"[EMAIL] Failed to send to {to_email}: {exc}")


def _send_async(app, to_email, subject, html_body):
    """Fire-and-forget: sends via Brevo in a background daemon thread."""
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
        print(f"[EMAIL] Skipping confirmation for {order.order_number} — no email on record.")
        return
    try:
        app       = current_app._get_current_object()
        subject   = f"Order Confirmed #{order.order_number} — Hare Krishna!"
        html_body = render_template("emails/order_confirmation.html", order=order)
        print(f"[EMAIL] Queuing confirmation → {order.customer_email}")
        _send_async(app, order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_confirmation error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_confirmation error: {exc}")


def send_order_shipped(order):
    """Email customer when order is shipped with tracking details."""
    if not order.customer_email:
        print(f"[EMAIL] Skipping shipped for {order.order_number} — no email on record.")
        return
    try:
        app       = current_app._get_current_object()
        subject   = f"Your Order #{order.order_number} Has Been Shipped!"
        html_body = render_template("emails/order_shipped.html", order=order)
        print(f"[EMAIL] Queuing shipped → {order.customer_email}")
        _send_async(app, order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_shipped error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_shipped error: {exc}")


def send_order_delivered(order):
    """Email customer when order is marked delivered."""
    if not order.customer_email:
        print(f"[EMAIL] Skipping delivered for {order.order_number} — no email on record.")
        return
    try:
        app       = current_app._get_current_object()
        subject   = f"Your Order #{order.order_number} Has Been Delivered!"
        html_body = render_template("emails/order_delivered.html", order=order)
        print(f"[EMAIL] Queuing delivered → {order.customer_email}")
        _send_async(app, order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_delivered error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_delivered error: {exc}")
