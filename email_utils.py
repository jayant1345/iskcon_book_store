"""
Email notification helpers for ISKCON Book Store.
Uses Brevo HTTP API — works on Railway/Render where SMTP is blocked.
Sends synchronously so gunicorn workers don't kill the request before
the API call completes (daemon threads get killed too early in production).
"""

import requests as http
from flask import current_app, render_template


def _safe_url(endpoint, **kwargs):
    """Build an external URL, returning '' safely if no request context exists."""
    try:
        from flask import url_for
        return url_for(endpoint, _external=True, **kwargs)
    except Exception:
        return ""


def _send(to_email, subject, html_body):
    """Send via Brevo HTTP API — called synchronously in the request."""
    app       = current_app._get_current_object()
    api_key   = app.config.get("BREVO_API_KEY", "")
    from_email = app.config.get("MAIL_USERNAME", "noreply@iskconbooks.in")

    if not api_key:
        print("[EMAIL] BREVO_API_KEY not set — skipping send.")
        app.logger.warning("[EMAIL] BREVO_API_KEY not set — skipping send.")
        return False

    payload = {
        "sender":      {"name": "ISKCON Book Store", "email": from_email},
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
        resp = http.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload, headers=headers, timeout=15
        )
        if resp.status_code in (200, 201):
            print(f"[EMAIL] OK — '{subject}' -> {to_email}")
            app.logger.info(f"[EMAIL] '{subject}' -> {to_email}")
            return True
        else:
            print(f"[EMAIL] Brevo error {resp.status_code}: {resp.text[:300]}")
            app.logger.error(f"[EMAIL] Brevo error {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as exc:
        print(f"[EMAIL] Failed to send to {to_email}: {exc}")
        app.logger.error(f"[EMAIL] Failed to send to {to_email}: {exc}")
        return False


# ─── Public helpers ──────────────────────────────────────────────────────────

def send_order_placed(order, utr=""):
    """Email customer immediately when a UPI order is submitted (payment pending verification)."""
    if not order.customer_email:
        return
    try:
        track_url = _safe_url("order_track")
        subject   = f"Order Received #{order.order_number} — Payment Verification Pending"
        html_body = render_template("emails/order_placed.html", order=order, utr=utr, track_url=track_url)
        _send(order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_placed error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_placed error: {exc}")


def send_order_confirmation(order):
    """Email customer when their order is confirmed / payment received."""
    if not order.customer_email:
        print(f"[EMAIL] Skipping confirmation for {order.order_number} — no email on record.")
        return
    try:
        track_url = _safe_url("order_track")

        # Ebooks: payment is confirmed at this point (this email fires when
        # admin marks the order paid), so any not-yet-downloaded ebook items
        # get a direct link here — this is the one channel that reaches a
        # guest customer even if their checkout-time browser session is gone.
        ebook_links = {}
        if order.payment_method != "cod" and order.payment_status == "paid":
            for item in order.items:
                if item.book and item.book.is_ebook and item.book.ebook_file and not item.ebook_downloaded_at:
                    ebook_links[item.id] = _safe_url(
                        "ebook_download", order_number=order.order_number, book_id=item.book_id
                    )

        subject   = f"Order Confirmed #{order.order_number} — Hare Krishna!"
        html_body = render_template("emails/order_confirmation.html", order=order, track_url=track_url,
                                     ebook_links=ebook_links)
        _send(order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_confirmation error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_confirmation error: {exc}")


def send_order_shipped(order):
    """Email customer when order is shipped with tracking details."""
    if not order.customer_email:
        print(f"[EMAIL] Skipping shipped for {order.order_number} — no email on record.")
        return
    try:
        track_url = _safe_url("order_track")
        subject   = f"Your Order #{order.order_number} Has Been Shipped!"
        html_body = render_template("emails/order_shipped.html", order=order, track_url=track_url)
        _send(order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_shipped error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_shipped error: {exc}")


def send_order_delivered(order):
    """Email customer when order is marked delivered."""
    if not order.customer_email:
        print(f"[EMAIL] Skipping delivered for {order.order_number} — no email on record.")
        return
    try:
        store_url = _safe_url("books")
        subject   = f"Your Order #{order.order_number} Has Been Delivered!"
        html_body = render_template("emails/order_delivered.html", order=order, store_url=store_url)
        _send(order.customer_email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_order_delivered error: {exc}")
        current_app.logger.error(f"[EMAIL] send_order_delivered error: {exc}")


def send_password_reset(customer):
    """Email customer a password reset link."""
    try:
        reset_url = _safe_url("customer_reset_password", token=customer.reset_token)
        subject   = "Reset your ISKCON Book Store password"
        html_body = render_template("emails/password_reset.html",
                                    customer=customer, reset_url=reset_url)
        _send(customer.email, subject, html_body)
    except Exception as exc:
        print(f"[EMAIL] send_password_reset error: {exc}")
        current_app.logger.error(f"[EMAIL] send_password_reset error: {exc}")
