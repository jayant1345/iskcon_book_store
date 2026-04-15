# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Flask e-commerce store for ISKCON book distribution (India). Python 3.9+, SQLite (dev) / PostgreSQL (prod), Razorpay payments.

## Setup & Run

```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
python seed_data.py         # seed DB with sample books/coupons
python app.py               # dev server at http://127.0.0.1:5000
```

Admin panel: `/admin/login` — credentials via `.env` (defaults: `admin` / `Hare@Krishna108`)

## Architecture

**Single-file backend:** `app.py` (~900 lines) contains all Flask routes, SQLAlchemy models, and business logic.

**Models:** `Category` → `Book` → `OrderItem` → `Order`, `Coupon`

**Cart:** session-based (no auth required for shopping)

**Payment flow:** Razorpay order created server-side → client JS captures payment → `/payment/verify` validates HMAC signature → order saved

**Templates:** Jinja2 in `/templates/` (store-facing + admin sub-folder)

**Environment config (`.env`):**
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `SHIPPING_CHARGES`, `FREE_SHIPPING_THRESHOLD`
- `WHATSAPP_NUMBER`

## Deployment

- Cloud (Render/Railway): `gunicorn app:app` via `Procfile`
- Production config: `gunicorn.conf.py`
- Switch to PostgreSQL by setting `DATABASE_URL` env var
