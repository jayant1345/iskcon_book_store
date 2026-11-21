"""
ISKCON Book Store - Complete Flask Application
=============================================
A production-ready e-commerce platform for ISKCON books.
"""

import os
import uuid
import secrets
import hmac
import hashlib
import json
import csv
import io
import base64
import zipfile
from datetime import datetime, timedelta
from functools import wraps

# Load .env file for local development (no-op on Railway/Render where vars are injected)
from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, session, redirect,
    url_for, flash, jsonify, abort, send_from_directory, send_file, Response
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from email_utils import send_order_placed, send_order_confirmation, send_order_shipped, send_order_delivered

# ─────────────────────────────────────────────
# App & Configuration
# ─────────────────────────────────────────────

app = Flask(__name__)

_IST = timedelta(hours=5, minutes=30)

@app.template_filter('ist')
def to_ist(dt, fmt='%d %b %Y, %I:%M %p'):
    if dt is None:
        return ''
    return (dt + _IST).strftime(fmt)


_EMAIL_RE = __import__("re").compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def valid_indian_phone(phone):
    """Return the bare 10-digit mobile number if valid, else None.

    Accepts a bare 10-digit number, or one prefixed with a leading 0
    or country code 91, as long as the 10-digit core starts with 6-9
    (the valid range for Indian mobile numbers).
    """
    import re as _re
    digits = _re.sub(r'\D', '', str(phone or ''))
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    if _re.fullmatch(r'[6-9]\d{9}', digits):
        return digits
    return None


def valid_email(email):
    """Return True if email is blank (optional field) or looks like a real address."""
    if not email:
        return True
    return bool(_EMAIL_RE.match(email))


def safe_download_filename(name):
    """
    ASCII-only filename for Content-Disposition. Werkzeug's `filename=` kwarg
    does not RFC-5987-encode non-Latin1 characters (e.g. book titles with an
    em dash or Devanagari script) — the raw bytes reach gunicorn's stricter
    header validator, which then rejects the whole response outright.
    """
    name = (name.replace('—', '-').replace('–', '-')
                .replace('’', "'").replace('‘', "'")
                .replace('“', '"').replace('”', '"'))
    name = name.encode('ascii', 'ignore').decode('ascii').strip()
    return name or "ebook"


@app.template_filter('wa_phone')
def wa_phone_filter(phone):
    """Return E.164 digits for wa.me — adds 91 country code for bare 10-digit Indian numbers."""
    if not phone:
        return ''
    import re as _re
    digits = _re.sub(r'\D', '', str(phone))
    if len(digits) == 10:
        return '91' + digits
    if len(digits) == 11 and digits.startswith('0'):
        return '91' + digits[1:]
    return digits

def notify_admin_whatsapp(message):
    """Fire-and-forget WhatsApp notification to admin via Green API. Never blocks the request."""
    import threading, requests as _req, re as _re
    instance_id = app.config.get("GREENAPI_INSTANCE_ID", "")
    token       = app.config.get("GREENAPI_TOKEN", "")
    api_url     = app.config.get("GREENAPI_API_URL", "https://7107.api.greenapi.com")
    phone       = app.config.get("ADMIN_NOTIFY_WHATSAPP", "")
    if not instance_id or not token or not phone:
        return
    # Normalise to E.164 digits: add 91 if bare 10-digit Indian number
    digits = _re.sub(r'\D', '', str(phone))
    if len(digits) == 10:
        digits = '91' + digits
    def _send():
        try:
            url = f"{api_url}/waInstance{instance_id}/sendMessage/{token}"
            _req.post(url, json={
                "chatId": f"{digits}@c.us",
                "message": message
            }, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "iskcon-books-super-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'iskcon_books.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Without pool_pre_ping, the first request after the DB (or a proxy in front
    # of it) silently closes an idle connection gets an uncaught error -> 500,
    # and only the retry (which gets a fresh connection) succeeds.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "images", "books")
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024         # 500 MB (ebooks can be large)
    MAX_IMAGE_SIZE     = 16 * 1024 * 1024          # 16 MB cap for book cover images
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    # Nested inside UPLOAD_FOLDER so ebooks live on the same Railway persistent
    # volume as book cover images (Railway allows only one volume per service).
    EBOOK_FOLDER = os.path.join(UPLOAD_FOLDER, "ebooks")
    PREVIEW_FOLDER = os.path.join(BASE_DIR, "static", "previews")
    REVIEW_VIDEO_FOLDER = os.path.join(BASE_DIR, "static", "videos", "book_reviews")
    ALLOWED_EBOOK_EXTENSIONS = {"pdf", "epub"}
    RAZORPAY_KEY_ID     = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_your_key_id")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "your_razorpay_secret")
    PAYU_MERCHANT_KEY   = os.environ.get("PAYU_MERCHANT_KEY", "")
    PAYU_MERCHANT_SALT  = os.environ.get("PAYU_MERCHANT_SALT", "")
    PAYU_ENV            = os.environ.get("PAYU_ENV", "test")   # "test" or "prod"
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "Hare@Krishna108"))
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "+919999999999")
    SOCIAL_FACEBOOK_URL  = os.environ.get("SOCIAL_FACEBOOK_URL", "")
    SOCIAL_INSTAGRAM_URL = os.environ.get("SOCIAL_INSTAGRAM_URL", "")
    SOCIAL_YOUTUBE_URL   = os.environ.get("SOCIAL_YOUTUBE_URL", "")
    UPI_ID   = os.environ.get("UPI_ID", "")
    UPI_NAME = os.environ.get("UPI_NAME", "ISKCON Book Store")
    STORE_NAME = "ISKCON Book Store"
    SHIPPING_CHARGE = float(os.environ.get("SHIPPING_CHARGE", "50"))
    FREE_SHIPPING_ABOVE = float(os.environ.get("FREE_SHIPPING_ABOVE", "500"))
    DELHIVERY_API_TOKEN       = os.environ.get("DELHIVERY_API_TOKEN", "")
    DELHIVERY_DEFAULT_WEIGHT  = float(os.environ.get("DELHIVERY_DEFAULT_WEIGHT", "0.1"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "noreply@iskconbooks.in")
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    GREENAPI_INSTANCE_ID = os.environ.get("GREENAPI_INSTANCE_ID", "")
    GREENAPI_TOKEN       = os.environ.get("GREENAPI_TOKEN", "")
    GREENAPI_API_URL     = os.environ.get("GREENAPI_API_URL", "https://7107.api.greenapi.com")
    ADMIN_NOTIFY_WHATSAPP = os.environ.get("ADMIN_NOTIFY_WHATSAPP", "919157938887")
    CRON_SECRET           = os.environ.get("CRON_SECRET", "")


app.config.from_object(Config)

# Fix Heroku/Render postgres:// → postgresql://
db_url = app.config["SQLALCHEMY_DATABASE_URI"]
print(f"[DB] Using: {db_url[:40]}...")  # debug — shows first 40 chars only
if db_url.startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url.replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

try:
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["EBOOK_FOLDER"], exist_ok=True)
    os.makedirs(app.config["PREVIEW_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REVIEW_VIDEO_FOLDER"], exist_ok=True)
except Exception as e:
    print(f"[WARNING] makedirs failed: {e}")


# ─────────────────────────────────────────────
# Database Models
# ─────────────────────────────────────────────

class Category(db.Model):
    __tablename__ = "categories"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    slug        = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    icon        = db.Column(db.String(10), default="📚")
    sort_order  = db.Column(db.Integer, default=0)
    books       = db.relationship("Book", backref="category", lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"


class Book(db.Model):
    __tablename__ = "books"
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(250), nullable=False)
    author         = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text)
    short_desc     = db.Column(db.String(300))
    price          = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float)
    image          = db.Column(db.String(200), default="default_book.jpg")
    category_id    = db.Column(db.Integer, db.ForeignKey("categories.id"))
    isbn           = db.Column(db.String(30))
    language       = db.Column(db.String(50), default="English")
    pages          = db.Column(db.Integer)
    weight_kg      = db.Column(db.Float, default=0.1)   # shipping weight
    publisher      = db.Column(db.String(200), default="The Bhaktivedanta Book Trust")
    stock          = db.Column(db.Integer, default=100)
    featured       = db.Column(db.Boolean, default=False)
    active         = db.Column(db.Boolean, default=True)
    deleted        = db.Column(db.Boolean, default=False)   # True = moved to Trash
    is_ebook       = db.Column(db.Boolean, default=False)
    ebook_file     = db.Column(db.String(200), nullable=True)
    preview_file   = db.Column(db.String(200), nullable=True)
    review_text      = db.Column(db.Text, nullable=True)
    review_video     = db.Column(db.String(200), nullable=True)
    review_video_url  = db.Column(db.String(500), nullable=True)
    review_video_url2 = db.Column(db.String(500), nullable=True)
    review_video_url3 = db.Column(db.String(500), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    order_items    = db.relationship("OrderItem", backref="book", lazy=True)
    gallery_images = db.relationship("BookImage", backref="book", lazy=True,
                                      order_by="BookImage.sort_order",
                                      cascade="all, delete-orphan")

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            return int((1 - self.price / self.original_price) * 100)
        return 0

    @property
    def in_stock(self):
        return self.stock > 0

    def __repr__(self):
        return f"<Book {self.title}>"


class BookImage(db.Model):
    """Extra photos for a book (front/back cover, inside pages, etc.) shown
    as a thumbnail gallery on the book detail page, in addition to the
    book's single main `image`."""
    __tablename__ = "book_images"
    id         = db.Column(db.Integer, primary_key=True)
    book_id    = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    filename   = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class Order(db.Model):
    __tablename__ = "orders"
    id                 = db.Column(db.Integer, primary_key=True)
    order_number       = db.Column(db.String(20), unique=True, nullable=False)
    customer_name      = db.Column(db.String(200), nullable=False)
    customer_email     = db.Column(db.String(200))
    customer_phone     = db.Column(db.String(20), nullable=False)
    address            = db.Column(db.Text, nullable=False)
    city               = db.Column(db.String(100))
    state              = db.Column(db.String(100))
    pincode            = db.Column(db.String(10))
    age                = db.Column(db.Integer, nullable=True)
    profession         = db.Column(db.String(100), nullable=True)
    subtotal           = db.Column(db.Float, nullable=False)
    shipping_charge    = db.Column(db.Float, default=0)
    discount_amount    = db.Column(db.Float, default=0)
    total_amount       = db.Column(db.Float, nullable=False)
    payment_method     = db.Column(db.String(50), default="cod")
    payment_status     = db.Column(db.String(50), default="pending")   # pending/paid/failed
    order_status       = db.Column(db.String(50), default="placed")    # placed/confirmed/shipped/delivered/cancelled
    razorpay_order_id  = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    coupon_code        = db.Column(db.String(50))
    notes              = db.Column(db.Text)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    courier_name       = db.Column(db.String(100))
    tracking_number    = db.Column(db.String(100))
    expected_delivery  = db.Column(db.Date)
    upi_transaction_id = db.Column(db.String(100))
    status_note        = db.Column(db.Text)
    is_deleted         = db.Column(db.Boolean, default=False)
    stock_deducted     = db.Column(db.Boolean, default=False)
    is_donation               = db.Column(db.Boolean, default=False)
    donation_type             = db.Column(db.String(20), nullable=True)   # "iskcon" | "person"
    donation_recipient        = db.Column(db.String(200), nullable=True)
    donation_recipient_address= db.Column(db.Text, nullable=True)
    donor_message             = db.Column(db.Text, nullable=True)
    customer_id        = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    items              = db.relationship("OrderItem", backref="order", lazy=True)

    @property
    def display_items(self):
        """Order lines meant to actually be shown to a human — real books
        plus one row per combo purchased. Excludes the zero-priced combo
        "component" rows that exist only for inventory deduction; use
        item.combo.combo_items to show a combo row's book breakdown."""
        return [i for i in self.items if not i.is_combo_component]

    @property
    def product_type(self):
        """Individual Book / Combo / Mixed — for the admin Order Report."""
        has_combo = any(i.combo_id for i in self.display_items)
        has_book  = any(not i.combo_id for i in self.display_items)
        if has_combo and has_book:
            return "Mixed"
        return "Combo" if has_combo else "Individual Book"

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    book_id    = db.Column(db.Integer, db.ForeignKey("books.id"))
    book_title = db.Column(db.String(250))
    quantity   = db.Column(db.Integer, nullable=False)
    price      = db.Column(db.Float, nullable=False)
    ebook_downloaded_at = db.Column(db.DateTime, nullable=True)
    # Combo support: a "header" row (combo_id set, is_combo_component False,
    # book_id None) represents the combo itself for display/pricing — its
    # price is the combo's selling price. Separate "component" rows (same
    # combo_id, is_combo_component True, real book_id, price 0) exist purely
    # so normal per-book inventory deduction (deduct_order_stock) works
    # without special-casing combos.
    combo_id           = db.Column(db.Integer, db.ForeignKey("combos.id"), nullable=True)
    is_combo_component = db.Column(db.Boolean, default=False, nullable=False)
    combo              = db.relationship("Combo", foreign_keys=[combo_id])

    @property
    def subtotal(self):
        return self.price * self.quantity


def deduct_order_stock(order):
    """Decrement physical-book stock once, at ship time. eBooks are never stock-tracked."""
    if order.stock_deducted:
        return
    for item in order.items:
        book = item.book if hasattr(item, "book") else Book.query.get(item.book_id)
        if book and not book.is_ebook:
            book.stock = max(0, book.stock - item.quantity)
    order.stock_deducted = True


def restore_order_stock(order):
    """Undo deduct_order_stock — used when a shipment is cancelled/reverted."""
    if not order.stock_deducted:
        return
    for item in order.items:
        book = item.book if hasattr(item, "book") else Book.query.get(item.book_id)
        if book and not book.is_ebook:
            book.stock = book.stock + item.quantity
    order.stock_deducted = False


class Combo(db.Model):
    """An admin-defined bundle of books sold at one combined price.
    Created/edited/priced/activated entirely from the admin panel —
    no code change needed to add or change a combo."""
    __tablename__ = "combos"
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(200), nullable=False)
    language       = db.Column(db.String(50), default="English")   # English/Hindi/Gujarati — display/filter only
    description    = db.Column(db.Text, nullable=True)
    image          = db.Column(db.String(200), nullable=True)      # static/images/combos/<image>
    selling_price  = db.Column(db.Float, nullable=False, default=0)
    active         = db.Column(db.Boolean, default=True, nullable=False)
    featured       = db.Column(db.Boolean, default=False)          # shown first on the home page
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    combo_items = db.relationship("ComboItem", backref="combo", lazy=True,
                                   cascade="all, delete-orphan")

    @property
    def individual_total(self):
        """Sum of each contained book's normal price × quantity — what the
        customer would pay buying the books separately."""
        return sum((ci.book.price or 0) * ci.quantity for ci in self.combo_items if ci.book)

    @property
    def savings(self):
        return max(0, self.individual_total - self.selling_price)

    @property
    def in_stock(self):
        """A combo can only be sold while every physical book in it has stock."""
        return all(ci.book and (ci.book.is_ebook or ci.book.stock >= ci.quantity)
                   for ci in self.combo_items)

    def __repr__(self):
        return f"<Combo {self.name}>"


class ComboItem(db.Model):
    __tablename__ = "combo_items"
    id       = db.Column(db.Integer, primary_key=True)
    combo_id = db.Column(db.Integer, db.ForeignKey("combos.id"), nullable=False)
    book_id  = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    book = db.relationship("Book")


class Coupon(db.Model):
    __tablename__ = "coupons"
    id             = db.Column(db.Integer, primary_key=True)
    code           = db.Column(db.String(50), unique=True, nullable=False)
    description    = db.Column(db.String(200))
    discount_type  = db.Column(db.String(20), default="percent")   # percent / fixed
    discount_value = db.Column(db.Float, nullable=False)
    min_order      = db.Column(db.Float, default=0)
    max_discount   = db.Column(db.Float)                            # cap for percent coupons
    max_uses       = db.Column(db.Integer, default=100)
    used_count     = db.Column(db.Integer, default=0)
    active         = db.Column(db.Boolean, default=True)
    expires_at     = db.Column(db.DateTime)
    auto_apply     = db.Column(db.Boolean, default=False)

    def is_valid(self, cart_total):
        if not self.active:
            return False, "Coupon is inactive."
        if self.used_count >= self.max_uses:
            return False, "Coupon usage limit reached."
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False, "Coupon has expired."
        if cart_total < self.min_order:
            return False, f"Minimum order ₹{self.min_order:.0f} required."
        return True, "Valid"

    def calculate_discount(self, cart_total):
        if self.discount_type == "percent":
            disc = cart_total * self.discount_value / 100
            if self.max_discount:
                disc = min(disc, self.max_discount)

            return round(disc, 2)
        return min(self.discount_value, cart_total)


class WhatsAppInquiry(db.Model):
    __tablename__ = "whatsapp_inquiries"
    id             = db.Column(db.Integer, primary_key=True)
    book_id        = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=True)
    book_title     = db.Column(db.String(250))
    customer_name  = db.Column(db.String(200))
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(200), nullable=True)
    age            = db.Column(db.Integer, nullable=True)
    profession     = db.Column(db.String(100), nullable=True)
    address        = db.Column(db.Text, nullable=True)
    city           = db.Column(db.String(100), nullable=True)
    state          = db.Column(db.String(100), nullable=True)
    pincode        = db.Column(db.String(10), nullable=True)
    shipping_rate  = db.Column(db.Float, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    status         = db.Column(db.String(20), default="open")
    admin_note     = db.Column(db.Text)


class AdminSession(db.Model):
    __tablename__ = "admin_sessions"
    id         = db.Column(db.Integer, primary_key=True)
    token      = db.Column(db.String(64), unique=True, nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    login_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen  = db.Column(db.DateTime, default=datetime.utcnow)


class StockReceipt(db.Model):
    """Records each batch of books received from the ISKCON temple main store."""
    __tablename__ = "stock_receipts"
    id             = db.Column(db.Integer, primary_key=True)
    book_id        = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=True)
    book_name      = db.Column(db.String(250), nullable=False)   # stored in case book is deleted
    quantity       = db.Column(db.Integer, nullable=False)
    cost_per_unit  = db.Column(db.Float, nullable=False)         # price paid to temple per copy
    total_payment  = db.Column(db.Float, nullable=False)         # quantity × cost_per_unit
    payment_status = db.Column(db.String(20), default="paid")    # paid / pending
    received_date  = db.Column(db.DateTime, default=datetime.utcnow)
    notes          = db.Column(db.Text)
    batch_ref      = db.Column(db.String(20), nullable=True)     # shared ID for bulk-upload rows
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    book           = db.relationship("Book", backref="stock_receipts", lazy=True)


class Setting(db.Model):
    __tablename__ = "settings"
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500), nullable=True)

    @staticmethod
    def get(key, default=None):
        s = Setting.query.get(key)
        return s.value if s else default

    @staticmethod
    def set(key, value):
        s = Setting.query.get(key)
        if s:
            s.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()


class GitaYagnaDonation(db.Model):
    """One Gita Dan Yagna donation — either paid online (linked to an Order, so it
    goes through the normal payment gateways) or entered by admin from the paper
    form (order_id empty). The temple distributes the Gitas; nothing is shipped."""
    __tablename__ = "gita_yagna_donations"
    id            = db.Column(db.Integer, primary_key=True)
    order_id      = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    source        = db.Column(db.String(20), default="online")      # online / offline
    donor_name    = db.Column(db.String(200), nullable=False)
    donor_phone   = db.Column(db.String(20))
    donor_email   = db.Column(db.String(200))
    profession    = db.Column(db.String(100))
    area          = db.Column(db.String(200))
    language      = db.Column(db.String(20), default="Hindi")       # Hindi / Gujarati / English
    quantity      = db.Column(db.Integer, nullable=False, default=1)
    amount        = db.Column(db.Float, nullable=False, default=0)
    students_qty  = db.Column(db.Integer, default=0)                # sankalpa split (all optional)
    village_qty   = db.Column(db.Integer, default=0)
    others_qty    = db.Column(db.Integer, default=0)
    arati         = db.Column(db.Boolean, default=False)            # joins Arati on Gita Jayanti
    yajna         = db.Column(db.Boolean, default=False)            # joins the Gita Yajna
    dedication    = db.Column(db.String(250))                       # "in the name of / in memory of"
    show_name     = db.Column(db.Boolean, default=False)            # donor agreed to public donor wall
    payment_mode  = db.Column(db.String(30))                        # razorpay / upi / qr / cash / cheque ...
    receipt_no    = db.Column(db.String(50))                        # paper form / receipt number
    distributed   = db.Column(db.Boolean, default=False)
    distributed_at = db.Column(db.DateTime)
    donated_on    = db.Column(db.DateTime, default=datetime.utcnow)
    notes         = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    # How the Gitas reach people: "local" = temple hands them out locally (no courier);
    # "courier" = online distribution, sent by courier to the recipient below.
    distribution   = db.Column(db.String(10), default="local")
    courier_charge = db.Column(db.Float, default=0)    # courier charge — always paid by the donor
    parcel_kg      = db.Column(db.Float)               # parcel weight used for the courier rate / shipment
    recipient_name    = db.Column(db.String(200))
    recipient_phone   = db.Column(db.String(20))
    recipient_address = db.Column(db.Text)
    recipient_city    = db.Column(db.String(100))
    recipient_state   = db.Column(db.String(100))
    recipient_pincode = db.Column(db.String(10))

    order = db.relationship("Order", foreign_keys=[order_id],
                            backref=db.backref("yagna_donation", uselist=False))

    @property
    def counted(self):
        """Counts toward totals: offline entries always, online only once paid."""
        if self.order_id is None:
            return True
        return bool(self.order and not self.order.is_deleted
                    and self.order.payment_status == "paid")

    @property
    def is_courier(self):
        return self.distribution == "courier"

    @property
    def courier_paid_by_donor(self):
        """The courier charge is always paid by the donor; local distribution has none."""
        return (self.courier_charge or 0) if self.is_courier else 0.0

    @property
    def total_paid(self):
        """What the donor pays: Gitas + courier charge (courier distribution only)."""
        return (self.amount or 0) + self.courier_paid_by_donor

    @property
    def distribution_label(self):
        return "Online distribution (courier)" if self.is_courier else "Local distribution"

    @property
    def status_label(self):
        if self.distributed:
            return "Distributed"
        return "Received" if self.counted else "Awaiting payment"

    @property
    def donor_key(self):
        return yagna_donor_key(self.donor_phone, self.donor_name)

    @property
    def donor_total(self):
        """This donor's total Gitas (paper copies, ANY language, across all their donations).
        Counts every paid / offline donation plus this one. Lists pre-compute it
        (see yagna_attach_donor_totals) to avoid one query per row."""
        cached = getattr(self, "_donor_total", None)
        if cached is not None:
            return cached
        q = GitaYagnaDonation.query
        if self.donor_phone:
            q = q.filter(GitaYagnaDonation.donor_phone == self.donor_phone)
        else:
            q = q.filter(db.func.lower(GitaYagnaDonation.donor_name) == (self.donor_name or "").strip().lower(),
                         db.or_(GitaYagnaDonation.donor_phone.is_(None), GitaYagnaDonation.donor_phone == ""))
        others = sum(r.quantity or 0 for r in q.all() if r.counted and r.id != self.id)
        return others + (self.quantity or 0)

    @property
    def invitation(self):
        """50 or more Gitas in total (50 included) -> special Gita Jayanti invitation card."""
        return self.donor_total >= YAGNA_INVITE_MIN

    @property
    def invite_min(self):
        return YAGNA_INVITE_MIN

    @property
    def event_date(self):
        return yagna_config()["event_date"]

    def __repr__(self):
        return f"<GitaYagnaDonation {self.id} {self.donor_name} x{self.quantity}>"


# ── Gita Dan Yagna settings (editable in Admin → Gita Dan Yagna) ──
YAGNA_LANGS = ("Hindi", "Gujarati", "English")
YAGNA_DEFAULT_PRICES = {"Hindi": 200, "Gujarati": 210, "English": 240}
YAGNA_DEFAULT_GOAL = 10000
YAGNA_DEFAULT_EVENT = "Sunday, 20 December 2026"
YAGNA_INVITE_MIN = 50          # donors of 50 or more Gitas in total (any language) get a special invitation card
YAGNA_MAX_QTY = 10000
YAGNA_DEFAULT_WEIGHT_KG = 0.5   # parcel weight per Gita, used for the courier rate


def yagna_donor_key(phone, name):
    phone = (phone or "").strip()
    return ("p:" + phone) if phone else ("n:" + (name or "").strip().lower())


def yagna_donor_totals():
    """{donor_key: total counted Gitas} — one donor = same mobile number (or same name when no number)."""
    totals = {}
    for r in GitaYagnaDonation.query.all():
        if r.counted:
            totals[r.donor_key] = totals.get(r.donor_key, 0) + (r.quantity or 0)
    return totals


def yagna_attach_donor_totals(rows):
    """Pre-compute .donor_total on a list of donations (one query instead of one per row)."""
    totals = yagna_donor_totals()
    for r in rows:
        r._donor_total = totals.get(r.donor_key, 0) + (0 if r.counted else (r.quantity or 0))
    return rows


def yagna_cover_path():
    """Static path of the English 'Bhagavad Gita As It Is' cover (paper edition, from the
    catalogue) for the Yagna popup and page. Falls back to the generic Gita picture."""
    try:
        books = Book.query.filter(
            Book.active == True, Book.deleted == False, Book.is_ebook == False,
            Book.language == "English", Book.title.ilike("Bhagavad Gita As It Is%")).all()
        books = [b for b in books if b.image and b.image != "default_book.jpg"]
        books.sort(key=lambda b: (b.title.strip().lower() != "bhagavad gita as it is",
                                  "large" not in b.title.lower(), b.id))
        if books:
            return "images/books/" + books[0].image
    except Exception:
        pass
    return "images/bhagvat_gita.jpg"


def yagna_config():
    prices = {}
    for lang in YAGNA_LANGS:
        try:
            prices[lang] = float(Setting.get(f"yagna_price_{lang.lower()}", YAGNA_DEFAULT_PRICES[lang]))
        except (TypeError, ValueError):
            prices[lang] = float(YAGNA_DEFAULT_PRICES[lang])
    try:
        goal = int(float(Setting.get("yagna_goal", YAGNA_DEFAULT_GOAL)))
    except (TypeError, ValueError):
        goal = YAGNA_DEFAULT_GOAL
    return {
        "enabled": Setting.get("yagna_enabled", "0") == "1",
        "goal": max(1, goal),
        "prices": prices,
        "event_date": Setting.get("yagna_event_date", YAGNA_DEFAULT_EVENT) or YAGNA_DEFAULT_EVENT,
        "weight_kg": _yagna_float(Setting.get("yagna_weight_kg"), YAGNA_DEFAULT_WEIGHT_KG),
    }


def _yagna_float(value, default):
    try:
        v = float(value)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def yagna_courier_charge(pincode, quantity, cfg=None):
    """Courier charge for sending `quantity` Gitas to `pincode` — the same rule the
    store checkout uses: Delhivery rate for the weight, else the flat store charge."""
    cfg = cfg or yagna_config()
    weight_grams = max(int(quantity * cfg["weight_kg"] * 1000), 500)
    try:
        from delhivery import get_shipping_rate
        rate, _zone, _err = get_shipping_rate(pincode, weight_grams)
    except Exception:
        rate = None
    return float(rate) if rate is not None else float(app.config["SHIPPING_CHARGE"])


def yagna_stats(cfg=None):
    cfg = cfg or yagna_config()
    rows = GitaYagnaDonation.query.all()
    counted = [r for r in rows if r.counted]
    gitas = sum(r.quantity or 0 for r in counted)
    by_lang = {lang: sum(r.quantity or 0 for r in counted if r.language == lang) for lang in YAGNA_LANGS}
    courier = [r for r in counted if r.is_courier]
    return {
        "gitas": gitas,
        "amount": sum(r.total_paid for r in counted),
        "gita_amount": sum(r.amount or 0 for r in counted),
        "local_gitas": sum(r.quantity or 0 for r in counted if not r.is_courier),
        "local_donors": sum(1 for r in counted if not r.is_courier),
        "courier_gitas": sum(r.quantity or 0 for r in courier),
        "courier_donors": len(courier),
        "courier_collected": sum(r.courier_paid_by_donor for r in counted),
        "donors": len(counted),
        "online": sum(1 for r in counted if r.source == "online"),
        "offline": sum(1 for r in counted if r.source == "offline"),
        "pending": sum(1 for r in rows if not r.counted),
        "distributed": sum(r.quantity or 0 for r in counted if r.distributed),
        "invitations": sum(1 for v in yagna_donor_totals().values() if v >= YAGNA_INVITE_MIN),
        "students": sum(r.students_qty or 0 for r in counted),
        "village": sum(r.village_qty or 0 for r in counted),
        "others": sum(r.others_qty or 0 for r in counted),
        "by_lang": by_lang,
        "goal": cfg["goal"],
        "pct": min(100, round(gitas * 100 / cfg["goal"], 1)) if cfg["goal"] else 0,
    }


class Customer(db.Model):
    __tablename__ = "customers"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False, index=True)
    phone         = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    tier                = db.Column(db.String(20), default="regular")  # regular / loyal / vip
    is_active           = db.Column(db.Boolean, default=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    reset_token         = db.Column(db.String(64), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    # Saved delivery address (updated after every order)
    saved_address       = db.Column(db.Text, nullable=True)
    saved_city          = db.Column(db.String(100), nullable=True)
    saved_state         = db.Column(db.String(100), nullable=True)
    saved_pincode       = db.Column(db.String(10), nullable=True)
    orders        = db.relationship("Order", backref="customer", lazy="dynamic",
                                    foreign_keys="Order.customer_id")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def total_orders(self):
        return self.orders.filter(Order.order_status != "cancelled").count()

    @property
    def total_spent(self):
        from sqlalchemy import func
        result = db.session.query(func.sum(Order.total_amount)).filter(
            Order.customer_id == self.id,
            Order.order_status != "cancelled",
        ).scalar()
        return result or 0.0

    def update_tier(self):
        n, s = self.total_orders, self.total_spent
        if n >= 10 or s >= 5000:
            self.tier = "vip"
        elif n >= 3 or s >= 1000:
            self.tier = "loyal"
        else:
            self.tier = "regular"

    def __repr__(self):
        return f"<Customer {self.email}>"


class Review(db.Model):
    """Customer-submitted book review. Only verified purchasers can create one
    (enforced in the submit_review route), and it stays hidden from the
    public book page until an admin approves it."""
    __tablename__ = "reviews"
    id          = db.Column(db.Integer, primary_key=True)
    book_id     = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    rating      = db.Column(db.Integer, nullable=False)   # 1-5
    comment     = db.Column(db.Text, nullable=True)
    approved    = db.Column(db.Boolean, default=False, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    book     = db.relationship("Book", backref=db.backref("reviews", lazy="dynamic"))
    customer = db.relationship("Customer", backref=db.backref("reviews", lazy="dynamic"))

    __table_args__ = (db.UniqueConstraint("book_id", "customer_id", name="uq_review_book_customer"),)

    def __repr__(self):
        return f"<Review book={self.book_id} customer={self.customer_id} rating={self.rating}>"


class Magazine(db.Model):
    __tablename__ = "magazines"
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    issue_label  = db.Column(db.String(100), default="Issue 1")
    description  = db.Column(db.Text)
    pdf_filename = db.Column(db.String(200))          # file inside static/magazines/
    single_price = db.Column(db.Float, default=49.0)  # one-time purchase price
    is_free      = db.Column(db.Boolean, default=False)
    active       = db.Column(db.Boolean, default=True)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchases    = db.relationship("MagazinePurchase", backref="magazine", lazy=True)

    def __repr__(self):
        return f"<Magazine {self.title}>"


class MagazineSubscription(db.Model):
    __tablename__ = "magazine_subscriptions"
    id                  = db.Column(db.Integer, primary_key=True)
    customer_id         = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    plan                = db.Column(db.String(20), nullable=False)  # 'monthly' | 'yearly'
    start_date          = db.Column(db.DateTime, default=datetime.utcnow)
    end_date            = db.Column(db.DateTime, nullable=False)
    razorpay_order_id   = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    amount_paid         = db.Column(db.Float)
    status              = db.Column(db.String(20), default="active")  # active | expired
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    customer            = db.relationship("Customer", backref="mag_subscriptions")


class MagazinePurchase(db.Model):
    __tablename__ = "magazine_purchases"
    id                  = db.Column(db.Integer, primary_key=True)
    customer_id         = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    magazine_id         = db.Column(db.Integer, db.ForeignKey("magazines.id"), nullable=False)
    razorpay_order_id   = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    amount_paid         = db.Column(db.Float)
    purchased_at        = db.Column(db.DateTime, default=datetime.utcnow)
    customer            = db.relationship("Customer", backref="mag_purchases")


class PendingMagPayment(db.Model):
    """Temporary record created before payment — lets PayU callbacks find context without session."""
    __tablename__ = "pending_mag_payments"
    id              = db.Column(db.Integer, primary_key=True)
    txn_ref         = db.Column(db.String(100), unique=True, nullable=False)
    payment_type    = db.Column(db.String(20))   # 'buy' | 'subscribe'
    mag_id          = db.Column(db.Integer, nullable=True)
    plan            = db.Column(db.String(20), nullable=True)
    customer_id     = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    amount          = db.Column(db.Float)
    payment_method  = db.Column(db.String(20))   # 'razorpay' | 'payu' | 'upi'
    status          = db.Column(db.String(20), default="pending")   # pending/completed/failed
    utr             = db.Column(db.String(100), nullable=True)
    razorpay_order_id = db.Column(db.String(100), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    customer        = db.relationship("Customer", backref="pending_mag_payments")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def save_image(file):
    """Save uploaded image and return filename."""
    if file and allowed_file(file.filename):
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > app.config["MAX_IMAGE_SIZE"]:
            return None
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return filename
    return None


_EBOOK_MIMETYPES = {"pdf": "application/pdf", "epub": "application/epub+zip"}


def allowed_ebook_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EBOOK_EXTENSIONS"]


def save_ebook(file):
    """Save uploaded ebook file and return filename."""
    if file and allowed_ebook_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config["EBOOK_FOLDER"], filename))
        return filename
    return None


def save_preview(file):
    """Save uploaded preview PDF and return filename (stored in static/previews/)."""
    if file and file.filename and file.filename.lower().endswith(".pdf"):
        filename = f"preview_{uuid.uuid4().hex}.pdf"
        file.save(os.path.join(app.config["PREVIEW_FOLDER"], filename))
        return filename
    return None


ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "avi", "mkv", "m4v"}

_VIDEO_MIME = {
    "mp4":  "video/mp4",
    "m4v":  "video/mp4",
    "mov":  "video/mp4",
    "webm": "video/webm",
    "avi":  "video/x-msvideo",
    "mkv":  "video/x-matroska",
}


@app.route("/video/review/<path:filename>")
def serve_review_video_stream(filename):
    video_path = os.path.join(app.config["REVIEW_VIDEO_FOLDER"], filename)
    if not os.path.isfile(video_path):
        abort(404)
    ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    mime = _VIDEO_MIME.get(ext, "video/mp4")
    return send_file(video_path, mimetype=mime, conditional=True)


def save_review_video(file):
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext in ALLOWED_VIDEO_EXTENSIONS:
            filename = f"review_{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config["REVIEW_VIDEO_FOLDER"], filename))
            return filename
    return None


def _make_embed_url(url):
    """Convert any YouTube URL (watch/short/youtu.be) to embed URL. Returns other URLs as-is."""
    import re as _re
    if not url:
        return None
    url = url.strip()
    # YouTube Shorts: youtube.com/shorts/VIDEO_ID
    m = _re.search(r"youtube\.com/shorts/([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}?rel=0"
    # YouTube watch URL or youtu.be short link
    m = _re.search(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}?rel=0"
    return url


def generate_order_number():
    return "ISKCON" + datetime.now().strftime("%Y%m%d") + uuid.uuid4().hex[:6].upper()


def get_magazine_access(customer_id, magazine_id):
    """Return True if customer has full access to the given magazine."""
    mag = Magazine.query.get(magazine_id)
    if not mag or mag.is_free:
        return True
    if not customer_id:
        return False
    now = datetime.utcnow()
    sub = MagazineSubscription.query.filter_by(
        customer_id=customer_id, status="active"
    ).filter(MagazineSubscription.end_date > now).first()
    if sub:
        return True
    purchase = MagazinePurchase.query.filter_by(
        customer_id=customer_id, magazine_id=magazine_id
    ).first()
    return purchase is not None


def _create_razorpay_order(amount_inr, receipt, notes=None):
    """Create a Razorpay order and return the order dict or raise."""
    import requests as _req
    payload = {
        "amount":   int(amount_inr * 100),
        "currency": "INR",
        "receipt":  receipt,
        "notes":    notes or {},
    }
    resp = _req.post(
        "https://api.razorpay.com/v1/orders",
        json=payload,
        auth=(app.config["RAZORPAY_KEY_ID"], app.config["RAZORPAY_KEY_SECRET"]),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Cart helpers (stored in Flask session) ──

def get_cart():
    return session.get("cart", {})


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


# ── Combo cart helpers — deliberately a SEPARATE session key from the
# regular book cart (not merged into the same dict). The existing cart
# logic throughout the app assumes every cart key is a plain book id;
# keeping combos in their own session key means none of that existing,
# already-working book-cart code has to change or risk breaking. ──

def get_combo_cart():
    return session.get("combo_cart", {})


def save_combo_cart(combo_cart):
    session["combo_cart"] = combo_cart
    session.modified = True


def combo_weight_kg(combo):
    """Total shipping weight of one unit of this combo (sum of its books)."""
    default_w = app.config["DELHIVERY_DEFAULT_WEIGHT"]
    return sum((ci.book.weight_kg or default_w) * ci.quantity
               for ci in combo.combo_items if ci.book)


def item_weight_kg(item):
    """Shipping weight for one cart_totals() line item (book or combo)."""
    if item["is_combo"]:
        return combo_weight_kg(item["combo"])
    return item["book"].weight_kg or app.config["DELHIVERY_DEFAULT_WEIGHT"]


def item_is_ebook(item):
    """True only if every book behind this line item is an ebook (a combo
    counts as physical/shippable unless every book in it is an ebook)."""
    if item["is_combo"]:
        return all(ci.book.is_ebook for ci in item["combo"].combo_items if ci.book)
    return item["book"].is_ebook


# ── Wishlist helpers (stored in Flask session, same pattern as cart) ──

def get_wishlist():
    return session.get("wishlist", [])


def save_wishlist(wishlist):
    session["wishlist"] = wishlist
    session.modified = True


def wishlist_item_count():
    return len(get_wishlist())


def cart_item_count():
    return (sum(item["qty"] for item in get_cart().values())
            + sum(item["qty"] for item in get_combo_cart().values()))


def cart_totals():
    cart       = get_cart()
    combo_cart = get_combo_cart()
    if not cart and not combo_cart:
        return {"subtotal": 0, "shipping": 0, "discount": 0, "total": 0, "items": []}

    book_ids = [int(k) for k in cart.keys()]
    books = {b.id: b for b in Book.query.filter(Book.id.in_(book_ids)).all()}

    items, subtotal = [], 0
    for book_id_str, item in cart.items():
        book = books.get(int(book_id_str))
        if not book or book.deleted or not book.active:
            continue
        line_total = book.price * item["qty"]
        subtotal += line_total
        items.append({
            "is_combo":   False,
            "book":       book,
            "combo":      None,
            "qty":        item["qty"],
            "line_total": line_total,
        })

    if combo_cart:
        combo_ids = [int(k) for k in combo_cart.keys()]
        combos = {c.id: c for c in Combo.query.filter(Combo.id.in_(combo_ids)).all()}
        for combo_id_str, item in combo_cart.items():
            combo = combos.get(int(combo_id_str))
            if not combo or not combo.active:
                continue
            line_total = combo.selling_price * item["qty"]
            subtotal += line_total
            items.append({
                "is_combo":   True,
                "book":       None,
                "combo":      combo,
                "qty":        item["qty"],
                "line_total": line_total,
            })

    all_ebooks = bool(items) and all(item_is_ebook(item) for item in items)
    shipping = 0 if all_ebooks else app.config["SHIPPING_CHARGE"]

    # Re-validate any applied coupon against the current subtotal
    code = session.get("coupon_code")
    if code:
        coupon = Coupon.query.filter_by(code=code).first()
        valid = coupon.is_valid(subtotal)[0] if coupon else False
        if coupon and valid:
            session["coupon_discount"] = coupon.calculate_discount(subtotal)
        else:
            session.pop("coupon_code", None)
            session.pop("coupon_discount", None)
            session.pop("coupon_auto", None)
            code = None

    # No coupon applied — try to auto-apply the best matching coupon
    if not code:
        best, best_discount = None, 0
        for c in Coupon.query.filter_by(active=True, auto_apply=True).all():
            if c.is_valid(subtotal)[0]:
                d = c.calculate_discount(subtotal)
                if d > best_discount:
                    best, best_discount = c, d
        if best:
            session["coupon_code"]     = best.code
            session["coupon_discount"] = best_discount
            session["coupon_auto"]     = True

    discount = session.get("coupon_discount", 0)
    total = max(0, subtotal + shipping - discount)

    return {
        "items":    items,
        "subtotal": subtotal,
        "shipping": shipping,
        "discount": discount,
        "total":    total,
    }


# ── Admin auth ──

def safe_books_return(value):
    """Only allow redirecting back into /admin/books (with its filters/page
    intact) — falls back to the plain list for anything else or missing."""
    if value and value.startswith("/admin/books"):
        return value
    return url_for("admin_books")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login to access the admin panel.", "warning")
            return redirect(url_for("admin_login"))
        token = session.get("admin_session_token")
        try:
            if token:
                rec = AdminSession.query.filter_by(token=token).first()
                if rec:
                    rec.last_seen = datetime.utcnow()
                    db.session.commit()
                else:
                    token = None
            if not token:
                token = secrets.token_hex(32)
                session["admin_session_token"] = token
                ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
                db.session.add(AdminSession(token=token, ip_address=ip))
                db.session.commit()
        except Exception:
            db.session.rollback()
        return f(*args, **kwargs)
    return decorated


# ── Customer auth ──

def get_current_customer():
    cid = session.get("customer_id")
    if cid:
        try:
            return Customer.query.get(cid)
        except Exception:
            db.session.rollback()   # clear aborted-transaction state so other queries still work
            session.pop("customer_id", None)
    return None


def customer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("customer_id"):
            flash("Please log in to access your account.", "warning")
            return redirect(url_for("customer_login", next=request.full_path))
        return f(*args, **kwargs)
    return decorated


# ── Context processors ──

@app.context_processor
def inject_globals():
    return {
        "cart_count":       cart_item_count(),
        "wishlist_ids":     get_wishlist(),
        "wishlist_count":   wishlist_item_count(),
        "categories":       Category.query.order_by(Category.sort_order).all(),
        "store_name":       app.config["STORE_NAME"],
        "whatsapp_num":     app.config["WHATSAPP_NUMBER"],
        "social_facebook":  app.config["SOCIAL_FACEBOOK_URL"],
        "social_instagram": app.config["SOCIAL_INSTAGRAM_URL"],
        "social_youtube":   app.config["SOCIAL_YOUTUBE_URL"],
        "upi_id":           app.config["UPI_ID"],
        "upi_name":         app.config["UPI_NAME"],
        "shipping_charge":      app.config["SHIPPING_CHARGE"],
        "free_shipping_above":  app.config["FREE_SHIPPING_ABOVE"],
        "current_customer": get_current_customer(),
        "pending_review_count": (Review.query.filter_by(approved=False).count()
                                  if request.path.startswith("/admin") else 0),
        "now":              datetime.utcnow(),
        "settings_get":     Setting.get,
    }


# ─────────────────────────────────────────────
# Static info pages (About, Privacy, Shipping, Refund)
# ─────────────────────────────────────────────

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.route("/shipping-policy")
def shipping_policy():
    return render_template("shipping_policy.html")


@app.route("/refund-policy")
def refund_policy():
    return render_template("refund_policy.html")


# ─────────────────────────────────────────────
# SEO — sitemap & robots
# ─────────────────────────────────────────────

@app.route("/api/shipping-rate/<pincode>")
def api_shipping_rate(pincode):
    """AJAX: return Delhivery Prepaid rate for a destination pincode."""
    if not pincode.isdigit() or len(pincode) != 6:
        return jsonify({"serviceable": False, "error": "Invalid pincode"})
    from delhivery import get_shipping_rate, check_serviceability, estimate_delivery_days
    svc = check_serviceability(pincode)
    if not svc.get("serviceable"):
        return jsonify({"serviceable": False, "error": "Delhivery does not deliver to this pincode"})
    if not svc.get("pre_paid"):
        return jsonify({"serviceable": False, "error": "Prepaid delivery not available at this pincode"})
    totals = cart_totals()
    weight_grams = max(
        int(sum(item["qty"] * item_weight_kg(item) * 1000 for item in totals["items"])),
        500
    )
    rate, zone, err = get_shipping_rate(pincode, weight_grams)
    if err or rate is None:
        return jsonify({"serviceable": False, "error": err or "Rate unavailable"})
    eta_min, eta_max = estimate_delivery_days(zone, svc.get("oda", False))
    return jsonify({
        "serviceable": True,
        "rate":    rate,
        "zone":    zone,
        "city":    svc.get("city", ""),
        "oda":     svc.get("oda", False),
        "eta_min": eta_min,
        "eta_max": eta_max,
    })


@app.route("/api/shipping-rate-book/<pincode>/<int:book_id>")
def api_shipping_rate_book(pincode, book_id):
    """AJAX: Delhivery rate for a single book (used by the WhatsApp enquiry
    modal on the book page, before anything is in the cart)."""
    if not pincode.isdigit() or len(pincode) != 6:
        return jsonify({"serviceable": False, "error": "Invalid pincode"})
    book = Book.query.get(book_id)
    if not book:
        return jsonify({"serviceable": False, "error": "Book not found"})
    from delhivery import get_shipping_rate, check_serviceability, estimate_delivery_days
    svc = check_serviceability(pincode)
    if not svc.get("serviceable"):
        return jsonify({"serviceable": False, "error": "Delhivery does not deliver to this pincode"})
    if not svc.get("pre_paid"):
        return jsonify({"serviceable": False, "error": "Prepaid delivery not available at this pincode"})
    weight_grams = max(int((book.weight_kg or app.config["DELHIVERY_DEFAULT_WEIGHT"]) * 1000), 500)
    rate, zone, err = get_shipping_rate(pincode, weight_grams)
    if err or rate is None:
        return jsonify({"serviceable": False, "error": err or "Rate unavailable"})
    eta_min, eta_max = estimate_delivery_days(zone, svc.get("oda", False))
    return jsonify({
        "serviceable": True,
        "rate":    rate,
        "city":    svc.get("city", ""),
        "oda":     svc.get("oda", False),
        "eta_min": eta_min,
        "eta_max": eta_max,
    })


@app.route("/admin/api/shipping-rate-multi/<pincode>")
@admin_required
def admin_api_shipping_rate_multi(pincode):
    """AJAX: Delhivery rate for an arbitrary set of books+quantities, keyed
    by 'book_id:qty' pairs — used by the manual order form (WhatsApp/phone/
    walk-in orders) since those items never pass through the session cart."""
    if not pincode.isdigit() or len(pincode) != 6:
        return jsonify({"serviceable": False, "error": "Invalid pincode"})

    items_param = request.args.get("items", "")
    total_weight_kg = 0.0
    any_physical = False
    for pair in items_param.split(","):
        if ":" not in pair:
            continue
        bid_str, qty_str = pair.split(":", 1)
        try:
            bid, qty = int(bid_str), int(qty_str)
        except ValueError:
            continue
        book = Book.query.get(bid)
        if not book or book.is_ebook or qty <= 0:
            continue
        any_physical = True
        total_weight_kg += (book.weight_kg or app.config["DELHIVERY_DEFAULT_WEIGHT"]) * qty

    if not any_physical:
        return jsonify({"serviceable": True, "rate": 0, "note": "No physical books — no shipping needed"})

    from delhivery import get_shipping_rate, check_serviceability, estimate_delivery_days
    svc = check_serviceability(pincode)
    if not svc.get("serviceable"):
        return jsonify({"serviceable": False, "error": "Delhivery does not deliver to this pincode"})
    if not svc.get("pre_paid"):
        return jsonify({"serviceable": False, "error": "Prepaid delivery not available at this pincode"})

    weight_grams = max(int(total_weight_kg * 1000), 500)
    rate, zone, err = get_shipping_rate(pincode, weight_grams)
    if err or rate is None:
        return jsonify({"serviceable": False, "error": err or "Rate unavailable"})
    eta_min, eta_max = estimate_delivery_days(zone, svc.get("oda", False))
    return jsonify({
        "serviceable": True,
        "rate":    rate,
        "city":    svc.get("city", ""),
        "eta_min": eta_min,
        "eta_max": eta_max,
    })


@app.route("/sitemap.xml")
def sitemap():
    domain = "https://iskconbooks.in"
    books  = Book.query.filter_by(active=True, deleted=False).all()
    lines  = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in ["/", "/books", "/order/track", "/about", "/privacy-policy", "/shipping-policy", "/refund-policy"]:
        lines.append(f"<url><loc>{domain}{path}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>")
    for book in books:
        lines.append(f"<url><loc>{domain}/book/{book.id}</loc><changefreq>monthly</changefreq><priority>0.9</priority></url>")
    lines.append("</urlset>")
    return "\n".join(lines), 200, {"Content-Type": "application/xml"}


@app.route("/robots.txt")
def robots():
    content = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /checkout
Disallow: /cart
Disallow: /payment/
Disallow: /order/success/
Disallow: /order/failed/

Sitemap: https://iskconbooks.in/sitemap.xml
"""
    return content, 200, {"Content-Type": "text/plain"}


# ─────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    featured_books  = (Book.query.filter_by(featured=True, active=True, deleted=False)
                       .order_by(Book.created_at.desc()).limit(8).all())
    new_arrivals    = (Book.query.filter_by(active=True, deleted=False)
                       .order_by(Book.created_at.desc()).limit(6).all())
    # Featured combos first, then newest; up to 8 on the home page
    home_combos     = (Combo.query.filter_by(active=True)
                       .order_by(db.case((Combo.featured == True, 0), else_=1), Combo.created_at.desc())
                       .limit(8).all())
    categories      = Category.query.order_by(Category.sort_order).all()
    # Look up carousel books from admin settings, fall back to keyword search
    def get_carousel_book(setting_key, keyword):
        book_id = Setting.get(setting_key)
        if book_id:
            b = Book.query.filter_by(id=int(book_id), active=True).first()
            if b:
                return b
        return Book.query.filter(Book.title.ilike(f'%{keyword}%'), Book.active == True).order_by(Book.id).first()

    carousel_books = {
        'slide0':  get_carousel_book('carousel_slide_0', 'Prabhupada'),
        'gita':    get_carousel_book('carousel_slide_1', 'Bhagavad Gita'),
        'sb':      get_carousel_book('carousel_slide_2', 'Bhagavatam'),
        'krishna': get_carousel_book('carousel_slide_3', 'Krishna'),
        'nod':     get_carousel_book('carousel_slide_4', 'Nectar of Devotion'),
    }
    yagna_cfg = yagna_config()
    yagna_banner = yagna_stats(yagna_cfg) if yagna_cfg["enabled"] else None
    return render_template("index.html",
                           yagna_banner=yagna_banner, yagna_cfg=yagna_cfg,
                           yagna_cover=yagna_cover_path() if yagna_banner else None,
                           featured_books=featured_books,
                           new_arrivals=new_arrivals,
                           home_combos=home_combos,
                           categories=categories,
                           carousel_books=carousel_books)


@app.route("/books")
def books():
    query  = request.args.get("q", "").strip()
    cat    = request.args.get("category", "")
    lang   = request.args.get("language", "")
    sort   = request.args.get("sort", "title")
    page   = request.args.get("page", 1, type=int)

    bq = Book.query.filter_by(active=True)

    if query:
        import re
        # Spelling-tolerant match (title/author/language/format) OR the
        # original keyword match (which also looks inside descriptions).
        smart_ids = [b["id"] for b in smart_search(query)]
        keyword_conds = []
        for word in query.split():
            word = re.sub(r"[^\w]", "", word)
            if not word:
                continue
            keyword_conds.append(or_(
                Book.title.ilike(f"%{word}%"),
                Book.author.ilike(f"%{word}%"),
                Book.description.ilike(f"%{word}%"),
            ))
        conds = []
        if smart_ids:
            conds.append(Book.id.in_(smart_ids))
        if keyword_conds:
            conds.append(db.and_(*keyword_conds))
        bq = bq.filter(or_(*conds)) if conds else bq.filter(db.false())
    if cat:
        category = Category.query.filter_by(slug=cat).first()
        if category:
            bq = bq.filter_by(category_id=category.id)
    if lang:
        bq = bq.filter_by(language=lang)

    sort_map = {
        "title":      Book.title.asc(),
        "price_low":  Book.price.asc(),
        "price_high": Book.price.desc(),
        "newest":     Book.created_at.desc(),
    }
    bq = bq.order_by(sort_map.get(sort, Book.title.asc()))

    pagination   = bq.paginate(page=page, per_page=12, error_out=False)
    languages    = [r[0] for r in db.session.query(Book.language).filter_by(active=True).distinct().all()]
    active_cat   = Category.query.filter_by(slug=cat).first() if cat else None

    return render_template("books.html",
                           books=pagination.items,
                           pagination=pagination,
                           query=query,
                           active_cat=active_cat,
                           language=lang,
                           sort=sort,
                           languages=languages)


def customer_has_purchased(customer_id, book_id):
    """True if this customer has a paid order containing this book — the
    'verified purchase' gate for leaving a review."""
    return db.session.query(OrderItem.id).join(Order, OrderItem.order_id == Order.id).filter(
        OrderItem.book_id == book_id,
        Order.customer_id == customer_id,
        Order.payment_status == "paid",
    ).first() is not None


@app.route("/book/<int:book_id>")
def book_detail(book_id):
    import re
    book    = Book.query.get_or_404(book_id)
    if book.deleted or not book.active:
        abort(404)
    related = Book.query.filter_by(category_id=book.category_id, active=True)\
                        .filter(Book.id != book_id).limit(4).all()

    # Find same book in other languages by stripping trailing "(Language)" from title
    base_title = re.sub(r'\s*\(\s*[^)]+\)\s*$', '', book.title).strip()
    other_lang_books = Book.query.filter(
        Book.active == True,
        Book.id != book_id,
        Book.title.ilike(f'{base_title}%'),
        Book.language != book.language,
    ).order_by(Book.language).all() if base_title else []

    # ── Customer reviews ──
    approved_reviews = (Review.query.filter_by(book_id=book_id, approved=True)
                         .order_by(Review.created_at.desc()).all())
    review_count = len(approved_reviews)
    avg_rating = round(sum(r.rating for r in approved_reviews) / review_count, 1) if review_count else 0

    customer = get_current_customer()
    my_review = None
    can_review = False
    if customer:
        my_review = Review.query.filter_by(book_id=book_id, customer_id=customer.id).first()
        can_review = (not my_review) and customer_has_purchased(customer.id, book_id)

    return render_template("book_detail.html", book=book, related=related,
                           other_lang_books=other_lang_books,
                           approved_reviews=approved_reviews,
                           review_count=review_count, avg_rating=avg_rating,
                           my_review=my_review, can_review=can_review)


@app.route("/book/<int:book_id>/review", methods=["POST"])
@customer_login_required
def submit_review(book_id):
    book = Book.query.get_or_404(book_id)
    customer = get_current_customer()

    if not customer_has_purchased(customer.id, book_id):
        flash("Only customers who've purchased this book can leave a review.", "warning")
        return redirect(url_for("book_detail", book_id=book_id))

    if Review.query.filter_by(book_id=book_id, customer_id=customer.id).first():
        flash("You've already reviewed this book.", "info")
        return redirect(url_for("book_detail", book_id=book_id))

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0
    if rating < 1 or rating > 5:
        flash("Please select a star rating from 1 to 5.", "danger")
        return redirect(url_for("book_detail", book_id=book_id))

    comment = request.form.get("comment", "").strip()[:2000]

    review = Review(book_id=book_id, customer_id=customer.id, rating=rating,
                     comment=comment or None, approved=False)
    db.session.add(review)
    db.session.commit()
    flash("Thank you! Your review has been submitted and will appear once approved.", "success")
    return redirect(url_for("book_detail", book_id=book_id))


# ─────────────────────────────────────────────
# COMBO ROUTES (customer-facing)
# ─────────────────────────────────────────────

@app.route("/combos")
def combo_list():
    language = request.args.get("language", "")
    cq = Combo.query.filter_by(active=True)
    if language:
        cq = cq.filter_by(language=language)
    combos = cq.order_by(Combo.name).all()
    languages = [r[0] for r in db.session.query(Combo.language)
                 .filter(Combo.active == True).distinct().order_by(Combo.language).all()]
    return render_template("combos.html", combos=combos, language=language, languages=languages)


@app.route("/combo/<int:combo_id>")
def combo_detail(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    if not combo.active:
        abort(404)
    related = Combo.query.filter(Combo.active == True, Combo.id != combo_id).limit(4).all()
    return render_template("combo_detail.html", combo=combo, related=related)


@app.route("/static/images/combos/<path:filename>")
def serve_combo_image(filename):
    folder = os.path.join(BASE_DIR, "static", "images", "combos")
    filepath = os.path.join(folder, filename)
    if os.path.isfile(filepath):
        return send_from_directory(folder, filename)

    # Check alternate extension (.png <-> .jpg <-> .jpeg <-> .webp)
    base, _ = os.path.splitext(filename)
    for alt_ext in (".jpg", ".jpeg", ".png", ".webp"):
        alt_name = base + alt_ext
        if os.path.isfile(os.path.join(folder, alt_name)):
            return send_from_directory(folder, alt_name)

    # Check persistent volume (inside UPLOAD_FOLDER/combos)
    persistent_folder = os.path.join(app.config.get("UPLOAD_FOLDER", ""), "combos")
    if os.path.isfile(os.path.join(persistent_folder, filename)):
        return send_from_directory(persistent_folder, filename)

    # Fallback to default book image so it never shows a broken icon
    return send_from_directory(os.path.join(BASE_DIR, "static", "images", "books"), "default_book.jpg")


@app.route("/admin/receive-image", methods=["POST"])
def receive_image():
    token = request.form.get("token", "")
    if token != "iskcon-img-sync-2024":
        abort(403)
    f = request.files.get("file")
    filename = request.form.get("filename", "")
    target = request.form.get("target", "books")  # "books" or "combos"
    if not f or not filename:
        return "bad request", 400
    if target == "combos":
        save_folder = os.path.join(BASE_DIR, "static", "images", "combos")
        persistent_folder = os.path.join(app.config.get("UPLOAD_FOLDER", ""), "combos")
    else:
        save_folder = app.config.get("UPLOAD_FOLDER", "")
        persistent_folder = None
    os.makedirs(save_folder, exist_ok=True)
    save_path = os.path.join(save_folder, filename)
    f.save(save_path)
    if persistent_folder:
        os.makedirs(persistent_folder, exist_ok=True)
        try:
            import shutil
            shutil.copy2(save_path, os.path.join(persistent_folder, filename))
        except Exception:
            pass
    return f"saved:{filename}", 200


# ─────────────────────────────────────────────
# CART ROUTES
# ─────────────────────────────────────────────

@app.route("/cart/add/<int:book_id>", methods=["POST"])
def add_to_cart(book_id):
    book = Book.query.get_or_404(book_id)
    if book.deleted or not book.active:
        abort(404)
    qty  = int(request.form.get("qty", 1))
    cart = get_cart()
    key  = str(book_id)
    if key in cart:
        cart[key]["qty"] = min(cart[key]["qty"] + qty, book.stock)
    else:
        cart[key] = {"qty": qty, "title": book.title}
    save_cart(cart)
    flash(f'"{book.title}" added to cart!', "success")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "cart_count": cart_item_count()})
    if request.form.get("buy_now"):
        return redirect(url_for("checkout"))
    return redirect(request.referrer or url_for("cart"))


@app.route("/wishlist/toggle/<int:book_id>", methods=["POST"])
def wishlist_toggle(book_id):
    book = Book.query.get_or_404(book_id)
    wishlist = get_wishlist()
    key = str(book_id)
    if key in wishlist:
        wishlist.remove(key)
        added = False
    else:
        wishlist.append(key)
        added = True
    save_wishlist(wishlist)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "in_wishlist": added, "wishlist_count": len(wishlist)})
    flash(f'"{book.title}" {"added to" if added else "removed from"} your wishlist.', "success")
    return redirect(request.referrer or url_for("books"))


@app.route("/wishlist")
def wishlist():
    ids = [int(i) for i in get_wishlist()]
    books = []
    if ids:
        books = Book.query.filter(Book.id.in_(ids), Book.deleted == False).all()
        order = {book_id: idx for idx, book_id in enumerate(ids)}
        books.sort(key=lambda b: order.get(b.id, 0), reverse=True)
    return render_template("wishlist.html", books=books)


@app.route("/cart")
def cart():
    totals = cart_totals()
    coupon_code = session.get("coupon_code", "")
    coupon_auto = session.get("coupon_auto", False)
    return render_template("cart.html", **totals, coupon_code=coupon_code, coupon_auto=coupon_auto)


@app.route("/cart/update", methods=["POST"])
def update_cart():
    cart = get_cart()
    for key in list(cart.keys()):
        new_qty = request.form.get(f"qty_{key}", type=int)
        if new_qty is not None:
            if new_qty <= 0:
                del cart[key]
            else:
                cart[key]["qty"] = new_qty
    save_cart(cart)

    combo_cart = get_combo_cart()
    for key in list(combo_cart.keys()):
        new_qty = request.form.get(f"combo_qty_{key}", type=int)
        if new_qty is not None:
            if new_qty <= 0:
                del combo_cart[key]
            else:
                combo_cart[key]["qty"] = new_qty
    save_combo_cart(combo_cart)

    # Reset coupon if cart changed
    session.pop("coupon_code", None)
    session.pop("coupon_discount", None)
    flash("Cart updated.", "success")
    return redirect(url_for("cart"))


@app.route("/combo/<int:combo_id>/add-to-cart", methods=["POST"])
def add_combo_to_cart(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    if not combo.active:
        abort(404)
    qty = max(1, request.form.get("qty", 1, type=int))
    combo_cart = get_combo_cart()
    key = str(combo_id)
    if key in combo_cart:
        combo_cart[key]["qty"] += qty
    else:
        combo_cart[key] = {"qty": qty}
    save_combo_cart(combo_cart)
    flash(f'"{combo.name}" added to cart!', "success")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "cart_count": cart_item_count()})
    if request.form.get("buy_now"):
        return redirect(url_for("checkout"))
    return redirect(request.referrer or url_for("cart"))


@app.route("/combo/remove/<int:combo_id>")
def remove_combo_from_cart(combo_id):
    combo_cart = get_combo_cart()
    combo_cart.pop(str(combo_id), None)
    save_combo_cart(combo_cart)
    session.pop("coupon_code", None)
    session.pop("coupon_discount", None)
    flash("Combo removed from cart.", "info")
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:book_id>")
def remove_from_cart(book_id):
    cart = get_cart()
    cart.pop(str(book_id), None)
    save_cart(cart)
    session.pop("coupon_code", None)
    session.pop("coupon_discount", None)
    flash("Item removed from cart.", "info")
    return redirect(url_for("cart"))


@app.route("/cart/clear")
def clear_cart():
    session.pop("cart", None)
    session.pop("combo_cart", None)
    session.pop("coupon_code", None)
    session.pop("coupon_discount", None)
    return redirect(url_for("cart"))


# ─────────────────────────────────────────────
# COUPON
# ─────────────────────────────────────────────

@app.route("/apply-coupon", methods=["POST"])
def apply_coupon():
    code    = request.form.get("coupon_code", "").strip().upper()
    totals  = cart_totals()
    coupon  = Coupon.query.filter_by(code=code).first()

    if not coupon:
        flash("Invalid coupon code.", "danger")
        return redirect(url_for("cart"))

    valid, msg = coupon.is_valid(totals["subtotal"])
    if not valid:
        flash(msg, "danger")
        return redirect(url_for("cart"))

    discount = coupon.calculate_discount(totals["subtotal"])
    session["coupon_code"]     = code
    session["coupon_discount"] = discount
    session["coupon_auto"]     = False
    session.modified = True
    flash(f"Coupon applied! You saved ₹{discount:.0f}.", "success")
    return redirect(url_for("cart"))


# ─────────────────────────────────────────────
# CHECKOUT & PAYMENT
# ─────────────────────────────────────────────
# PayU helpers
# ─────────────────────────────────────────────

def _payu_hash(key, txnid, amount, productinfo, firstname, email, salt):
    s = f"{key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}|||||||||{salt}"
    return hashlib.sha512(s.encode("utf-8")).hexdigest()

def _payu_verify_hash(data, salt):
    s = (f"{salt}|{data.get('status')}||||||"
         f"{data.get('udf5','')}|{data.get('udf4','')}|{data.get('udf3','')}|"
         f"{data.get('udf2','')}|{data.get('udf1','')}|{data.get('email','')}|"
         f"{data.get('firstname','')}|{data.get('productinfo','')}|"
         f"{data.get('amount','')}|{data.get('txnid','')}|{data.get('key','')}")
    return hashlib.sha512(s.encode("utf-8")).hexdigest()

# ─────────────────────────────────────────────

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    totals = cart_totals()
    if not totals["items"]:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("books"))

    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip()
        phone   = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        city    = request.form.get("city", "").strip()
        state   = request.form.get("state", "").strip()
        pincode = request.form.get("pincode", "").strip()
        age_raw = request.form.get("age", "").strip()
        profession = request.form.get("profession", "").strip()
        payment = request.form.get("payment_method", "cod")
        app.logger.info(f"[CHECKOUT] payment_method received: '{payment}' | form keys: {list(request.form.keys())}")
        notes   = request.form.get("notes", "").strip()

        if not all([name, phone, address, city, pincode, age_raw, profession]):
            flash("Please fill all required fields.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))

        normalized_phone = valid_indian_phone(phone)
        if not normalized_phone:
            flash("Please enter a valid 10-digit mobile number.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))
        phone = normalized_phone

        if not valid_email(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))

        try:
            age = int(age_raw)
            if age < 1 or age > 120:
                raise ValueError
        except ValueError:
            flash("Please enter a valid age.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))

        if payment == "cod":
            flash("Cash on Delivery is not available. Please choose an online payment method.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))

        if payment == "payu":
            flash("This payment option is temporarily unavailable. Please pay via UPI or Razorpay.", "danger")
            return render_template("checkout.html", **totals,
                                   all_ebooks=all(item_is_ebook(item) for item in totals["items"]))

        # Ebook-only orders have no shipping
        all_ebooks = all(item_is_ebook(item) for item in totals["items"])
        if all_ebooks:
            shipping_charge = 0
        else:
            # Calculate Delhivery shipping rate for this pincode
            from delhivery import get_shipping_rate
            weight_grams = max(
                int(sum(item["qty"] * item_weight_kg(item) for item in totals["items"]) * 1000),
                500
            )
            delhivery_rate, _, _ = get_shipping_rate(pincode, weight_grams)
            shipping_charge = delhivery_rate if delhivery_rate is not None else totals["shipping"]
        subtotal    = totals["subtotal"]
        discount    = totals["discount"]
        total_amount = max(0, subtotal + shipping_charge - discount)

        # Link to customer account if logged in
        cust_id = session.get("customer_id")

        # Create order
        order = Order(
            order_number    = generate_order_number(),
            customer_name   = name,
            customer_email  = email,
            customer_phone  = phone,
            address         = address,
            city            = city,
            state           = state,
            pincode         = pincode,
            age             = age,
            profession      = profession or None,
            subtotal        = subtotal,
            shipping_charge = shipping_charge,
            discount_amount = discount,
            total_amount    = total_amount,
            payment_method  = payment,
            coupon_code     = session.get("coupon_code"),
            notes           = notes,
            payment_status  = "pending",
            order_status    = "placed",
            customer_id     = cust_id,
        )
        db.session.add(order)
        db.session.flush()  # get order.id

        for cart_item in totals["items"]:
            if cart_item["is_combo"]:
                combo = cart_item["combo"]
                # Header row — what the customer actually bought and paid for.
                db.session.add(OrderItem(
                    order_id   = order.id,
                    book_id    = None,
                    book_title = combo.name,
                    quantity   = cart_item["qty"],
                    price      = combo.selling_price,
                    combo_id   = combo.id,
                    is_combo_component = False,
                ))
                # Component rows — zero-priced, exist only so the normal
                # per-book stock deduction at ship time also covers combos.
                for ci in combo.combo_items:
                    if not ci.book:
                        continue
                    db.session.add(OrderItem(
                        order_id   = order.id,
                        book_id    = ci.book.id,
                        book_title = ci.book.title,
                        quantity   = ci.quantity * cart_item["qty"],
                        price      = 0,
                        combo_id   = combo.id,
                        is_combo_component = True,
                    ))
            else:
                oi = OrderItem(
                    order_id   = order.id,
                    book_id    = cart_item["book"].id,
                    book_title = cart_item["book"].title,
                    quantity   = cart_item["qty"],
                    price      = cart_item["book"].price,
                )
                db.session.add(oi)
            # Stock is deducted at ship time (deduct_order_stock), not at order
            # creation — an unpaid/abandoned order must never reduce stock.

        # Update coupon usage
        if order.coupon_code:
            coupon = Coupon.query.filter_by(code=order.coupon_code).first()
            if coupon:
                coupon.used_count += 1

        # Update customer tier and save latest delivery address
        if cust_id:
            cust = Customer.query.get(cust_id)
            if cust:
                cust.update_tier()
                cust.saved_address = address
                cust.saved_city    = city
                cust.saved_state   = state
                cust.saved_pincode = pincode

        db.session.commit()
        _books = ", ".join(
            (ci["combo"].name if ci["is_combo"] else ci["book"].title) for ci in totals["items"]
        )
        notify_admin_whatsapp(
            f"🛒 New Order Placed!\n"
            f"Order: {order.order_number}\n"
            f"Customer: {order.customer_name} | {order.customer_phone}\n"
            f"Amount: ₹{order.total_amount:.0f} | {order.payment_method.upper()}\n"
            f"Books: {_books}"
        )

        # Clear cart & coupon from session
        session.pop("cart", None)
        session.pop("combo_cart", None)
        session.pop("coupon_code", None)
        session.pop("coupon_discount", None)

        if payment == "payu":
            key  = app.config["PAYU_MERCHANT_KEY"]
            salt = app.config["PAYU_MERCHANT_SALT"]
            env  = app.config["PAYU_ENV"]
            amount_str  = f"{order.total_amount:.2f}"
            firstname   = (order.customer_name.split()[0] if order.customer_name else "Customer")[:50]
            email_str   = order.customer_email or ""
            hash_val    = _payu_hash(key, order.order_number, amount_str,
                                     "ISKCON Books", firstname, email_str, salt)
            payu_url    = ("https://test.payu.in/_payment" if env == "test"
                           else "https://secure.payu.in/_payment")
            return render_template("payment_payu.html",
                                   order=order,
                                   payu_url=payu_url,
                                   key=key,
                                   amount=amount_str,
                                   firstname=firstname,
                                   email=email_str,
                                   phone=order.customer_phone or "",
                                   hash_val=hash_val,
                                   surl=url_for("payment_payu_success", _external=True),
                                   furl=url_for("payment_payu_failure", _external=True))

        if payment == "razorpay":
            # Create Razorpay order via direct HTTP (no SDK dependency)
            try:
                import requests as _req
                rp_resp = _req.post(
                    "https://api.razorpay.com/v1/orders",
                    auth=(app.config["RAZORPAY_KEY_ID"], app.config["RAZORPAY_KEY_SECRET"]),
                    json={
                        "amount":   int(order.total_amount * 100),
                        "currency": "INR",
                        "receipt":  order.order_number,
                    },
                    timeout=10,
                )
                rp_resp.raise_for_status()
                rp_order = rp_resp.json()
                order.razorpay_order_id = rp_order["id"]
                db.session.commit()
                return render_template("payment_razorpay.html",
                                       order=order,
                                       rp_order=rp_order,
                                       key_id=app.config["RAZORPAY_KEY_ID"])
            except Exception as e:
                # Delete child rows first to satisfy FK constraint (PostgreSQL)
                OrderItem.query.filter_by(order_id=order.id).delete()
                db.session.delete(order)
                db.session.commit()
                # Restore cart and stock
                restored_cart, restored_combo_cart = {}, {}
                for item in totals["items"]:
                    if item["is_combo"]:
                        restored_combo_cart[str(item["combo"].id)] = {"qty": item["qty"]}
                    else:
                        key = str(item["book"].id)
                        restored_cart[key] = {"qty": item["qty"], "title": item["book"].title}
                        item["book"].stock += item["qty"]
                db.session.commit()
                session["cart"] = restored_cart
                session["combo_cart"] = restored_combo_cart
                session.modified = True
                flash(f"Payment gateway error: {e}. Please try again or choose Cash on Delivery.", "danger")
                return redirect(url_for("checkout"))

        if payment == "upi":
            return redirect(url_for("payment_upi_qr", order_number=order.order_number))

        flash(f"Order #{order.order_number} placed successfully! 🎉", "success")
        return redirect(url_for("order_success", order_number=order.order_number))

    cust = get_current_customer()
    prefill = None
    if cust:
        if cust.saved_address:
            prefill = cust
        else:
            # No saved address yet — pull from most recent linked orders
            from types import SimpleNamespace
            last_addr = cust.orders.filter(
                Order.address.isnot(None)
            ).order_by(Order.created_at.desc()).first()

            if last_addr:
                # State may be empty on old orders — find the most recent one that has it
                last_state = cust.orders.filter(
                    Order.state.isnot(None), Order.state != ''
                ).order_by(Order.created_at.desc()).first()

                prefill = SimpleNamespace(
                    name          = cust.name,
                    email         = cust.email,
                    phone         = cust.phone,
                    saved_address = last_addr.address,
                    saved_city    = last_addr.city    or '',
                    saved_state   = (last_state.state if last_state else '') ,
                    saved_pincode = last_addr.pincode or '',
                )
            else:
                prefill = cust

    return render_template("checkout.html", **totals,
                           razorpay_key=app.config["RAZORPAY_KEY_ID"],
                           prefill=prefill,
                           all_ebooks=all(item_is_ebook(item) for item in totals["items"]))


@app.route("/donate/<int:book_id>", methods=["GET", "POST"])
def donate_book(book_id):
    book = Book.query.get_or_404(book_id)
    if book.deleted:
        abort(404)

    if request.method == "GET":
        return render_template("donate.html", book=book)

    donor_name    = request.form.get("donor_name", "").strip()
    donor_phone   = request.form.get("donor_phone", "").strip()
    donor_email   = request.form.get("donor_email", "").strip()
    donor_message = request.form.get("donor_message", "").strip()
    donation_type  = "person"
    payment_method = request.form.get("payment_method", "upi")
    try:
        quantity = max(1, int(request.form.get("quantity") or 1))
    except ValueError:
        quantity = 1

    donation_recipient         = request.form.get("donation_recipient", "").strip()
    donation_recipient_address = request.form.get("donation_recipient_address", "").strip()

    if not donor_name or not donor_phone:
        flash("Please fill your name and phone number.", "danger")
        return render_template("donate.html", book=book)

    normalized_donor_phone = valid_indian_phone(donor_phone)
    if not normalized_donor_phone:
        flash("Please enter a valid 10-digit mobile number.", "danger")
        return render_template("donate.html", book=book)
    donor_phone = normalized_donor_phone

    if not valid_email(donor_email):
        flash("Please enter a valid email address.", "danger")
        return render_template("donate.html", book=book)

    if not donation_recipient or not donation_recipient_address:
        flash("Please fill the recipient's name and delivery address.", "danger")
        return render_template("donate.html", book=book)

    total_amount = round(book.price * quantity, 2)
    order_address = donation_recipient_address

    order = Order(
        order_number              = generate_order_number(),
        customer_name             = donor_name,
        customer_email            = donor_email or None,
        customer_phone            = donor_phone,
        address                   = order_address,
        city                      = "—",
        state                     = "",
        pincode                   = "000000",
        subtotal                  = total_amount,
        shipping_charge           = 0,
        discount_amount           = 0,
        total_amount              = total_amount,
        payment_method            = payment_method,
        payment_status            = "pending",
        order_status              = "placed",
        notes                     = donor_message or None,
        is_donation               = True,
        donation_type             = donation_type,
        donation_recipient        = donation_recipient or None,
        donation_recipient_address= donation_recipient_address or None,
        donor_message             = donor_message or None,
    )
    db.session.add(order)
    db.session.flush()

    oi = OrderItem(
        order_id   = order.id,
        book_id    = book.id,
        book_title = book.title,
        quantity   = quantity,
        price      = book.price,
    )
    db.session.add(oi)
    db.session.commit()
    notify_admin_whatsapp(
        f"🎁 New Book Gift Order!\n"
        f"Sender: {donor_name} | {donor_phone}\n"
        f"Book: {book.title} × {quantity}\n"
        f"Amount: ₹{total_amount:.0f} | {payment_method.upper()}\n"
        f"Recipient: {donation_recipient}"
    )

    if payment_method == "upi":
        return redirect(url_for("payment_upi_qr", order_number=order.order_number))

    if payment_method == "payu":
        key         = app.config["PAYU_MERCHANT_KEY"]
        salt        = app.config["PAYU_MERCHANT_SALT"]
        env         = app.config["PAYU_ENV"]
        amount_str  = f"{order.total_amount:.2f}"
        firstname   = (order.customer_name.split()[0] if order.customer_name else "Donor")[:50]
        email_str   = order.customer_email or ""
        hash_val    = _payu_hash(key, order.order_number, amount_str,
                                 "Iskconbooks Gift Order", firstname, email_str, salt)
        payu_url    = ("https://test.payu.in/_payment" if env == "test"
                       else "https://secure.payu.in/_payment")
        return render_template("payment_payu.html",
                               order=order,
                               payu_url=payu_url,
                               payu_key=key,
                               amount_str=amount_str,
                               firstname=firstname,
                               email_str=email_str,
                               hash_val=hash_val,
                               surl=url_for("payment_payu_success", _external=True),
                               furl=url_for("payment_payu_failure", _external=True))

    # Razorpay
    try:
        import requests as _req
        rp_resp = _req.post(
            "https://api.razorpay.com/v1/orders",
            auth=(app.config["RAZORPAY_KEY_ID"], app.config["RAZORPAY_KEY_SECRET"]),
            json={
                "amount":   int(total_amount * 100),
                "currency": "INR",
                "receipt":  order.order_number,
            },
            timeout=10,
        )
        rp_resp.raise_for_status()
        rp_order = rp_resp.json()
        order.razorpay_order_id = rp_order["id"]
        db.session.commit()
        return render_template("payment_razorpay.html",
                               order=order,
                               rp_order=rp_order,
                               key_id=app.config["RAZORPAY_KEY_ID"])
    except Exception as e:
        OrderItem.query.filter_by(order_id=order.id).delete()
        db.session.delete(order)
        db.session.commit()
        book.stock += quantity
        db.session.commit()
        flash(f"Payment gateway error: {e}. Please try again.", "danger")
        return render_template("donate.html", book=book)


# ─────────────────────────────────────────────
# GITA DAN YAGNA (public)
# ─────────────────────────────────────────────

def _yagna_int(name, default=0, hi=YAGNA_MAX_QTY):
    try:
        return max(0, min(hi, int(request.form.get(name) or default)))
    except ValueError:
        return default


def _yagna_wall(limit=30):
    rows = (GitaYagnaDonation.query.filter_by(show_name=True)
            .order_by(GitaYagnaDonation.donated_on.desc()).limit(200).all())
    return [r for r in rows if r.counted][:limit]


@app.route("/gita-dan-yagna", methods=["GET", "POST"])
def gita_dan_yagna():
    cfg = yagna_config()
    stats = yagna_stats(cfg)

    def render(**extra):
        return render_template("gita_yagna.html", cfg=cfg, stats=stats,
                               wall=_yagna_wall(), langs=YAGNA_LANGS, cover=yagna_cover_path(),
                               invite_min=YAGNA_INVITE_MIN, form=extra.pop("form", {}), **extra)

    if request.method == "GET" or not cfg["enabled"]:
        return render()

    f = request.form
    donor_name = f.get("donor_name", "").strip()
    donor_phone = f.get("donor_phone", "").strip()
    donor_email = f.get("donor_email", "").strip()
    profession = f.get("profession", "").strip()[:100]
    area = f.get("area", "").strip()[:200]
    dedication = f.get("dedication", "").strip()[:250]
    language = f.get("language", "Hindi")
    payment_method = f.get("payment_method", "upi")
    distribution = f.get("distribution", "local")
    if distribution not in ("local", "courier"):
        distribution = "local"
    r_name = f.get("recipient_name", "").strip()[:200]
    r_phone = f.get("recipient_phone", "").strip()
    r_address = f.get("recipient_address", "").strip()
    r_city = f.get("recipient_city", "").strip()[:100]
    r_state = f.get("recipient_state", "").strip()[:100]
    r_pin = f.get("recipient_pincode", "").strip()
    quantity = _yagna_int("quantity", 0)
    students, village, others = (_yagna_int("students_qty"), _yagna_int("village_qty"),
                                 _yagna_int("others_qty"))
    arati = f.get("arati") == "on"
    yajna = f.get("yajna") == "on"
    show_name = f.get("show_name") == "on"

    def fail(msg):
        flash(msg, "danger")
        return render(form=f)

    if language not in YAGNA_LANGS:
        return fail("Please choose the language of the Gitas.")
    if quantity < 1:
        return fail("Please choose how many Gitas you want to donate.")
    if not donor_name:
        return fail("Please enter your name.")
    phone = valid_indian_phone(donor_phone)
    if not phone:
        return fail("Please enter a valid 10-digit mobile number.")
    if not valid_email(donor_email):
        return fail("Please enter a valid email address.")
    if students + village + others > quantity:
        return fail("The Gitas split for Students / Village residents / Others "
                    "is more than the total number of Gitas.")
    if payment_method not in ("upi", "razorpay"):
        payment_method = "upi"

    courier_charge = 0.0
    if distribution == "courier":
        if not r_name or not r_address:
            return fail("For online (courier) distribution please enter the recipient's name and full address.")
        if not _re.fullmatch(r"\d{6}", r_pin):
            return fail("Please enter the recipient's 6-digit pincode.")
        if r_phone:
            r_phone = valid_indian_phone(r_phone)
            if not r_phone:
                return fail("Please enter a valid 10-digit mobile number for the recipient (or leave it empty).")
        courier_charge = yagna_courier_charge(r_pin, quantity, cfg)

    unit = cfg["prices"][language]
    gitas_amount = round(unit * quantity, 2)
    courier_pay = courier_charge          # always paid by the donor (0 for local distribution)
    total_amount = round(gitas_amount + courier_pay, 2)
    sankalpa = ", ".join(x for x in (
        f"Students {students}" if students else "",
        f"Village residents {village}" if village else "",
        f"Others {others}" if others else "") if x) or "Temple decides"
    participation = ", ".join(x for x in (
        "Arati on Gita Jayanti" if arati else "", "Gita Yajna" if yajna else "") if x)

    order = Order(
        order_number              = generate_order_number(),
        customer_name             = donor_name,
        customer_email            = donor_email or None,
        customer_phone            = phone,
        address                   = (r_address if distribution == "courier"
                                     else "Gita Dan Yagna — distributed by ISKCON Ahmedabad"),
        city                      = (r_city or "—") if distribution == "courier" else (area or "—"),
        state                     = r_state if distribution == "courier" else "",
        pincode                   = r_pin if distribution == "courier" else "000000",
        subtotal                  = gitas_amount,
        shipping_charge           = courier_pay,
        discount_amount           = 0,
        total_amount              = total_amount,
        payment_method            = payment_method,
        payment_status            = "pending",
        order_status              = "placed",
        notes                     = f"Gita Dan Yagna | Sankalpa: {sankalpa}"
                                    + (f" | Participation: {participation}" if participation else "")
                                    + (" | Distribution: Local (temple)" if distribution == "local"
                                       else f" | Distribution: Courier — courier charge paid by donor "
                                            f"(₹{courier_charge:.0f})"),
        is_donation               = True,
        donation_type             = "yagna",
        donation_recipient        = (r_name if distribution == "courier" else sankalpa)[:200],
        donation_recipient_address= r_address if distribution == "courier" else None,
        donor_message             = dedication or None,
        profession                = profession or None,
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(OrderItem(
        order_id=order.id, book_id=None,
        book_title=f"Gita Dan Yagna — Bhagavad Gita As It Is ({language})",
        quantity=quantity, price=unit))
    db.session.add(GitaYagnaDonation(
        order_id=order.id, source="online", donor_name=donor_name, donor_phone=phone,
        donor_email=donor_email or None, profession=profession or None, area=area or None,
        language=language, quantity=quantity, amount=gitas_amount,
        distribution=distribution,
        courier_charge=courier_charge,
        parcel_kg=round(quantity * cfg["weight_kg"], 2) if distribution == "courier" else None,
        recipient_name=r_name or None, recipient_phone=r_phone or None,
        recipient_address=r_address or None, recipient_city=r_city or None,
        recipient_state=r_state or None, recipient_pincode=r_pin or None,
        students_qty=students, village_qty=village, others_qty=others,
        arati=arati, yajna=yajna, dedication=dedication or None, show_name=show_name,
        payment_mode=payment_method))
    db.session.commit()
    donation_total = quantity + sum(
        r.quantity or 0 for r in GitaYagnaDonation.query.filter(
            GitaYagnaDonation.donor_phone == phone, GitaYagnaDonation.order_id != order.id).all() if r.counted)
    notify_admin_whatsapp(
        f"🙏 New Gita Dan Yagna Donation!\n"
        f"Donor: {donor_name} | {phone}\n"
        f"Gitas: {quantity} × {language} = ₹{total_amount:.0f} | {payment_method.upper()}\n"
        f"Sankalpa: {sankalpa}\n"
        + ("Distribution: Local (temple)" if distribution == "local" else
           f"Distribution: COURIER to {r_name}, {r_pin} — courier ₹{courier_charge:.0f} (paid by donor)")
        + (f"\n🎟 Special invitation card eligible (donor total {donation_total} Gitas)"
           if donation_total >= YAGNA_INVITE_MIN else ""))

    if payment_method == "upi":
        return redirect(url_for("payment_upi_qr", order_number=order.order_number))

    try:
        import requests as _req
        rp_resp = _req.post(
            "https://api.razorpay.com/v1/orders",
            auth=(app.config["RAZORPAY_KEY_ID"], app.config["RAZORPAY_KEY_SECRET"]),
            json={"amount": int(round(total_amount * 100)), "currency": "INR",
                  "receipt": order.order_number},
            timeout=10)
        rp_resp.raise_for_status()
        rp_order = rp_resp.json()
        order.razorpay_order_id = rp_order["id"]
        db.session.commit()
        return render_template("payment_razorpay.html", order=order, rp_order=rp_order,
                               key_id=app.config["RAZORPAY_KEY_ID"])
    except Exception as e:
        GitaYagnaDonation.query.filter_by(order_id=order.id).delete()
        OrderItem.query.filter_by(order_id=order.id).delete()
        db.session.delete(order)
        db.session.commit()
        return fail(f"Payment gateway error: {e}. Please try again.")


@app.route("/api/gita-dan-yagna/courier-rate")
def api_yagna_courier_rate():
    pin = request.args.get("pincode", "").strip()
    qty = max(1, min(YAGNA_MAX_QTY, request.args.get("qty", 1, type=int) or 1))
    if not _re.fullmatch(r"\d{6}", pin):
        return jsonify({"ok": False})
    return jsonify({"ok": True, "charge": yagna_courier_charge(pin, qty)})


@app.route("/gita-dan-yagna/thanks/<order_number>")
def gita_yagna_thanks(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    donation = order.yagna_donation
    if not donation:
        abort(404)
    return render_template("gita_yagna_thanks.html", order=order, d=donation,
                           cfg=yagna_config(), invite_min=YAGNA_INVITE_MIN)


@app.route("/gita-dan-yagna/certificate/<order_number>")
def gita_yagna_certificate(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    donation = order.yagna_donation
    if not donation or not donation.counted:
        abort(404)
    return render_template("gita_yagna_certificate.html", d=donation, cfg=yagna_config(),
                           cert_no=order.order_number)


@app.route("/payment/verify", methods=["POST"])
def payment_verify():
    data = request.get_json() or request.form.to_dict()
    order_number = data.get("order_number") or data.get("receipt")
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({"success": False, "error": "Order not found"}), 404

    # Verify Razorpay signature
    rp_order_id   = data.get("razorpay_order_id")
    rp_payment_id = data.get("razorpay_payment_id")
    rp_signature  = data.get("razorpay_signature")

    try:
        msg = f"{rp_order_id}|{rp_payment_id}".encode()
        expected = hmac.new(app.config["RAZORPAY_KEY_SECRET"].encode(), msg, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, rp_signature):
            order.payment_status    = "paid"
            order.razorpay_payment_id = rp_payment_id
            order.order_status      = "confirmed"
            db.session.commit()
            send_order_confirmation(order)
            books = ", ".join(i.book_title for i in order.items)
            notify_admin_whatsapp(
                f"🔔 Payment Received!\n"
                f"Order: {order.order_number}\n"
                f"Customer: {order.customer_name} | {order.customer_phone}\n"
                f"Amount: ₹{order.total_amount:.0f} | Razorpay\n"
                f"Payment ID: {rp_payment_id}\n"
                f"Books: {books}"
            )
            return jsonify({"success": True, "redirect": url_for("order_success", order_number=order.order_number)})
    except Exception:
        pass

    order.payment_status = "failed"
    db.session.commit()
    return jsonify({"success": False, "redirect": url_for("payment_failed", order_number=order.order_number)})


@app.route("/order/success/<order_number>")
def order_success(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if order.donation_type == "yagna":
        return redirect(url_for("gita_yagna_thanks", order_number=order.order_number))
    return render_template("payment_success.html", order=order)


@app.route("/payment/payu/success", methods=["POST"])
def payment_payu_success():
    data = request.form.to_dict()
    salt = app.config["PAYU_MERCHANT_SALT"]
    txnid = data.get("txnid", "")
    order = Order.query.filter_by(order_number=txnid).first()
    if order:
        expected = _payu_verify_hash(data, salt)
        received = data.get("hash", "")
        if expected == received and data.get("status") == "success":
            order.payment_status = "paid"
            order.order_status = "confirmed"
            order.razorpay_payment_id = data.get("mihpayid", "")
            db.session.commit()
            send_order_confirmation(order)
            books = ", ".join(i.book_title for i in order.items)
            notify_admin_whatsapp(
                f"🔔 Payment Received!\n"
                f"Order: {order.order_number}\n"
                f"Customer: {order.customer_name} | {order.customer_phone}\n"
                f"Amount: ₹{order.total_amount:.0f} | PayU\n"
                f"Payment ID: {data.get('mihpayid', '')}\n"
                f"Books: {books}"
            )
            flash("Payment successful! 🎉 Hare Krishna!", "success")
            return redirect(url_for("order_success", order_number=order.order_number))
        else:
            order.payment_status = "failed"
            db.session.commit()
    flash("Payment verification failed. Please contact support.", "danger")
    return redirect(url_for("order_track"))


@app.route("/payment/payu/failure", methods=["POST"])
def payment_payu_failure():
    data = request.form.to_dict()
    txnid = data.get("txnid", "")
    order = Order.query.filter_by(order_number=txnid).first()
    if order:
        order.payment_status = "failed"
        db.session.commit()
    flash("Payment failed or cancelled. Please try again.", "danger")
    return redirect(url_for("order_track"))


@app.route("/payment/payu/webhook", methods=["POST"])
def payment_payu_webhook():
    """PayU S2S server-to-server webhook — fires independently of browser redirect."""
    data = request.form.to_dict()
    salt = app.config["PAYU_MERCHANT_SALT"]
    txnid = data.get("txnid", "")
    order = Order.query.filter_by(order_number=txnid).first()
    if order:
        expected = _payu_verify_hash(data, salt)
        received = data.get("hash", "")
        if expected == received:
            newly_confirmed = False
            if data.get("status") == "success" and order.payment_status != "paid":
                order.payment_status = "paid"
                order.order_status = "confirmed"
                order.razorpay_payment_id = data.get("mihpayid", "")
                newly_confirmed = True
            elif data.get("status") != "success" and order.payment_status == "pending":
                order.payment_status = "failed"
            db.session.commit()
            if newly_confirmed:
                send_order_confirmation(order)
    return "OK", 200


@app.route("/whatsapp/log", methods=["POST"])
def whatsapp_log():
    data       = request.get_json() or request.form.to_dict()
    name       = (data.get("name") or "").strip()
    phone      = (data.get("phone") or "").strip()
    email      = (data.get("email") or "").strip()
    book_id    = data.get("book_id")
    book_title = (data.get("book_title") or "").strip()
    address    = (data.get("address") or "").strip()
    city       = (data.get("city") or "").strip()
    state      = (data.get("state") or "").strip()
    pincode    = (data.get("pincode") or "").strip()
    profession = (data.get("profession") or "").strip()
    age        = data.get("age")
    try:
        age = int(age) if age else None
    except (TypeError, ValueError):
        age = None
    shipping_rate = data.get("shipping_rate")
    try:
        shipping_rate = float(shipping_rate) if shipping_rate else None
    except (TypeError, ValueError):
        shipping_rate = None
    if name or phone:
        db.session.add(WhatsAppInquiry(
            book_id       = int(book_id) if book_id else None,
            book_title    = book_title,
            customer_name = name,
            customer_phone= phone,
            customer_email= email if valid_email(email) else None,
            age           = age,
            profession    = profession or None,
            address       = address or None,
            city          = city or None,
            state         = state or None,
            pincode       = pincode or None,
            shipping_rate = shipping_rate,
        ))
        db.session.commit()
        location = f" | {city}, {pincode}" if city or pincode else ""
        notify_admin_whatsapp(
            f"📱 New WhatsApp Enquiry!\n"
            f"Customer: {name or '—'} | {phone or '—'}{location}\n"
            f"Book: {book_title or 'General Enquiry'}"
        )
    return jsonify({"success": True})


@app.route("/payment/upi-qr/<order_number>")
def payment_upi_qr(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    upi_id   = app.config.get("UPI_ID", "")
    upi_name = app.config.get("UPI_NAME", "ISKCON Book Store")
    amount   = f"{order.total_amount:.2f}"
    upi_link = (
        f"upi://pay?pa={upi_id}&pn={upi_name.replace(' ', '%20')}"
        f"&am={amount}&tn={order.order_number}&cu=INR"
    )
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=8, border=4)
        qr.add_data(upi_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a1a", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        qr_b64 = None
    return render_template("payment_upi_qr.html",
                           order=order, qr_b64=qr_b64,
                           upi_id=upi_id, upi_name=upi_name, amount=amount)


@app.route("/order/upi-confirm/<order_number>", methods=["POST"])
def upi_confirm(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if order.payment_method != "upi":
        abort(400)
    utr = request.form.get("utr", "").strip()
    if utr:
        try:
            # Use raw SQL in case column was just added and SQLAlchemy mapper cache is stale
            db.session.execute(
                db.text("UPDATE orders SET upi_transaction_id = :utr WHERE id = :oid"),
                {"utr": utr, "oid": order.id}
            )
            db.session.commit()
            flash("Transaction ID submitted! We will verify and confirm your order shortly.", "success")
            books = ", ".join(i.book_title for i in order.items)
            notify_admin_whatsapp(
                f"💰 UPI Payment Pending Verification\n"
                f"Order: {order.order_number}\n"
                f"Customer: {order.customer_name} | {order.customer_phone}\n"
                f"Amount: ₹{order.total_amount:.0f} | UPI\n"
                f"UTR: {utr}\n"
                f"Books: {books}\n"
                f"⚠️ Please verify UTR and mark Paid."
            )
            send_order_placed(order, utr=utr)
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] upi_confirm save failed: {e}")
            flash("Could not save Transaction ID. Please send it via WhatsApp.", "warning")
    return redirect(url_for("order_success", order_number=order_number))


@app.route("/ebook/download/<order_number>/<int:book_id>", methods=["GET", "POST"])
def ebook_download(order_number, book_id):
    order = Order.query.filter_by(order_number=order_number).first_or_404()

    # Access control: COD denied; every other method requires admin-confirmed payment
    if order.payment_method == "cod":
        abort(403)
    if order.payment_status != "paid":
        abort(403)

    # Verify book is actually in the order
    item = next((i for i in order.items if i.book_id == book_id), None)
    if not item:
        abort(404)

    book = Book.query.get_or_404(book_id)
    if not book.is_ebook or not book.ebook_file:
        abort(404)

    ebook_path = os.path.join(app.config["EBOOK_FOLDER"], book.ebook_file)
    if not os.path.exists(ebook_path):
        flash("eBook file not found. Please contact support.", "warning")
        return redirect(url_for("order_success", order_number=order_number))

    # Single-use link: once downloaded, this URL is dead. Admin can reset it
    # from the order detail page if a customer genuinely needs it again.
    if item.ebook_downloaded_at is not None:
        flash(
            "This eBook download link has already been used and is now inactive "
            "(each link works only once). Please contact us via WhatsApp if you "
            "need it resent.",
            "warning"
        )
        return redirect(url_for("order_success", order_number=order_number))

    # GET only shows a landing page — it must never trigger the actual file
    # transfer, because email providers and corporate mail filters (Gmail,
    # Outlook Safe Links, etc.) automatically fetch every link in an email to
    # scan it, which would otherwise burn the single-use link before the
    # customer ever clicks it. The real download only starts on the POST
    # below, which a scanner won't submit.
    if request.method == "GET":
        return render_template("ebook_landing.html", order=order, book=book)

    ext = book.ebook_file.rsplit(".", 1)[1]
    file_size = os.path.getsize(ebook_path)
    mimetype = _EBOOK_MIMETYPES.get(ext.lower(), "application/octet-stream")
    download_name = safe_download_filename(f"{book.title}.{ext}")

    # Capture primitives only — `item`/`order`/`book` are detached (and their
    # session torn down) by the time this request's context is popped, which
    # happens before the WSGI server iterates a streaming response body.
    item_id, order_id = item.id, order.id
    order_number_, customer_name, customer_phone, book_title = (
        order.order_number, order.customer_name, order.customer_phone, book.title
    )

    def generate():
        bytes_sent = 0
        try:
            with open(ebook_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    bytes_sent += len(chunk)
                    yield chunk
        finally:
            # Only mark the link "used" once the whole file was actually
            # handed off. A dropped connection (or a link-preview bot that
            # aborts early) raises GeneratorExit here with bytes_sent short
            # of file_size, so the single-use link stays alive.
            if bytes_sent >= file_size:
                with app.app_context():
                    try:
                        fresh_item = OrderItem.query.get(item_id)
                        if fresh_item and fresh_item.ebook_downloaded_at is None:
                            fresh_item.ebook_downloaded_at = datetime.utcnow()
                            fresh_order = Order.query.get(order_id)
                            if fresh_order and fresh_order.order_status in ("placed", "confirmed") and all(
                                i.book and i.book.is_ebook and i.ebook_downloaded_at is not None
                                for i in fresh_order.items
                            ):
                                fresh_order.order_status = "delivered"
                            db.session.commit()
                            notify_admin_whatsapp(
                                f"📥 eBook Downloaded!\n"
                                f"Order: {order_number_}\n"
                                f"Customer: {customer_name} | {customer_phone}\n"
                                f"Book: {book_title}"
                            )
                    except Exception:
                        db.session.rollback()
                        app.logger.exception("ebook_download: failed to record completed download")

    response = Response(generate(), mimetype=mimetype)
    response.headers.set("Content-Disposition", "attachment", filename=download_name)
    response.headers["Content-Length"] = str(file_size)
    return response


@app.route("/admin/orders/<int:order_id>/ebook/<int:item_id>/download")
@admin_required
def admin_ebook_download(order_id, item_id):
    """Admin-only file access for verification — does NOT consume the customer's single-use link."""
    order = Order.query.get_or_404(order_id)
    item = next((i for i in order.items if i.id == item_id), None)
    if not item or not item.book or not item.book.is_ebook or not item.book.ebook_file:
        abort(404)
    book = item.book
    ext = book.ebook_file.rsplit(".", 1)[1]
    return send_from_directory(
        app.config["EBOOK_FOLDER"],
        book.ebook_file,
        as_attachment=True,
        download_name=safe_download_filename(f"{book.title}.{ext}")
    )


@app.route("/order/failed/<order_number>")
def payment_failed(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return render_template("payment_failed.html", order=order)


@app.route("/order/track", methods=["GET", "POST"])
def order_track():
    order = None
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        # Normalise phone: try both raw input and without +91 / 91 prefix
        phone_variants = [query]
        digits = query.lstrip("+")
        if digits.startswith("91") and len(digits) == 12:
            phone_variants.append(digits[2:])       # strip 91 → 10-digit
        elif len(digits) == 10:
            phone_variants.append("91" + digits)    # add 91
            phone_variants.append("+91" + digits)   # add +91
        order = Order.query.filter(
            or_(Order.order_number == query,
                Order.customer_phone.in_(phone_variants))
        ).order_by(Order.created_at.desc()).first()
        if not order:
            flash("No order found with that order number or phone.", "warning")
    return render_template("order_tracking.html", order=order)


# ─────────────────────────────────────────────
# MAGAZINE ROUTES
# ─────────────────────────────────────────────

@app.route("/magazine")
def magazine():
    magazines = Magazine.query.filter_by(active=True).order_by(Magazine.published_at.desc()).all()
    if len(magazines) == 1:
        return redirect(url_for("magazine_detail", mag_id=magazines[0].id))
    return render_template("magazine_list.html", magazines=magazines)


@app.route("/magazine/<int:mag_id>")
def magazine_detail(mag_id):
    mag          = Magazine.query.get_or_404(mag_id)
    customer     = get_current_customer()
    # Only real purchase/subscription grants access — no admin override on customer page
    has_access   = get_magazine_access(customer.id if customer else None, mag_id)
    monthly_price = float(Setting.get("mag_monthly_price", "49"))
    yearly_price  = float(Setting.get("mag_yearly_price",  "399"))
    active_sub = None
    if customer:
        now = datetime.utcnow()
        active_sub = MagazineSubscription.query.filter_by(
            customer_id=customer.id, status="active"
        ).filter(MagazineSubscription.end_date > now).first()
    return render_template(
        "magazine.html",
        mag=mag,
        has_access=has_access,
        monthly_price=monthly_price,
        yearly_price=yearly_price,
        active_sub=active_sub,
        razorpay_key=app.config["RAZORPAY_KEY_ID"],
    )


@app.route("/magazine/checkout", methods=["POST"])
def magazine_checkout():
    """Unified magazine checkout — handles buy (single issue) or subscribe (monthly/yearly)
    across all three payment methods: UPI, PayU, Razorpay."""
    action         = request.form.get("action")        # 'buy' | 'subscribe'
    mag_id         = request.form.get("mag_id", type=int)
    plan           = request.form.get("plan")          # 'monthly' | 'yearly'
    payment_method = request.form.get("payment_method", "razorpay")

    customer = get_current_customer()
    if not customer:
        flash("Please log in to complete this purchase.", "warning")
        return redirect(url_for("customer_login", next=request.referrer or url_for("magazine")))

    monthly_price = float(Setting.get("mag_monthly_price", "49"))
    yearly_price  = float(Setting.get("mag_yearly_price",  "399"))

    if action == "buy":
        mag = Magazine.query.get_or_404(mag_id)
        if mag.is_free or get_magazine_access(customer.id, mag_id):
            flash("You already have access to this magazine.", "info")
            return redirect(url_for("magazine_detail", mag_id=mag_id))
        amount      = mag.single_price
        description = f"{mag.title} — {mag.issue_label}"
        txn_prefix  = f"MAGBUY{mag_id}"
        back_url    = url_for("magazine_detail", mag_id=mag_id)
    elif action == "subscribe":
        amount      = monthly_price if plan == "monthly" else yearly_price
        label       = "Monthly" if plan == "monthly" else "Yearly"
        description = f"Magazine {label} Subscription"
        txn_prefix  = f"MAGSUB{plan.upper()[:1]}"
        back_url    = url_for("magazine")
        mag_id      = None
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("magazine"))

    txn_ref = f"{txn_prefix}-C{customer.id}-{uuid.uuid4().hex[:6].upper()}"

    # Persist pending payment so server callbacks (PayU) can resolve it
    pending = PendingMagPayment(
        txn_ref        = txn_ref,
        payment_type   = action,
        mag_id         = mag_id,
        plan           = plan,
        customer_id    = customer.id,
        amount         = amount,
        payment_method = payment_method,
        status         = "pending",
    )
    db.session.add(pending)
    db.session.commit()

    # ── Razorpay ──────────────────────────────────────────────
    if payment_method == "razorpay":
        try:
            rp_order = _create_razorpay_order(amount, txn_ref, {"type": action})
            pending.razorpay_order_id = rp_order["id"]
            db.session.commit()
            return render_template(
                "payment_razorpay_simple.html",
                razorpay_key      = app.config["RAZORPAY_KEY_ID"],
                razorpay_order_id = rp_order["id"],
                amount            = int(amount * 100),
                customer_name     = customer.name,
                customer_email    = customer.email,
                customer_phone    = customer.phone,
                order_number      = txn_ref,
                callback_url      = url_for("magazine_razorpay_verify", _external=True),
                description       = description,
            )
        except Exception:
            pending.status = "failed"
            db.session.commit()
            flash("Payment gateway error. Please try again.", "danger")
            return redirect(back_url)

    # ── PayU ──────────────────────────────────────────────────
    if payment_method == "payu":
        key       = app.config["PAYU_MERCHANT_KEY"]
        salt      = app.config["PAYU_MERCHANT_SALT"]
        env       = app.config["PAYU_ENV"]
        amt_str   = f"{amount:.2f}"
        firstname = (customer.name.split()[0] if customer.name else "Customer")[:50]
        email_str = customer.email or ""
        hash_val  = _payu_hash(key, txn_ref, amt_str, "ISKCON Magazine",
                               firstname, email_str, salt)
        payu_url  = ("https://test.payu.in/_payment" if env == "test"
                     else "https://secure.payu.in/_payment")
        return render_template(
            "payment_payu.html",
            order        = type("O", (), {
                "order_number":   txn_ref,
                "total_amount":   amount,
                "customer_name":  customer.name,
                "customer_phone": customer.phone,
                "customer_email": customer.email,
                "items":          [],
            })(),
            payu_url  = payu_url,
            key       = key,
            amount    = amt_str,
            firstname = firstname,
            email     = email_str,
            phone     = customer.phone or "",
            hash_val  = hash_val,
            surl      = url_for("magazine_payu_success", _external=True),
            furl      = url_for("magazine_payu_failure", _external=True),
        )

    # ── UPI ───────────────────────────────────────────────────
    if payment_method == "upi":
        return redirect(url_for("magazine_upi_qr", txn_ref=txn_ref))

    flash("Unknown payment method.", "danger")
    return redirect(back_url)


@app.route("/magazine/razorpay/verify", methods=["POST"])
def magazine_razorpay_verify():
    data          = request.get_json() or request.form.to_dict()
    rp_order_id   = data.get("razorpay_order_id")
    rp_payment_id = data.get("razorpay_payment_id")
    rp_signature  = data.get("razorpay_signature")

    pending = PendingMagPayment.query.filter_by(
        razorpay_order_id=rp_order_id, status="pending"
    ).first()
    if not pending:
        return jsonify({"success": False, "error": "Payment record not found"}), 400

    try:
        msg      = f"{rp_order_id}|{rp_payment_id}".encode()
        expected = hmac.new(app.config["RAZORPAY_KEY_SECRET"].encode(), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, rp_signature):
            raise ValueError("Signature mismatch")
        redirect_url = _complete_mag_payment(pending, rp_payment_id)
        return jsonify({"success": True, "redirect": redirect_url})
    except Exception:
        pending.status = "failed"
        db.session.commit()
        return jsonify({"success": False, "error": "Verification failed"}), 400


@app.route("/magazine/payu/success", methods=["POST"])
def magazine_payu_success():
    data    = request.form.to_dict()
    salt    = app.config["PAYU_MERCHANT_SALT"]
    txn_ref = data.get("txnid", "")
    pending = PendingMagPayment.query.filter_by(txn_ref=txn_ref).first()
    if pending:
        expected = _payu_verify_hash(data, salt)
        if expected == data.get("hash", "") and data.get("status") == "success":
            redirect_url = _complete_mag_payment(pending, data.get("mihpayid", ""))
            flash("Payment successful! Enjoy the magazine. 🙏", "success")
            return redirect(redirect_url)
        pending.status = "failed"
        db.session.commit()
    flash("Payment verification failed. Please contact support.", "danger")
    return redirect(url_for("magazine"))


@app.route("/magazine/payu/failure", methods=["POST"])
def magazine_payu_failure():
    data    = request.form.to_dict()
    txn_ref = data.get("txnid", "")
    pending = PendingMagPayment.query.filter_by(txn_ref=txn_ref).first()
    if pending:
        pending.status = "failed"
        db.session.commit()
    flash("Payment failed or cancelled. Please try again.", "danger")
    return redirect(url_for("magazine"))


@app.route("/magazine/upi/<txn_ref>")
def magazine_upi_qr(txn_ref):
    pending = PendingMagPayment.query.filter_by(txn_ref=txn_ref).first_or_404()
    if pending.status == "completed":
        flash("Payment already completed!", "success")
        return redirect(_mag_success_redirect(pending))
    upi_id   = app.config.get("UPI_ID", "")
    upi_name = app.config.get("UPI_NAME", "ISKCON Book Store")
    amount   = f"{pending.amount:.2f}"
    upi_link = (f"upi://pay?pa={upi_id}&pn={upi_name.replace(' ', '%20')}"
                f"&am={amount}&tn={txn_ref}&cu=INR")
    qr_b64 = None
    try:
        import qrcode, io as _io
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=8, border=4)
        qr.add_data(upi_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass
    return render_template("magazine_upi.html",
                           pending=pending, upi_id=upi_id, upi_name=upi_name,
                           amount=amount, upi_link=upi_link, qr_b64=qr_b64)


@app.route("/magazine/upi/confirm/<txn_ref>", methods=["POST"])
def magazine_upi_confirm(txn_ref):
    pending = PendingMagPayment.query.filter_by(txn_ref=txn_ref).first_or_404()
    utr = request.form.get("utr", "").strip()
    if utr:
        pending.utr    = utr
        pending.status = "pending_verification"   # admin must manually confirm UPI
        db.session.commit()
        flash("Transaction ID submitted! We'll verify and activate your access shortly. 🙏", "success")
        notify_admin_whatsapp(
            f"📰 Magazine UPI Pending Verification\n"
            f"Ref: {txn_ref}\n"
            f"Amount: ₹{pending.amount:.0f} | UPI\n"
            f"UTR: {utr}\n"
            f"⚠️ Please verify UTR and activate access."
        )
    return redirect(_mag_success_redirect(pending))


def _complete_mag_payment(pending, payment_id):
    """Create MagazinePurchase or MagazineSubscription from a completed PendingMagPayment."""
    if pending.payment_type == "buy":
        db.session.add(MagazinePurchase(
            customer_id         = pending.customer_id,
            magazine_id         = pending.mag_id,
            razorpay_payment_id = payment_id,
            amount_paid         = pending.amount,
        ))
    else:
        days = 30 if pending.plan == "monthly" else 365
        db.session.add(MagazineSubscription(
            customer_id         = pending.customer_id,
            plan                = pending.plan,
            end_date            = datetime.utcnow() + timedelta(days=days),
            razorpay_payment_id = payment_id,
            amount_paid         = pending.amount,
            status              = "active",
        ))
    pending.status = "completed"
    db.session.commit()
    _type = "Issue Purchase" if pending.payment_type == "buy" else f"{(pending.plan or '').title()} Subscription"
    notify_admin_whatsapp(
        f"📰 Magazine Payment Confirmed!\n"
        f"Customer: {pending.customer.name} | {pending.customer.phone}\n"
        f"Amount: ₹{pending.amount:.0f} | {pending.payment_method.upper()}\n"
        f"Type: {_type}\n"
        f"Payment ID: {payment_id}"
    )
    return _mag_success_redirect(pending)


def _mag_success_redirect(pending):
    if pending.payment_type == "buy" and pending.mag_id:
        return url_for("magazine_detail", mag_id=pending.mag_id)
    return url_for("magazine")


@app.route("/magazine/<int:mag_id>/download")
@customer_login_required
def magazine_download(mag_id):
    mag = Magazine.query.get_or_404(mag_id)
    customer = get_current_customer()
    if not get_magazine_access(customer.id if customer else None, mag_id):
        flash("Please purchase this issue or subscribe to download.", "warning")
        return redirect(url_for("magazine_detail", mag_id=mag_id))
    mag_dir = os.path.join(app.static_folder, "magazines")
    return send_from_directory(mag_dir, mag.pdf_filename, as_attachment=True,
                               download_name=safe_download_filename(f"{mag.title}.pdf"))


# ── Admin: Magazine management ──

@app.route("/admin/magazines")
@admin_required
def admin_magazines():
    magazines     = Magazine.query.order_by(Magazine.published_at.desc()).all()
    subscriptions = MagazineSubscription.query.order_by(
        MagazineSubscription.created_at.desc()).limit(50).all()
    purchases     = MagazinePurchase.query.order_by(
        MagazinePurchase.purchased_at.desc()).limit(50).all()
    monthly_price = Setting.get("mag_monthly_price", "49")
    yearly_price  = Setting.get("mag_yearly_price",  "399")
    sub_enabled   = Setting.get("mag_subscription_enabled", "1")
    return render_template(
        "admin/magazines.html",
        magazines=magazines,
        subscriptions=subscriptions,
        purchases=purchases,
        monthly_price=monthly_price,
        yearly_price=yearly_price,
        sub_enabled=sub_enabled,
        active_page="magazines",
    )


@app.route("/admin/magazines/add", methods=["POST"])
@admin_required
def admin_magazine_add():
    mag = Magazine(
        title        = request.form.get("title", "").strip(),
        issue_label  = request.form.get("issue_label", "").strip(),
        description  = request.form.get("description", "").strip(),
        pdf_filename = request.form.get("pdf_filename", "").strip(),
        single_price = float(request.form.get("single_price") or 49),
        is_free      = request.form.get("is_free") == "1",
        active       = True,
    )
    db.session.add(mag)
    db.session.commit()
    flash(f"Magazine '{mag.title}' added.", "success")
    return redirect(url_for("admin_magazines"))


@app.route("/admin/magazines/edit/<int:mag_id>", methods=["POST"])
@admin_required
def admin_magazine_edit(mag_id):
    mag = Magazine.query.get_or_404(mag_id)
    mag.title        = request.form.get("title", mag.title).strip()
    mag.issue_label  = request.form.get("issue_label", mag.issue_label).strip()
    mag.description  = request.form.get("description", mag.description or "").strip()
    mag.pdf_filename = request.form.get("pdf_filename", mag.pdf_filename or "").strip()
    mag.single_price = float(request.form.get("single_price") or mag.single_price)
    mag.is_free      = request.form.get("is_free") == "1"
    mag.active       = request.form.get("active") == "1"
    db.session.commit()
    flash("Magazine updated.", "success")
    return redirect(url_for("admin_magazines"))


@app.route("/admin/magazines/delete/<int:mag_id>", methods=["POST"])
@admin_required
def admin_magazine_delete(mag_id):
    mag = Magazine.query.get_or_404(mag_id)
    mag.active = False
    db.session.commit()
    flash("Magazine deactivated.", "success")
    return redirect(url_for("admin_magazines"))


@app.route("/admin/magazines/settings", methods=["POST"])
@admin_required
def admin_magazine_settings():
    Setting.set("mag_monthly_price",        request.form.get("monthly_price", "49"))
    Setting.set("mag_yearly_price",         request.form.get("yearly_price",  "399"))
    Setting.set("mag_subscription_enabled", "1" if request.form.get("sub_enabled") else "0")
    flash("Subscription pricing updated.", "success")
    return redirect(url_for("admin_magazines"))


# ─────────────────────────────────────────────
# CUSTOMER ACCOUNT ROUTES
# ─────────────────────────────────────────────

@app.route("/account/register", methods=["GET", "POST"])
def customer_register():
    if session.get("customer_id"):
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        phone    = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        error = None
        if not all([name, email, phone, password]):
            error = "All fields are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif Customer.query.filter_by(email=email).first():
            error = "An account with this email already exists."

        if error:
            flash(error, "danger")
            return render_template("account/register.html",
                                   name=name, email=email, phone=phone)

        customer = Customer(name=name, email=email, phone=phone)
        customer.set_password(password)
        db.session.add(customer)
        db.session.flush()  # get customer.id

        # Auto-link existing orders placed with same email or phone
        linked = Order.query.filter(
            Order.customer_id.is_(None),
            or_(Order.customer_email == email, Order.customer_phone == phone),
        ).all()
        for o in linked:
            o.customer_id = customer.id
        db.session.flush()
        customer.update_tier()

        # Pre-populate address from linked orders
        if linked:
            last = max(linked, key=lambda o: o.created_at)
            if last.address:
                customer.saved_address = last.address
                customer.saved_city    = last.city
                customer.saved_pincode = last.pincode
                # Use state from this order, or find any linked order that has one
                if last.state:
                    customer.saved_state = last.state
                else:
                    state_order = next((o for o in sorted(linked, key=lambda o: o.created_at, reverse=True)
                                        if o.state), None)
                    customer.saved_state = state_order.state if state_order else None

        db.session.commit()

        session["customer_id"] = customer.id
        flash(f"Welcome, {customer.name}! Your account has been created.", "success")
        if linked:
            flash(f"{len(linked)} previous order(s) have been linked to your account.", "info")
        return redirect(url_for("customer_dashboard"))

    return render_template("account/register.html",
                           name=request.args.get("name", ""),
                           email=request.args.get("email", ""),
                           phone=request.args.get("phone", ""))


@app.route("/account/login", methods=["GET", "POST"])
def customer_login():
    if session.get("customer_id"):
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        customer = Customer.query.filter_by(email=email, is_active=True).first()

        if customer and customer.check_password(password):
            session["customer_id"] = customer.id

            # Pull in any guest orders (no account at checkout time) placed
            # with this same email/phone, so they show up in the dashboard.
            linked = Order.query.filter(
                Order.customer_id.is_(None),
                or_(Order.customer_email == customer.email, Order.customer_phone == customer.phone),
            ).all()
            if linked:
                try:
                    for o in linked:
                        o.customer_id = customer.id
                    customer.update_tier()
                    db.session.commit()
                    flash(f"{len(linked)} previous order(s) linked to your account.", "info")
                except Exception:
                    db.session.rollback()
                    app.logger.exception("customer_login: guest-order auto-link failed")

            raw_next = request.form.get("next", "")
            # Only allow local redirects — reject absolute URLs to prevent open redirect
            from urllib.parse import urlparse
            next_url = raw_next if raw_next and not urlparse(raw_next).netloc else url_for("customer_dashboard")
            flash(f"Welcome back, {customer.name}!", "success")
            return redirect(next_url)

        flash("Invalid email or password.", "danger")
        return render_template("account/login.html", email=email,
                               next=request.form.get("next", ""))

    return render_template("account/login.html", email="",
                           next=request.args.get("next", ""))


@app.route("/account/logout")
def customer_logout():
    session.pop("customer_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/account/")
@customer_login_required
def customer_dashboard():
    customer = get_current_customer()
    orders = customer.orders.order_by(Order.created_at.desc()).all()
    return render_template("account/dashboard.html", customer=customer, orders=orders)


@app.route("/account/forgot-password", methods=["GET", "POST"])
def customer_forgot_password():
    if session.get("customer_id"):
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        customer = Customer.query.filter_by(email=email, is_active=True).first()

        if customer:
            import secrets as _sec
            customer.reset_token         = _sec.token_urlsafe(32)
            customer.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            from email_utils import send_password_reset
            send_password_reset(customer)

        # Always show same message — don't reveal if email exists
        flash("If that email is registered, a password reset link has been sent.", "info")
        return redirect(url_for("customer_login"))

    return render_template("account/forgot_password.html")


@app.route("/account/reset-password/<token>", methods=["GET", "POST"])
def customer_reset_password(token):
    customer = Customer.query.filter_by(reset_token=token).first()

    if not customer or not customer.reset_token_expires \
            or datetime.utcnow() > customer.reset_token_expires:
        flash("This reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect(url_for("customer_forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            customer.set_password(password)
            customer.reset_token         = None
            customer.reset_token_expires = None
            db.session.commit()
            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for("customer_login"))

    return render_template("account/reset_password.html", token=token)


@app.route("/account/profile", methods=["GET", "POST"])
@customer_login_required
def customer_profile():
    customer = get_current_customer()

    if request.method == "POST":
        name         = request.form.get("name", "").strip()
        phone        = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "")
        confirm      = request.form.get("confirm_password", "")

        if not name or not phone:
            flash("Name and phone are required.", "danger")
        elif new_password and len(new_password) < 8:
            flash("New password must be at least 8 characters.", "danger")
        elif new_password and new_password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            customer.name          = name
            customer.phone         = phone
            customer.saved_address = request.form.get("saved_address", "").strip() or None
            customer.saved_city    = request.form.get("saved_city", "").strip() or None
            customer.saved_state   = request.form.get("saved_state", "").strip() or None
            customer.saved_pincode = request.form.get("saved_pincode", "").strip() or None
            if new_password:
                customer.set_password(new_password)
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("customer_profile"))

    return render_template("account/profile.html", customer=customer)


# ─────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if (username == app.config["ADMIN_USERNAME"] and
                check_password_hash(app.config["ADMIN_PASSWORD_HASH"], password)):
            session["admin_logged_in"] = True
            session.permanent = True
            token = secrets.token_hex(32)
            session["admin_session_token"] = token
            ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
            db.session.add(AdminSession(token=token, ip_address=ip))
            db.session.commit()
            flash("Welcome back, Admin! 🙏", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    token = session.pop("admin_session_token", None)
    if token:
        AdminSession.query.filter_by(token=token).delete()
        db.session.commit()
    session.pop("admin_logged_in", None)
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/sessions/clear-others", methods=["POST"])
@admin_required
def admin_clear_other_sessions():
    """Revoke every tracked admin session except the one making this
    request — useful for clearing out stale/automated logins."""
    my_token = session.get("admin_session_token")
    n = AdminSession.query.filter(AdminSession.token != my_token).delete()
    db.session.commit()
    flash(f"Cleared {n} other session(s).", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/sessions/<int:session_id>/revoke", methods=["POST"])
@admin_required
def admin_revoke_session(session_id):
    sess_row = AdminSession.query.get_or_404(session_id)
    if sess_row.token == session.get("admin_session_token"):
        flash("You can't revoke your own current session — use Logout instead.", "warning")
    else:
        db.session.delete(sess_row)
        db.session.commit()
        flash("Session revoked.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/combos")
@admin_required
def admin_combos():
    combos = Combo.query.order_by(Combo.created_at.desc()).all()
    return render_template("admin/combos.html", combos=combos, active_page="combos")


def _save_combo_from_form(combo):
    """Shared by add/edit: apply form fields (incl. book/qty rows and an
    optional image upload) onto a Combo instance. Does not commit."""
    combo.name          = request.form.get("name", "").strip()
    combo.language      = request.form.get("language", "English")
    combo.description   = request.form.get("description", "").strip()
    try:
        combo.selling_price = float(request.form.get("selling_price", 0) or 0)
    except ValueError:
        combo.selling_price = 0
    combo.active = request.form.get("active") == "on"
    combo.featured = request.form.get("featured") == "on"

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = image_file.filename.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg", "png", "webp"):
            folder = os.path.join(BASE_DIR, "static", "images", "combos")
            os.makedirs(folder, exist_ok=True)
            filename = f"combo_{uuid.uuid4().hex}.{ext}"
            saved_path = os.path.join(folder, filename)
            image_file.save(saved_path)
            combo.image = filename
            # Mirror to persistent volume so uploads survive Railway restarts
            persistent_folder = os.path.join(app.config.get("UPLOAD_FOLDER", ""), "combos")
            os.makedirs(persistent_folder, exist_ok=True)
            try:
                import shutil
                shutil.copy2(saved_path, os.path.join(persistent_folder, filename))
            except Exception:
                pass

    # Rebuild combo items from the submitted book_id[] / book_qty[] rows
    combo.combo_items.clear()
    book_ids = request.form.getlist("book_id[]")
    book_qtys = request.form.getlist("book_qty[]")
    for bid, qty in zip(book_ids, book_qtys):
        if not bid:
            continue
        try:
            bid_int, qty_int = int(bid), max(1, int(qty or 1))
        except ValueError:
            continue
        combo.combo_items.append(ComboItem(book_id=bid_int, quantity=qty_int))


@app.route("/admin/combos/add", methods=["GET", "POST"])
@admin_required
def admin_combo_add():
    if request.method == "POST":
        combo = Combo(selling_price=0)
        _save_combo_from_form(combo)
        if not combo.name or not combo.combo_items:
            flash("A combo needs a name and at least one book.", "danger")
            return render_template("admin/combo_form.html", combo=combo,
                                   books=Book.query.filter_by(deleted=False, active=True).order_by(Book.title).all(),
                                   active_page="combos")
        db.session.add(combo)
        db.session.commit()
        flash(f'Combo "{combo.name}" created.', "success")
        return redirect(url_for("admin_combos"))

    return render_template("admin/combo_form.html", combo=None,
                           books=Book.query.filter_by(deleted=False, active=True).order_by(Book.title).all(),
                           active_page="combos")


@app.route("/admin/combos/edit/<int:combo_id>", methods=["GET", "POST"])
@admin_required
def admin_combo_edit(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    if request.method == "POST":
        _save_combo_from_form(combo)
        if not combo.name or not combo.combo_items:
            flash("A combo needs a name and at least one book.", "danger")
        else:
            db.session.commit()
            flash(f'Combo "{combo.name}" updated.', "success")
            return redirect(url_for("admin_combos"))

    return render_template("admin/combo_form.html", combo=combo,
                           books=Book.query.filter_by(deleted=False, active=True).order_by(Book.title).all(),
                           active_page="combos")


@app.route("/admin/combos/toggle/<int:combo_id>", methods=["POST"])
@admin_required
def admin_combo_toggle(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    combo.active = not combo.active
    db.session.commit()
    flash(f'Combo "{combo.name}" is now {"active" if combo.active else "inactive"}.', "success")
    return redirect(url_for("admin_combos"))


@app.route("/admin/combos/toggle-featured/<int:combo_id>", methods=["POST"])
@admin_required
def admin_combo_toggle_featured(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    combo.featured = not combo.featured
    db.session.commit()
    flash(f'Combo "{combo.name}" ' + ("added to" if combo.featured else "removed from")
          + " Featured Combos on the home page.", "success")
    return redirect(url_for("admin_combos"))


@app.route("/admin/combos/delete/<int:combo_id>", methods=["POST"])
@admin_required
def admin_combo_delete(combo_id):
    combo = Combo.query.get_or_404(combo_id)
    if OrderItem.query.filter_by(combo_id=combo.id).first():
        flash("This combo has past orders and can't be deleted — deactivate it instead.", "warning")
        return redirect(url_for("admin_combos"))
    name = combo.name
    db.session.delete(combo)
    db.session.commit()
    flash(f'Combo "{name}" deleted.', "info")
    return redirect(url_for("admin_combos"))


@app.route("/admin/reviews")
@admin_required
def admin_reviews():
    status = request.args.get("status", "pending")
    q = Review.query
    if status == "pending":
        q = q.filter_by(approved=False)
    elif status == "approved":
        q = q.filter_by(approved=True)
    reviews = q.order_by(Review.created_at.desc()).all()
    counts = {
        "pending":  Review.query.filter_by(approved=False).count(),
        "approved": Review.query.filter_by(approved=True).count(),
    }
    return render_template("admin/reviews.html", reviews=reviews, status=status,
                           counts=counts, active_page="reviews")


@app.route("/admin/reviews/<int:review_id>/approve", methods=["POST"])
@admin_required
def admin_approve_review(review_id):
    review = Review.query.get_or_404(review_id)
    review.approved = True
    db.session.commit()
    flash(f"Review by {review.customer.name} approved and now visible on the site.", "success")
    return redirect(request.referrer or url_for("admin_reviews"))


@app.route("/admin/reviews/<int:review_id>/reject", methods=["POST"])
@admin_required
def admin_reject_review(review_id):
    review = Review.query.get_or_404(review_id)
    db.session.delete(review)
    db.session.commit()
    flash("Review rejected and removed.", "info")
    return redirect(request.referrer or url_for("admin_reviews"))


@app.route("/admin/whatsapp-inquiries")
@admin_required
def admin_whatsapp_inquiries():
    page   = request.args.get("page", 1, type=int)
    tab    = request.args.get("tab", "open")
    allowed = {"open", "converted", "dismissed"}
    if tab not in allowed:
        tab = "open"
    try:
        inquiries = (WhatsAppInquiry.query
                     .filter_by(status=tab)
                     .order_by(WhatsAppInquiry.created_at.desc())
                     .paginate(page=page, per_page=50, error_out=False))
    except Exception:
        db.session.rollback()
        inquiries = (WhatsAppInquiry.query
                     .filter_by(status=tab)
                     .order_by(WhatsAppInquiry.created_at.desc())
                     .paginate(page=page, per_page=50, error_out=False))
    counts = {}
    for s in allowed:
        counts[s] = WhatsAppInquiry.query.filter_by(status=s).count()
    return render_template("admin/whatsapp_inquiries.html",
                           inquiries=inquiries,
                           tab=tab,
                           counts=counts,
                           active_page="whatsapp")


@app.route("/admin/whatsapp-inquiries/<int:inq_id>/dismiss", methods=["POST"])
@admin_required
def admin_whatsapp_dismiss(inq_id):
    inq  = WhatsAppInquiry.query.get_or_404(inq_id)
    back = request.args.get("tab", "open")
    try:
        inq.status = "dismissed"
        db.session.commit()
        flash("Lead dismissed. Notes preserved.", "info")
    except Exception:
        db.session.rollback()
        flash("Could not dismiss lead.", "danger")
    return redirect(url_for("admin_whatsapp_inquiries", tab=back))


@app.route("/admin/whatsapp-inquiries/<int:inq_id>/restore", methods=["POST"])
@admin_required
def admin_whatsapp_restore(inq_id):
    inq = WhatsAppInquiry.query.get_or_404(inq_id)
    try:
        inq.status = "open"
        db.session.commit()
        flash("Lead restored to Open.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not restore lead.", "danger")
    return redirect(url_for("admin_whatsapp_inquiries", tab="dismissed"))


@app.route("/admin/whatsapp-inquiries/<int:inq_id>/note", methods=["POST"])
@admin_required
def admin_whatsapp_note(inq_id):
    inq = WhatsAppInquiry.query.get_or_404(inq_id)
    note = (request.get_json() or {}).get("note", "").strip()
    try:
        inq.admin_note = note
        db.session.commit()
        return {"ok": True}, 200
    except Exception:
        db.session.rollback()
        return {"ok": False}, 500


@app.route("/admin/whatsapp-inquiries/<int:inq_id>/convert")
@admin_required
def admin_whatsapp_convert(inq_id):
    inq = WhatsAppInquiry.query.get_or_404(inq_id)
    try:
        inq.status = "converted"
        db.session.commit()
    except Exception:
        db.session.rollback()
    name  = inq.customer_name  or ""
    phone = inq.customer_phone or ""
    note  = f"WhatsApp enquiry for: {inq.book_title or 'general'}"
    return redirect(url_for("admin_create_manual_order", name=name, phone=phone, note=note,
                             email=inq.customer_email or "",
                             age=inq.age or "", profession=inq.profession or "",
                             address=inq.address or "", city=inq.city or "",
                             state=inq.state or "", pincode=inq.pincode or "",
                             book_id=inq.book_id or ""))


@app.route("/admin/test-email", methods=["GET", "POST"])
@admin_required
def admin_test_email():
    """Send a test email via Brevo HTTP API to verify config is working."""
    import requests as http_req
    result = None
    cfg = {
        "api_key_set": bool(app.config.get("BREVO_API_KEY", "")),
        "username":    app.config.get("MAIL_USERNAME", "iskconbooks.in@gmail.com"),
    }
    if request.method == "POST":
        to = request.form.get("to_email", "").strip()
        if not to:
            result = {"ok": False, "msg": "Please enter a recipient email address."}
        elif not cfg["api_key_set"]:
            result = {"ok": False, "msg": "BREVO_API_KEY not set in Railway environment variables."}
        else:
            payload = {
                "sender":      {"name": "ISKCON Book Store", "email": cfg["username"]},
                "to":          [{"email": to}],
                "subject":     "Test Email — ISKCON Book Store",
                "htmlContent": "<h2>Test Email</h2><p>If you received this, Brevo email is configured correctly. Hare Krishna! 🙏</p>",
            }
            headers = {
                "accept":       "application/json",
                "content-type": "application/json",
                "api-key":      app.config.get("BREVO_API_KEY"),
            }
            try:
                resp = http_req.post("https://api.brevo.com/v3/smtp/email",
                                     json=payload, headers=headers, timeout=15)
                if resp.status_code in (200, 201):
                    result = {"ok": True, "msg": f"Test email sent to {to}. Check inbox and spam folder."}
                else:
                    result = {"ok": False, "msg": f"Brevo API error {resp.status_code}: {resp.text[:300]}"}
            except Exception as e:
                result = {"ok": False, "msg": f"Request error: {e}"}
    to_email = request.form.get("to_email", cfg["username"]) if request.method == "POST" else cfg["username"]
    return render_template("admin/test_email.html", cfg=cfg, result=result, to_email=to_email)


_IST_OFFSET = timedelta(hours=5, minutes=30)


def _add_months(first_of_month, delta):
    """first_of_month is a datetime on day 1; returns day 1 of the month `delta` away."""
    idx = first_of_month.year * 12 + (first_of_month.month - 1) + delta
    return first_of_month.replace(year=idx // 12, month=idx % 12 + 1, day=1)


@app.route("/admin/")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    # ── Month filter (IST months; DB stores UTC). Default = all time. ──
    now_ist = datetime.utcnow() + _IST_OFFSET
    this_month = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    selected_month = None
    month_start = month_end = None          # UTC bounds of the selected month
    try:
        selected_month = datetime.strptime(request.args.get("month", ""), "%Y-%m")
    except ValueError:
        selected_month = None
    if selected_month:
        month_start = selected_month - _IST_OFFSET
        month_end = _add_months(selected_month, 1) - _IST_OFFSET

    def in_month(query, column):
        if month_start is None:
            return query
        return query.filter(column >= month_start, column < month_end)

    total_orders        = in_month(Order.query.filter_by(is_deleted=False), Order.created_at).count()
    total_revenue       = in_month(db.session.query(db.func.sum(Order.total_amount))
                                   .filter(Order.payment_status != "failed",
                                           Order.is_deleted == False), Order.created_at).scalar() or 0
    total_books         = Book.query.filter_by(active=True).count()
    pending_orders      = in_month(Order.query.filter_by(order_status="placed", is_deleted=False),
                                   Order.created_at).count()
    recent_orders       = in_month(Order.query.filter_by(is_deleted=False), Order.created_at)\
                                     .order_by(Order.created_at.desc()).limit(10).all()
    low_stock           = Book.query.filter(Book.stock < 5, Book.active == True).all()
    temple_books_total  = in_month(db.session.query(db.func.sum(StockReceipt.quantity)),
                                   StockReceipt.received_date).scalar() or 0
    temple_pending_payment = db.session.query(db.func.sum(StockReceipt.total_payment))\
                               .filter(StockReceipt.payment_status == "pending").scalar() or 0
    recent_receipts     = StockReceipt.query.order_by(StockReceipt.received_date.desc()).limit(5).all()

    # ── Month picker options + prev/next ──
    first_order = db.session.query(db.func.min(Order.created_at)).scalar()
    first_month = ((first_order + _IST_OFFSET).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                   if first_order else this_month)
    month_options = []
    m = this_month
    while m >= first_month and len(month_options) < 60:
        month_options.append({"key": m.strftime("%Y-%m"), "label": m.strftime("%B %Y")})
        m = _add_months(m, -1)
    prev_month = next_month = None
    if selected_month:
        prev_month = _add_months(selected_month, -1).strftime("%Y-%m")
        if selected_month < this_month:
            next_month = _add_months(selected_month, 1).strftime("%Y-%m")

    # ── Month-wise breakdown for the last 12 months ──
    window_start = _add_months(this_month, -11)
    buckets = {}
    for created_at, amount, pay_status in db.session.query(
            Order.created_at, Order.total_amount, Order.payment_status)\
            .filter(Order.is_deleted == False,
                    Order.created_at >= window_start - _IST_OFFSET).all():
        key = (created_at + _IST_OFFSET).strftime("%Y-%m")
        row = buckets.setdefault(key, {"orders": 0, "revenue": 0.0})
        row["orders"] += 1
        if pay_status != "failed":
            row["revenue"] += amount or 0
    monthly_breakdown = []
    m = this_month
    for _ in range(12):
        key = m.strftime("%Y-%m")
        row = buckets.get(key, {"orders": 0, "revenue": 0.0})
        monthly_breakdown.append({"key": key, "label": m.strftime("%b %Y"),
                                  "orders": row["orders"], "revenue": row["revenue"]})
        m = _add_months(m, -1)

    cutoff = datetime.utcnow() - timedelta(minutes=30)
    AdminSession.query.filter(AdminSession.last_seen < cutoff).delete()
    db.session.commit()
    active_sessions = AdminSession.query.order_by(AdminSession.last_seen.desc()).all()
    return render_template("admin/dashboard.html",
                           total_orders=total_orders,
                           total_revenue=total_revenue,
                           total_books=total_books,
                           pending_orders=pending_orders,
                           recent_orders=recent_orders,
                           low_stock=low_stock,
                           temple_books_total=temple_books_total,
                           temple_pending_payment=temple_pending_payment,
                           recent_receipts=recent_receipts,
                           active_sessions=active_sessions,
                           selected_month=selected_month.strftime("%Y-%m") if selected_month else "",
                           selected_month_label=selected_month.strftime("%B %Y") if selected_month else "",
                           this_month_key=this_month.strftime("%Y-%m"),
                           month_options=month_options,
                           prev_month=prev_month, next_month=next_month,
                           monthly_breakdown=monthly_breakdown)


# ── Admin: Books ──

@app.route("/admin/books")
@admin_required
def admin_books():
    page          = request.args.get("page", 1, type=int)
    query         = request.args.get("q", "")
    category_id   = request.args.get("category_id", type=int)
    title_f       = request.args.get("tf", "")
    author_f      = request.args.get("af", "")
    lang_filter   = request.args.get("lang", "")
    fmt_filter    = request.args.get("fmt", "")
    status_filter = request.args.get("status", "")

    bq = Book.query.filter_by(deleted=False)
    if query:
        import re
        for word in query.split():
            word = re.sub(r"[^\w]", "", word)
            if not word:
                continue
            bq = bq.filter(or_(
                Book.title.ilike(f"%{word}%"),
                Book.author.ilike(f"%{word}%"),
            ))
    if title_f:
        bq = bq.filter(Book.title.ilike(f"%{title_f}%"))
    if author_f:
        bq = bq.filter(Book.author.ilike(f"%{author_f}%"))
    if category_id:
        bq = bq.filter_by(category_id=category_id)
    if lang_filter:
        bq = bq.filter(Book.language == lang_filter)
    if fmt_filter == 'ebook':
        bq = bq.filter(Book.is_ebook == True)
    elif fmt_filter == 'paper':
        bq = bq.filter(Book.is_ebook == False)
    if status_filter == 'active':
        bq = bq.filter(Book.active == True)
    elif status_filter == 'inactive':
        bq = bq.filter(Book.active == False)
    elif status_filter == 'featured':
        bq = bq.filter(Book.featured == True)

    bq = bq.order_by(Book.created_at.desc())

    books          = bq.paginate(page=page, per_page=20)
    trash_count    = Book.query.filter_by(deleted=True).count()
    all_categories = Category.query.order_by(Category.sort_order).all()
    active_cat     = Category.query.get(category_id) if category_id else None
    langs          = [r[0] for r in db.session.query(Book.language)
                      .filter(Book.deleted == False, Book.language != None, Book.language != '')
                      .distinct().order_by(Book.language).all()]
    return render_template("admin/books.html", books=books, query=query,
                           trash_count=trash_count, all_categories=all_categories,
                           active_cat=active_cat, category_id=category_id,
                           title_f=title_f, author_f=author_f,
                           lang_filter=lang_filter, fmt_filter=fmt_filter,
                           status_filter=status_filter, langs=langs)


@app.route("/admin/books/export-stock-csv")
@admin_required
def export_stock_csv():
    """Download books as a CSV stock receipt for physical records — respects
    the same search/category/language/format/status filters as Manage Books,
    and includes a summary of total / eBook / Paper counts."""
    query         = request.args.get("q", "")
    category_id   = request.args.get("category_id", type=int)
    title_f       = request.args.get("tf", "")
    author_f      = request.args.get("af", "")
    lang_filter   = request.args.get("lang", "")
    fmt_filter    = request.args.get("fmt", "")
    status_filter = request.args.get("status", "")

    bq = Book.query.filter_by(deleted=False)
    if query:
        import re
        for word in query.split():
            word = re.sub(r"[^\w]", "", word)
            if not word:
                continue
            bq = bq.filter(or_(
                Book.title.ilike(f"%{word}%"),
                Book.author.ilike(f"%{word}%"),
            ))
    if title_f:
        bq = bq.filter(Book.title.ilike(f"%{title_f}%"))
    if author_f:
        bq = bq.filter(Book.author.ilike(f"%{author_f}%"))
    if category_id:
        bq = bq.filter_by(category_id=category_id)
    if lang_filter:
        bq = bq.filter(Book.language == lang_filter)
    if fmt_filter == 'ebook':
        bq = bq.filter(Book.is_ebook == True)
    elif fmt_filter == 'paper':
        bq = bq.filter(Book.is_ebook == False)
    if status_filter == 'active':
        bq = bq.filter(Book.active == True)
    elif status_filter == 'inactive':
        bq = bq.filter(Book.active == False)
    elif status_filter == 'featured':
        bq = bq.filter(Book.featured == True)

    all_books = bq.order_by(Book.category_id, Book.title).all()

    total_count = len(all_books)
    ebook_count = sum(1 for b in all_books if b.is_ebook)
    paper_count = total_count - ebook_count

    output = io.StringIO()
    writer = csv.writer(output)

    # Summary block
    writer.writerow(["Stock Report Summary"])
    writer.writerow(["Total Books:", total_count])
    writer.writerow(["eBooks:", ebook_count])
    writer.writerow(["Hard Copy (Paper):", paper_count])
    writer.writerow([])

    # Header row
    writer.writerow([
        "Sr No", "Title", "Author", "Category", "Language", "Format",
        "Price (INR)", "Original Price (INR)", "Discount %",
        "Stock Qty", "ISBN", "Publisher", "Pages", "Active", "Featured"
    ])

    for idx, book in enumerate(all_books, start=1):
        writer.writerow([
            idx,
            book.title,
            book.author,
            book.category.name if book.category else "",
            book.language or "",
            "eBook" if book.is_ebook else "Paper",
            int(book.price),
            int(book.original_price) if book.original_price else "",
            book.discount_percent or "",
            book.stock,
            book.isbn or "",
            book.publisher or "",
            book.pages or "",
            "Yes" if book.active else "No",
            "Yes" if book.featured else "No",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")   # utf-8-sig adds BOM for Excel
    from flask import Response
    tag = f"_{fmt_filter}" if fmt_filter else ""
    filename = f"stock_report{tag}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/admin/books/add", methods=["GET", "POST"])
@admin_required
def admin_add_book():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        image_file = request.files.get("image")
        image_name = save_image(image_file) or "default_book.jpg"

        ebook_file_obj = request.files.get("ebook_file")
        is_ebook = request.form.get("book_format") == "ebook"
        ebook_filename = save_ebook(ebook_file_obj) if is_ebook else None
        preview_filename = save_preview(request.files.get("preview_file"))
        review_video_filename = save_review_video(request.files.get("review_video"))

        book = Book(
            title          = request.form["title"].strip(),
            author         = request.form["author"].strip(),
            description    = request.form.get("description", "").strip(),
            short_desc     = request.form.get("short_desc", "").strip(),
            price          = float(request.form["price"]),
            original_price = float(request.form["original_price"]) if request.form.get("original_price") else None,
            image          = image_name,
            category_id    = int(request.form.get("category_id") or 0) if request.form.get("category_id", "") != "" else None,
            isbn           = request.form.get("isbn", "").strip(),
            language       = request.form.get("language", "English").strip(),
            pages          = int(request.form["pages"]) if request.form.get("pages") else None,
            weight_kg      = float(request.form["weight_kg"]) if request.form.get("weight_kg") else 0.1,
            publisher      = request.form.get("publisher", "The Bhaktivedanta Book Trust").strip(),
            stock          = int(request.form.get("stock", 100)),
            featured       = bool(request.form.get("featured")),
            active         = bool(request.form.get("active", True)),
            is_ebook       = is_ebook,
            ebook_file     = ebook_filename,
            preview_file   = preview_filename,
            review_text      = request.form.get("review_text", "").strip() or None,
            review_video     = review_video_filename,
            review_video_url  = _make_embed_url(request.form.get("review_video_url", "").strip()),
            review_video_url2 = _make_embed_url(request.form.get("review_video_url2", "").strip()),
            review_video_url3 = _make_embed_url(request.form.get("review_video_url3", "").strip()),
        )
        db.session.add(book)
        db.session.flush()  # get book.id for gallery photos

        for extra_file in request.files.getlist("gallery_images"):
            if extra_file and extra_file.filename:
                saved = save_image(extra_file)
                if saved:
                    db.session.add(BookImage(book_id=book.id, filename=saved))

        db.session.commit()
        flash("Book added successfully!", "success")
        return redirect(safe_books_return(request.form.get("return_to")))

    return_to = safe_books_return(request.args.get("return_to"))
    return render_template("admin/book_form.html", book=None, categories=categories, return_to=return_to)


@app.route("/admin/books/<int:book_id>/clone-ebook", methods=["POST"])
@admin_required
def admin_clone_as_ebook(book_id):
    """Duplicate an existing book's details into a new eBook draft so the admin
    only has to switch the format and upload the eBook file, instead of
    re-typing title/author/description/etc. from scratch."""
    src = Book.query.get_or_404(book_id)
    ebook_category = Category.query.filter_by(slug="e-book").first()

    clone = Book(
        title             = src.title,
        author            = src.author,
        description       = src.description,
        short_desc        = src.short_desc,
        price             = src.price,
        original_price    = src.original_price,
        image             = src.image,
        category_id       = ebook_category.id if ebook_category else src.category_id,
        isbn              = src.isbn,
        language          = src.language,
        pages             = src.pages,
        weight_kg         = src.weight_kg,
        publisher         = src.publisher,
        stock             = src.stock,
        featured          = False,
        active            = False,   # stays hidden until the eBook file is uploaded and reviewed
        is_ebook          = True,
        ebook_file        = None,
        preview_file      = None,
        review_text       = src.review_text,
        review_video      = src.review_video,
        review_video_url  = src.review_video_url,
        review_video_url2 = src.review_video_url2,
        review_video_url3 = src.review_video_url3,
    )
    db.session.add(clone)
    db.session.commit()
    flash(f'Cloned "{src.title}" as a new eBook draft — upload the eBook file below, then mark it Active.', "success")
    from urllib.parse import quote
    return_to = safe_books_return(request.args.get("return_to"))
    return redirect(url_for("admin_edit_book", book_id=clone.id) + "?return_to=" + quote(return_to, safe=""))


@app.route("/admin/books/edit/<int:book_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_book(book_id):
    book       = Book.query.get_or_404(book_id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == "POST":
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            # Delete old image if not default
            if book.image != "default_book.jpg":
                old_path = os.path.join(app.config["UPLOAD_FOLDER"], book.image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            book.image = save_image(image_file) or book.image

        book.title          = request.form["title"].strip()
        book.author         = request.form["author"].strip()
        book.description    = request.form.get("description", "").strip()
        book.short_desc     = request.form.get("short_desc", "").strip()
        book.price          = float(request.form["price"])
        book.original_price = float(request.form["original_price"]) if request.form.get("original_price") else None
        book.category_id    = int(request.form["category_id"]) if request.form.get("category_id") else None
        book.isbn           = request.form.get("isbn", "").strip()
        book.language       = request.form.get("language", "English").strip()
        book.pages          = int(request.form["pages"]) if request.form.get("pages") else None
        book.weight_kg      = float(request.form["weight_kg"]) if request.form.get("weight_kg") else 0.1
        book.publisher      = request.form.get("publisher", "").strip()
        book.stock          = int(request.form.get("stock", 100))
        book.featured       = bool(request.form.get("featured"))
        book.active         = bool(request.form.get("active"))

        is_ebook = request.form.get("book_format") == "ebook"
        book.is_ebook = is_ebook

        ebook_file_obj = request.files.get("ebook_file")
        if ebook_file_obj and ebook_file_obj.filename:
            if book.ebook_file:
                old_ebook = os.path.join(app.config["EBOOK_FOLDER"], book.ebook_file)
                if os.path.exists(old_ebook):
                    os.remove(old_ebook)
            book.ebook_file = save_ebook(ebook_file_obj)

        if not is_ebook:
            book.ebook_file = None

        preview_file_obj = request.files.get("preview_file")
        if preview_file_obj and preview_file_obj.filename:
            if book.preview_file:
                old_preview = os.path.join(app.config["PREVIEW_FOLDER"], book.preview_file)
                if os.path.exists(old_preview):
                    os.remove(old_preview)
            book.preview_file = save_preview(preview_file_obj)

        book.review_text = request.form.get("review_text", "").strip() or None
        book.review_video_url  = _make_embed_url(request.form.get("review_video_url", "").strip())
        book.review_video_url2 = _make_embed_url(request.form.get("review_video_url2", "").strip())
        book.review_video_url3 = _make_embed_url(request.form.get("review_video_url3", "").strip())

        review_video_obj = request.files.get("review_video")
        if review_video_obj and review_video_obj.filename:
            if book.review_video:
                old_vid = os.path.join(app.config["REVIEW_VIDEO_FOLDER"], book.review_video)
                if os.path.exists(old_vid):
                    os.remove(old_vid)
            book.review_video = save_review_video(review_video_obj)

        if request.form.get("remove_review_video") == "1" and book.review_video:
            old_vid = os.path.join(app.config["REVIEW_VIDEO_FOLDER"], book.review_video)
            if os.path.exists(old_vid):
                os.remove(old_vid)
            book.review_video = None

        # Append any newly-uploaded gallery photos (existing ones are
        # managed separately via admin_delete_book_photo, not replaced here)
        next_sort = max([bi.sort_order for bi in book.gallery_images], default=-1) + 1
        for extra_file in request.files.getlist("gallery_images"):
            if extra_file and extra_file.filename:
                saved = save_image(extra_file)
                if saved:
                    db.session.add(BookImage(book_id=book.id, filename=saved, sort_order=next_sort))
                    next_sort += 1

        db.session.commit()
        flash("Book updated!", "success")
        return redirect(safe_books_return(request.form.get("return_to")))

    ebook_file_exists = bool(book.ebook_file) and os.path.exists(
        os.path.join(app.config["EBOOK_FOLDER"], book.ebook_file)
    )
    return_to = safe_books_return(request.args.get("return_to"))
    return render_template("admin/book_form.html", book=book, categories=categories,
                            ebook_file_exists=ebook_file_exists, return_to=return_to)


@app.route("/admin/books/<int:book_id>/photo/<int:photo_id>/delete", methods=["POST"])
@admin_required
def admin_delete_book_photo(book_id, photo_id):
    photo = BookImage.query.filter_by(id=photo_id, book_id=book_id).first_or_404()
    photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo.filename)
    if os.path.exists(photo_path):
        os.remove(photo_path)
    db.session.delete(photo)
    db.session.commit()
    flash("Photo removed.", "info")
    return redirect(url_for("admin_edit_book", book_id=book_id,
                             return_to=request.args.get("return_to", "")))


@app.route("/admin/books/bulk-video", methods=["GET", "POST"])
@admin_required
def admin_bulk_video():
    books = Book.query.filter_by(deleted=False).order_by(Book.title).all()
    if request.method == "POST":
        updated = 0
        for book in books:
            u1 = _make_embed_url(request.form.get(f"url1_{book.id}", "").strip())
            u2 = _make_embed_url(request.form.get(f"url2_{book.id}", "").strip())
            u3 = _make_embed_url(request.form.get(f"url3_{book.id}", "").strip())
            if u1 != book.review_video_url or u2 != book.review_video_url2 or u3 != book.review_video_url3:
                book.review_video_url  = u1
                book.review_video_url2 = u2
                book.review_video_url3 = u3
                updated += 1
        db.session.commit()
        flash(f"{updated} book(s) updated.", "success")
        return redirect(url_for("admin_bulk_video"))
    return render_template("admin/bulk_video.html", books=books)


@app.route("/admin/books/delete/<int:book_id>", methods=["POST"])
@admin_required
def admin_delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    book.active  = False
    book.deleted = True   # Move to Trash
    db.session.commit()
    flash(f'Book "{book.title}" moved to Trash. You can restore or permanently delete it from the Trash tab.', "info")
    return redirect(url_for("admin_books"))


@app.route("/admin/books/quick-update/<int:book_id>", methods=["POST"])
@admin_required
def admin_quick_update_book(book_id):
    book      = Book.query.get_or_404(book_id)
    price     = request.form.get("price", type=float)
    stock     = request.form.get("stock", type=int)
    weight_kg = request.form.get("weight_kg", type=float)
    if price is not None and price >= 0:
        book.price = price
    if stock is not None and stock >= 0:
        book.stock = stock
    if weight_kg is not None and weight_kg > 0:
        book.weight_kg = weight_kg
    db.session.commit()
    return jsonify({"success": True})


@app.route("/admin/books/reset-weights", methods=["POST"])
@admin_required
def admin_reset_book_weights():
    """Bulk reset all books with weight=0.5 (old default) to 0.1 kg."""
    updated = Book.query.filter(
        Book.deleted == False,
        Book.weight_kg == 0.5
    ).update({"weight_kg": 0.1}, synchronize_session=False)
    db.session.commit()
    flash(f"Done! {updated} book(s) reset from 0.5 kg to 0.1 kg. Update individual books with correct weights as needed.", "success")
    return redirect(url_for("admin_books"))


@app.route("/admin/books/trash")
@admin_required
def admin_trash_books():
    page          = request.args.get("page", 1, type=int)
    deleted_books = Book.query.filter_by(deleted=True).order_by(Book.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/trash_books.html", books=deleted_books)


@app.route("/admin/books/restore/<int:book_id>", methods=["POST"])
@admin_required
def admin_restore_book(book_id):
    book = Book.query.get_or_404(book_id)
    book.deleted = False
    book.active  = True
    db.session.commit()
    flash(f'Book "{book.title}" restored. You can now edit it.', "success")
    return redirect(url_for("admin_trash_books"))


@app.route("/admin/books/hard-delete/<int:book_id>", methods=["POST"])
@admin_required
def admin_hard_delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    title = book.title
    db.session.delete(book)
    db.session.commit()
    flash(f'Book "{title}" permanently deleted.', "danger")
    return redirect(url_for("admin_trash_books"))




@app.route("/admin/books/toggle-featured/<int:book_id>", methods=["POST"])
@admin_required
def toggle_featured(book_id):
    book = Book.query.get_or_404(book_id)
    book.featured = not book.featured
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"featured": book.featured})
    # Plain form post from the Books list: go back to the same filtered page
    # instead of leaving the admin on a raw JSON response.
    flash(f'"{book.title}" ' + ("added to" if book.featured else "removed from")
          + " Featured Books on the home page.", "success")
    return redirect(request.referrer or url_for("admin_books"))


# ── Admin: Gita Dan Yagna ──

def _yagna_form_to_donation(d):
    """Fill a GitaYagnaDonation from the admin's offline-entry form (paper form).
    Returns an error message string, or None when OK."""
    f = request.form
    d.donor_name = f.get("donor_name", "").strip()
    if not d.donor_name:
        return "Donor name is required."
    phone = f.get("donor_phone", "").strip()
    if phone:
        norm = valid_indian_phone(phone)
        if not norm:
            return "Please enter a valid 10-digit mobile number (or leave it empty)."
        phone = norm
    d.donor_phone = phone or None
    d.donor_email = f.get("donor_email", "").strip() or None
    if not valid_email(d.donor_email or ""):
        return "Please enter a valid email address."
    d.profession = f.get("profession", "").strip()[:100] or None
    d.area = f.get("area", "").strip()[:200] or None
    d.language = f.get("language", "Hindi")
    if d.language not in YAGNA_LANGS:
        return "Please choose a language."
    try:
        d.quantity = max(1, min(YAGNA_MAX_QTY, int(f.get("quantity") or 0)))
    except ValueError:
        d.quantity = 0
    if d.quantity < 1:
        return "Please enter the number of Gitas."
    try:
        d.amount = round(float(f.get("amount") or 0), 2)
    except ValueError:
        return "Please enter a valid amount."
    if d.amount <= 0:
        d.amount = round(yagna_config()["prices"][d.language] * d.quantity, 2)
    d.students_qty = _yagna_int("students_qty")
    d.village_qty = _yagna_int("village_qty")
    d.others_qty = _yagna_int("others_qty")
    if d.students_qty + d.village_qty + d.others_qty > d.quantity:
        return "Students + Village residents + Others is more than the total Gitas."
    d.arati = f.get("arati") == "on"
    d.yajna = f.get("yajna") == "on"
    d.dedication = f.get("dedication", "").strip()[:250] or None
    d.show_name = f.get("show_name") == "on"
    d.payment_mode = f.get("payment_mode", "qr")[:30]
    d.receipt_no = f.get("receipt_no", "").strip()[:50] or None
    d.notes = f.get("notes", "").strip() or None
    d.distribution = f.get("distribution", "local")
    if d.distribution not in ("local", "courier"):
        d.distribution = "local"
    if d.distribution == "courier":
        try:
            d.courier_charge = max(0.0, round(float(f.get("courier_charge") or 0), 2))
        except ValueError:
            return "Please enter a valid courier charge."
    else:
        d.courier_charge = 0.0
    d.recipient_name = f.get("recipient_name", "").strip()[:200] or None
    d.recipient_phone = f.get("recipient_phone", "").strip()[:20] or None
    d.recipient_address = f.get("recipient_address", "").strip() or None
    d.recipient_pincode = f.get("recipient_pincode", "").strip()[:10] or None
    if d.distribution == "courier" and not (d.recipient_name and d.recipient_address):
        return "For courier distribution please enter the recipient's name and address."
    try:
        day = datetime.strptime(f.get("donated_on", ""), "%Y-%m-%d")
        d.donated_on = day + timedelta(hours=12) - _IST_OFFSET      # noon IST that day
    except ValueError:
        d.donated_on = d.donated_on or datetime.utcnow()
    return None


@app.route("/admin/gita-yagna", methods=["GET", "POST"])
@admin_required
def admin_gita_yagna():
    if request.method == "POST":
        for lang in YAGNA_LANGS:
            try:
                price = float(request.form.get(f"price_{lang.lower()}", ""))
                if price > 0:
                    Setting.set(f"yagna_price_{lang.lower()}", str(price))
            except ValueError:
                pass
        try:
            goal = int(float(request.form.get("goal", "")))
            if goal > 0:
                Setting.set("yagna_goal", str(goal))
        except ValueError:
            pass
        try:
            wt = float(request.form.get("weight_kg", ""))
            if wt > 0:
                Setting.set("yagna_weight_kg", str(wt))
        except ValueError:
            pass
        event = request.form.get("event_date", "").strip()
        if event:
            Setting.set("yagna_event_date", event[:100])
        Setting.set("yagna_enabled", "1" if request.form.get("enabled") == "on" else "0")
        flash("Gita Dan Yagna settings saved.", "success")
        return redirect(url_for("admin_gita_yagna"))

    cfg = yagna_config()
    stats = yagna_stats(cfg)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    source = request.args.get("source", "")
    lang_f = request.args.get("lang", "")
    dist_f = request.args.get("dist", "")

    dq = GitaYagnaDonation.query
    if q:
        dq = dq.filter(or_(GitaYagnaDonation.donor_name.ilike(f"%{q}%"),
                           GitaYagnaDonation.donor_phone.ilike(f"%{q}%"),
                           GitaYagnaDonation.area.ilike(f"%{q}%")))
    if source in ("online", "offline"):
        dq = dq.filter(GitaYagnaDonation.source == source)
    if lang_f in YAGNA_LANGS:
        dq = dq.filter(GitaYagnaDonation.language == lang_f)
    if dist_f == "local":
        dq = dq.filter(or_(GitaYagnaDonation.distribution == "local",
                           GitaYagnaDonation.distribution.is_(None)))
    elif dist_f == "courier":
        dq = dq.filter(GitaYagnaDonation.distribution == "courier")
    rows = yagna_attach_donor_totals(dq.order_by(GitaYagnaDonation.donated_on.desc()).limit(500).all())
    if status == "received":
        rows = [r for r in rows if r.counted and not r.distributed]
    elif status == "pending":
        rows = [r for r in rows if not r.counted]
    elif status == "distributed":
        rows = [r for r in rows if r.distributed]
    elif status == "invite":
        rows = [r for r in rows if r.counted and r.invitation]
    return render_template("admin/gita_yagna.html", cfg=cfg, stats=stats, rows=rows,
                           langs=YAGNA_LANGS, q=q, status=status, source=source, lang_f=lang_f,
                           dist_f=dist_f, invite_min=YAGNA_INVITE_MIN, active_page="gita_yagna")


@app.route("/admin/gita-yagna/add", methods=["GET", "POST"])
@admin_required
def admin_gita_yagna_add():
    d = GitaYagnaDonation(source="offline", payment_mode="qr")
    if request.method == "POST":
        err = _yagna_form_to_donation(d)
        if err:
            flash(err, "danger")
        else:
            db.session.add(d)
            db.session.commit()
            flash(f"Offline donation of {d.quantity} Gitas by {d.donor_name} saved.", "success")
            return redirect(url_for("admin_gita_yagna"))
    return render_template("admin/gita_yagna_form.html", d=d, is_new=True, cfg=yagna_config(),
                           langs=YAGNA_LANGS, today=(datetime.utcnow() + _IST_OFFSET).strftime("%Y-%m-%d"),
                           active_page="gita_yagna")


@app.route("/admin/gita-yagna/edit/<int:did>", methods=["GET", "POST"])
@admin_required
def admin_gita_yagna_edit(did):
    d = GitaYagnaDonation.query.get_or_404(did)
    if d.source != "offline":
        flash("Online donations are managed from the Orders page.", "warning")
        return redirect(url_for("admin_gita_yagna"))
    if request.method == "POST":
        err = _yagna_form_to_donation(d)
        if err:
            db.session.rollback()
            flash(err, "danger")
        else:
            db.session.commit()
            flash("Donation updated.", "success")
            return redirect(url_for("admin_gita_yagna"))
    donated = ((d.donated_on or datetime.utcnow()) + _IST_OFFSET).strftime("%Y-%m-%d")
    return render_template("admin/gita_yagna_form.html", d=d, is_new=False, cfg=yagna_config(),
                           langs=YAGNA_LANGS, today=donated, active_page="gita_yagna")


@app.route("/admin/gita-yagna/distribute/<int:did>", methods=["POST"])
@admin_required
def admin_gita_yagna_distribute(did):
    d = GitaYagnaDonation.query.get_or_404(did)
    d.distributed = not d.distributed
    d.distributed_at = datetime.utcnow() if d.distributed else None
    db.session.commit()
    return redirect(request.referrer or url_for("admin_gita_yagna"))


@app.route("/admin/gita-yagna/delete/<int:did>", methods=["POST"])
@admin_required
def admin_gita_yagna_delete(did):
    d = GitaYagnaDonation.query.get_or_404(did)
    if d.source != "offline":
        flash("Only offline entries can be deleted here.", "warning")
    else:
        db.session.delete(d)
        db.session.commit()
        flash("Offline entry deleted.", "info")
    return redirect(url_for("admin_gita_yagna"))


@app.route("/admin/gita-yagna/certificate/<int:did>")
@admin_required
def admin_gita_yagna_certificate(did):
    d = GitaYagnaDonation.query.get_or_404(did)
    return render_template("gita_yagna_certificate.html", d=d, cfg=yagna_config(),
                           cert_no=(d.order.order_number if d.order else f"GDY-{d.id:05d}"))


@app.route("/admin/gita-yagna/export")
@admin_required
def admin_gita_yagna_export():
    from flask import Response
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ID", "Date", "Source", "Donor", "Phone", "Email", "Profession", "Area",
                "Language", "Gitas", "Gitas amount", "Distribution", "Courier charge (paid by donor)",
                "Total paid", "Recipient", "Recipient phone", "Recipient address", "Recipient pincode",
                "Students", "Village", "Others", "Arati", "Yajna",
                "Invitation card (50+ total)", "Donor total Gitas", "In the name of", "Show name", "Payment", "Receipt/Form No",
                "Status", "Distributed on", "Order #", "Notes"])
    for r in yagna_attach_donor_totals(GitaYagnaDonation.query.order_by(GitaYagnaDonation.donated_on).all()):
        w.writerow([r.id, ((r.donated_on or r.created_at) + _IST_OFFSET).strftime("%d-%m-%Y"),
                    r.source, r.donor_name, r.donor_phone or "", r.donor_email or "",
                    r.profession or "", r.area or "", r.language, r.quantity, f"{r.amount:.0f}",
                    "Courier" if r.is_courier else "Local",
                    f"{(r.courier_charge or 0):.0f}" if r.is_courier else "", f"{r.total_paid:.0f}",
                    r.recipient_name or "", r.recipient_phone or "",
                    (r.recipient_address or "").replace("\n", " "), r.recipient_pincode or "",
                    r.students_qty or 0, r.village_qty or 0, r.others_qty or 0,
                    "Yes" if r.arati else "", "Yes" if r.yajna else "",
                    "Yes" if r.invitation else "", r.donor_total, r.dedication or "",
                    "Yes" if r.show_name else "No", r.payment_mode or "", r.receipt_no or "",
                    r.status_label,
                    ((r.distributed_at + _IST_OFFSET).strftime("%d-%m-%Y") if r.distributed_at else ""),
                    r.order.order_number if r.order else "", r.notes or ""])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gita_dan_yagna.csv"})


# ── Admin: Temple Stock ──

@app.route("/admin/stock")
@admin_required
def admin_stock():
    page     = request.args.get("page", 1, type=int)
    receipts = StockReceipt.query.order_by(StockReceipt.received_date.desc()).paginate(page=page, per_page=20)
    books    = Book.query.order_by(Book.title).all()
    total_books_received = db.session.query(db.func.sum(StockReceipt.quantity)).scalar() or 0
    total_paid           = db.session.query(db.func.sum(StockReceipt.total_payment))\
                              .filter(StockReceipt.payment_status == "paid").scalar() or 0
    total_pending        = db.session.query(db.func.sum(StockReceipt.total_payment))\
                              .filter(StockReceipt.payment_status == "pending").scalar() or 0
    return render_template("admin/stock.html",
                           receipts=receipts,
                           books=books,
                           total_books_received=total_books_received,
                           total_paid=total_paid,
                           total_pending=total_pending,
                           now=datetime.utcnow())


@app.route("/admin/stock/export-csv")
@admin_required
def export_stock_receipts_csv():
    """Download temple stock receipts as CSV — all / paid / pending."""
    from flask import Response

    payment_filter = request.args.get("payment_status", "")

    rq = StockReceipt.query
    if payment_filter:
        rq = rq.filter_by(payment_status=payment_filter)
    all_receipts = rq.order_by(StockReceipt.received_date.desc()).all()

    # Totals for summary rows
    total_qty     = sum(r.quantity for r in all_receipts)
    total_cost    = sum(r.total_payment for r in all_receipts)

    output = io.StringIO()
    writer = csv.writer(output)

    # Title block
    label = {"paid": "Payment Done", "pending": "Payment Pending"}.get(payment_filter, "All Receipts")
    writer.writerow([f"ISKCON Book Store — Temple Stock Receipt Report ({label})"])
    writer.writerow([f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}"])
    writer.writerow([])

    # Header
    writer.writerow([
        "Sr No", "Date Received", "Book Title",
        "Qty Received", "Cost / Copy (INR)", "Total Amount (INR)",
        "Payment Status", "Notes"
    ])

    for idx, r in enumerate(all_receipts, start=1):
        writer.writerow([
            idx,
            r.received_date.strftime("%d-%m-%Y"),
            r.book_name,
            r.quantity,
            int(r.cost_per_unit),
            int(r.total_payment),
            "PAID" if r.payment_status == "paid" else "PENDING",
            r.notes or "",
        ])

    # Summary footer
    writer.writerow([])
    writer.writerow(["", "", "TOTAL", total_qty, "", int(total_cost), "", ""])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    tag = f"_{payment_filter}" if payment_filter else ""
    filename = f"temple_stock{tag}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/admin/stock/download-template")
@admin_required
def stock_download_template():
    """Generate an XLSX upload template with book-name dropdowns."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    from flask import Response

    books = Book.query.filter_by(active=True, deleted=False).order_by(Book.title).all()
    book_titles = [b.title for b in books]

    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Upload"

    # Hidden sheet for book names (avoids the 255-char formula limit for long lists)
    ws_books = wb.create_sheet("BookList")
    ws_books.sheet_state = "hidden"
    for i, title in enumerate(book_titles, start=1):
        ws_books.cell(row=i, column=1, value=title)

    orange_fill = PatternFill("solid", fgColor="FF9933")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, bottom=thin, top=thin)

    headers = [
        "Date Received (dd-mm-yyyy)",
        "Book Name",
        "Quantity",
        "Cost/Copy (₹)",
        "Payment Status (Paid / Pending)",
        "Notes",
    ]
    col_widths = [28, 48, 12, 18, 34, 40]

    ws.row_dimensions[1].height = 30
    for col, (header, width) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = orange_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width

    # Sample row so user knows the format
    sample = [
        datetime.now().strftime("%d-%m-%Y"),
        book_titles[0] if book_titles else "Bhagavad Gita As It Is",
        25,
        80,
        "Paid",
        "Received from temple counter",
    ]
    sample_font = Font(italic=True, color="888888")
    for col, val in enumerate(sample, start=1):
        cell = ws.cell(row=2, column=col, value=val)
        cell.font = sample_font
        cell.border = border

    # Book name dropdown (uses hidden BookList sheet — no char limit)
    if book_titles:
        n = len(book_titles)
        dv_book = DataValidation(
            type="list",
            formula1=f"BookList!$A$1:$A${n}",
            showDropDown=False,
            showErrorMessage=True,
            errorTitle="Invalid Book",
            error="Please select a book name from the dropdown.",
        )
        ws.add_data_validation(dv_book)
        dv_book.sqref = "B2:B500"

    # Payment status dropdown
    dv_pay = DataValidation(
        type="list",
        formula1='"Paid,Pending"',
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Invalid Status",
        error="Enter Paid or Pending.",
    )
    ws.add_data_validation(dv_pay)
    dv_pay.sqref = "E2:E500"

    ws.freeze_panes = "A2"

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    filename = f"temple_stock_template_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        out.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/stock/upload", methods=["POST"])
@admin_required
def stock_bulk_upload():
    """Bulk-insert temple stock receipts from an uploaded XLSX or CSV file."""
    uploaded = request.files.get("stock_file")
    if not uploaded or not uploaded.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("admin_stock"))

    ext = uploaded.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("xlsx", "csv"):
        flash("Only .xlsx or .csv files are accepted.", "danger")
        return redirect(url_for("admin_stock"))

    all_books = Book.query.all()
    book_map = {b.title.strip().lower(): b for b in all_books}

    batch_ref = "B-" + datetime.now().strftime("%d%m%y") + "-" + uuid.uuid4().hex[:4].upper()

    raw_rows = []
    if ext == "xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(c for c in row if c not in (None, "")):
                continue
            raw_rows.append(list(row))
    else:
        content = uploaded.read().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        next(reader, None)  # skip header
        for r in reader:
            if not any(c.strip() for c in r):
                continue
            raw_rows.append(r)

    inserted = 0
    skipped = []

    for i, row in enumerate(raw_rows, start=2):
        try:
            # Pad short rows
            while len(row) < 6:
                row.append("")

            date_raw    = str(row[0] or "").strip()
            book_name   = str(row[1] or "").strip()
            quantity    = int(float(str(row[2] or 0).strip() or 0))
            cost        = float(str(row[3] or 0).strip() or 0)
            payment_raw = str(row[4] or "paid").strip().lower()
            notes       = str(row[5] or "").strip()

            if not book_name:
                skipped.append(f"Row {i}: no book name")
                continue
            if quantity <= 0:
                skipped.append(f"Row {i}: quantity must be > 0")
                continue

            received_date = datetime.utcnow()
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    received_date = datetime.strptime(date_raw, fmt)
                    break
                except ValueError:
                    pass

            payment_status = "paid" if "paid" in payment_raw else "pending"
            book = book_map.get(book_name.lower())

            if not book:
                skipped.append(f"Row {i}: \"{book_name}\" not found in store — add it via Books first")
                continue

            receipt = StockReceipt(
                book_id       = book.id,
                book_name     = book.title,
                quantity      = quantity,
                cost_per_unit = cost,
                total_payment = round(quantity * cost, 2),
                payment_status= payment_status,
                received_date = received_date,
                notes         = notes,
                batch_ref     = batch_ref,
            )
            db.session.add(receipt)
            book.stock += quantity
            inserted += 1
        except Exception as e:
            skipped.append(f"Row {i}: {e}")

    db.session.commit()

    if inserted:
        flash(f"Bulk upload complete: {inserted} receipt(s) imported successfully.", "success")
    if skipped:
        details = "; ".join(skipped[:5]) + (" …" if len(skipped) > 5 else "")
        flash(
            f"{len(skipped)} row(s) skipped — {details}. "
            "Add missing books via the Books section, then re-upload.",
            "warning",
        )
    if not inserted and not skipped:
        flash("The file had no data rows to import.", "warning")

    return redirect(url_for("admin_stock"))


@app.route("/admin/stock/add", methods=["POST"])
@admin_required
def admin_add_stock():
    book_id      = request.form.get("book_id")
    book         = Book.query.get(book_id) if book_id else None
    quantity     = int(request.form["quantity"])
    cost_per_unit = float(request.form["cost_per_unit"])
    received_date_str = request.form.get("received_date", "")
    received_date = datetime.strptime(received_date_str, "%Y-%m-%d") if received_date_str else datetime.utcnow()

    receipt = StockReceipt(
        book_id        = book.id if book else None,
        book_name      = book.title if book else request.form.get("book_name_manual", "Unknown"),
        quantity       = quantity,
        cost_per_unit  = cost_per_unit,
        total_payment  = round(quantity * cost_per_unit, 2),
        payment_status = request.form.get("payment_status", "paid"),
        received_date  = received_date,
        notes          = request.form.get("notes", "").strip(),
    )
    db.session.add(receipt)
    # Also update book stock
    if book:
        book.stock += quantity
    db.session.commit()
    flash(f"Stock receipt added: {receipt.quantity} copies of '{receipt.book_name}'.", "success")
    return redirect(url_for("admin_stock"))


@app.route("/admin/stock/delete/<int:receipt_id>", methods=["POST"])
@admin_required
def admin_delete_stock(receipt_id):
    receipt = StockReceipt.query.get_or_404(receipt_id)
    # Reverse the stock addition
    if receipt.book_id:
        book = Book.query.get(receipt.book_id)
        if book:
            book.stock = max(0, book.stock - receipt.quantity)
    db.session.delete(receipt)
    db.session.commit()
    flash("Stock receipt deleted.", "info")
    return redirect(url_for("admin_stock"))


# ── Admin: Categories ──

@app.route("/admin/categories")
@admin_required
def admin_categories():
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template("admin/categories.html", categories=categories)


@app.route("/admin/categories/add", methods=["POST"])
@admin_required
def admin_add_category():
    name = request.form["name"].strip()
    slug = name.lower().replace(" ", "-").replace("'", "")
    if not Category.query.filter_by(slug=slug).first():
        cat = Category(
            name        = name,
            slug        = slug,
            description = request.form.get("description", ""),
            icon        = request.form.get("icon", "B"),
            sort_order  = int(request.form.get("sort_order", 0)),
        )
        db.session.add(cat)
        db.session.commit()
        flash(f'Category "{name}" added.', "success")
    else:
        flash("Category already exists.", "warning")
    return redirect(url_for("admin_categories"))


@app.route("/admin/categories/delete/<int:cat_id>", methods=["POST"])
@admin_required
def admin_delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    flash(f'Category "{cat.name}" deleted.', "info")
    return redirect(url_for("admin_categories"))


# ── Admin: Orders ──

@app.route("/admin/orders/create", methods=["GET", "POST"])
@admin_required
def admin_create_manual_order():
    """Create a manual order for WhatsApp / phone / walk-in enquiries."""
    books = Book.query.filter_by(active=True, deleted=False).order_by(Book.title).all()

    if request.method == "POST":
        # ── Customer details ──
        customer_name  = request.form.get("customer_name", "").strip()
        customer_phone = request.form.get("customer_phone", "").strip()
        customer_email = request.form.get("customer_email", "").strip() or None
        address        = request.form.get("address", "").strip()
        city           = request.form.get("city", "").strip()
        state          = request.form.get("state", "").strip()
        pincode        = request.form.get("pincode", "").strip()

        # ── Book rows (arrays) ──
        book_ids   = request.form.getlist("book_id")
        quantities = request.form.getlist("quantity")
        prices     = request.form.getlist("unit_price")

        age_str    = request.form.get("age", "").strip()
        profession = request.form.get("profession", "").strip() or None
        age = None
        if age_str:
            try:
                age = int(age_str)
            except ValueError:
                age = None

        if not customer_name or not customer_phone or not address or not customer_email:
            flash("Customer name, phone, address and email are required.", "danger")
            return render_template("admin/manual_order_form.html", books=books)

        if not valid_email(customer_email):
            flash("Please enter a valid email address.", "danger")
            return render_template("admin/manual_order_form.html", books=books)

        order_items_data = []
        subtotal = 0.0
        for bid, qty_str, price_str in zip(book_ids, quantities, prices):
            if not bid:
                continue
            try:
                qty   = int(qty_str)
                price = float(price_str)
            except (ValueError, TypeError):
                continue
            if qty <= 0:
                continue
            book = Book.query.get(int(bid))
            if not book:
                continue
            order_items_data.append({"book": book, "qty": qty, "price": price})
            subtotal += price * qty

        if not order_items_data:
            flash("Add at least one book to the order.", "danger")
            return render_template("admin/manual_order_form.html", books=books)

        shipping   = float(request.form.get("shipping_charge", 0) or 0)
        discount   = float(request.form.get("discount_amount", 0) or 0)
        total      = subtotal + shipping - discount

        pay_method = request.form.get("payment_method", "whatsapp")
        pay_status = request.form.get("payment_status", "pending")
        ord_status = request.form.get("order_status", "confirmed")
        notes      = request.form.get("notes", "").strip() or None

        order = Order(
            order_number    = generate_order_number(),
            customer_name   = customer_name,
            customer_phone  = customer_phone,
            customer_email  = customer_email,
            address         = address,
            city            = city,
            state           = state,
            pincode         = pincode,
            age             = age,
            profession      = profession,
            subtotal        = subtotal,
            shipping_charge = shipping,
            discount_amount = discount,
            total_amount    = total,
            payment_method  = pay_method,
            payment_status  = pay_status,
            order_status    = ord_status,
            notes           = notes,
        )
        db.session.add(order)
        db.session.flush()   # get order.id before committing

        for item_data in order_items_data:
            oi = OrderItem(
                order_id   = order.id,
                book_id    = item_data["book"].id,
                book_title = item_data["book"].title,
                quantity   = item_data["qty"],
                price      = item_data["price"],
            )
            db.session.add(oi)

        # Only deduct stock if this manual order is being recorded as
        # already shipped/delivered; otherwise it deducts at ship time
        # like every other order (see deduct_order_stock).
        if ord_status in ("shipped", "delivered"):
            deduct_order_stock(order)

        db.session.commit()
        flash(f"Manual order {order.order_number} created successfully!", "success")
        return redirect(url_for("admin_order_detail", order_id=order.id))

    return render_template("admin/manual_order_form.html", books=books)


ORDER_SORT_OPTIONS = {
    "date_desc":     ("Date: Newest First",     Order.created_at.desc()),
    "date_asc":      ("Date: Oldest First",     Order.created_at.asc()),
    "amount_desc":   ("Amount: High to Low",    Order.total_amount.desc()),
    "amount_asc":    ("Amount: Low to High",    Order.total_amount.asc()),
    "customer_asc":  ("Customer Name: A-Z",     Order.customer_name.asc()),
    "customer_desc": ("Customer Name: Z-A",     Order.customer_name.desc()),
    "age_asc":       ("Age: Low to High",       Order.age.asc()),
    "age_desc":      ("Age: High to Low",       Order.age.desc()),
    "city_asc":      ("City/Area: A-Z",         Order.city.asc()),
    "city_desc":     ("City/Area: Z-A",         Order.city.desc()),
    "status_asc":    ("Order Status: A-Z",      Order.order_status.asc()),
}

# Query-string keys the Order Report filter panel understands. Shared by the
# list view and the CSV export so the downloaded report always matches
# exactly what filters/sort are currently applied on screen.
ORDER_REPORT_FILTER_KEYS = [
    "status", "pay_status", "pay_method", "customer",
    "date_from", "date_to", "book_type", "city",
    "age_min", "age_max", "amount_min", "amount_max", "book_name",
    "product_type",
]


def build_order_report_query(args):
    """Apply every Order Report filter to a base Order query. `args` is
    typically request.args. Returns the filtered (not yet sorted) query."""
    oq = Order.query.filter_by(is_deleted=False)

    status      = args.get("status", "")
    pay_status  = args.get("pay_status", "")
    pay_method  = args.get("pay_method", "")
    customer_f  = args.get("customer", "")
    date_from   = args.get("date_from", "")
    date_to     = args.get("date_to", "")
    book_type   = args.get("book_type", "")
    city_f      = args.get("city", "")
    age_min     = args.get("age_min", "")
    age_max     = args.get("age_max", "")
    amount_min  = args.get("amount_min", "")
    amount_max  = args.get("amount_max", "")
    book_name_f = args.get("book_name", "")
    product_type = args.get("product_type", "")

    if status:
        oq = oq.filter_by(order_status=status)
    if pay_status:
        oq = oq.filter_by(payment_status=pay_status)
    if pay_method:
        oq = oq.filter_by(payment_method=pay_method)
    if customer_f:
        oq = oq.filter(or_(
            Order.customer_name.ilike(f"%{customer_f}%"),
            Order.customer_phone.ilike(f"%{customer_f}%"),
        ))
    if date_from:
        try:
            oq = oq.filter(Order.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            oq = oq.filter(Order.created_at < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    if book_type in ("ebook", "paper"):
        want_ebook = (book_type == "ebook")
        oq = oq.filter(Order.items.any(OrderItem.book.has(Book.is_ebook == want_ebook)))
    if city_f:
        oq = oq.filter(Order.city.ilike(f"%{city_f}%"))
    if age_min:
        try:
            oq = oq.filter(Order.age >= int(age_min))
        except ValueError:
            pass
    if age_max:
        try:
            oq = oq.filter(Order.age <= int(age_max))
        except ValueError:
            pass
    if amount_min:
        try:
            oq = oq.filter(Order.total_amount >= float(amount_min))
        except ValueError:
            pass
    if amount_max:
        try:
            oq = oq.filter(Order.total_amount <= float(amount_max))
        except ValueError:
            pass
    if book_name_f:
        oq = oq.filter(Order.items.any(OrderItem.book_title.ilike(f"%{book_name_f}%")))
    if product_type == "combo":
        oq = oq.filter(Order.items.any(OrderItem.combo_id.isnot(None)))
    elif product_type == "individual":
        oq = oq.filter(~Order.items.any(OrderItem.combo_id.isnot(None)))

    return oq


ORDERS_PER_PAGE_OPTIONS = (3, 5, 10, 20, 50, 100)
ORDERS_PER_PAGE_DEFAULT = 20


@app.route("/admin/orders")
@admin_required
def admin_orders():
    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "date_desc")
    per_page = request.args.get("per_page", ORDERS_PER_PAGE_DEFAULT, type=int)
    if per_page not in ORDERS_PER_PAGE_OPTIONS:
        per_page = ORDERS_PER_PAGE_DEFAULT

    oq = build_order_report_query(request.args)
    _, order_clause = ORDER_SORT_OPTIONS.get(sort, ORDER_SORT_OPTIONS["date_desc"])
    orders      = oq.order_by(order_clause).paginate(page=page, per_page=per_page)
    trash_count = Order.query.filter_by(is_deleted=True).count()

    filters = {k: request.args.get(k, "") for k in ORDER_REPORT_FILTER_KEYS}
    return render_template("admin/orders.html", orders=orders, sort=sort,
                           sort_options=ORDER_SORT_OPTIONS,
                           per_page=per_page, per_page_options=ORDERS_PER_PAGE_OPTIONS,
                           trash_count=trash_count, **filters,
                           any_filter_active=any(filters.values()))


# ─────────────────────────────────────────────
# ADMIN — MONTHLY / YEARLY SALES REPORT (office format)
# One row per order: Date, No. of Books, Books Ordered, Subtotal, Shipping, [Discount], Grand Total,
# a TOTAL row, and an all-round SUMMARY underneath. Same data feeds the on-screen page and the Excel file.
# ─────────────────────────────────────────────

SALES_REPORT_INCLUDE = {
    "paid": "Paid orders only",
    "all":  "All orders except failed / cancelled payments",
}


def _report_books_count(order):
    """Real books/copies in an order. Combo header rows are excluded (their books are
    counted through the combo's component rows); Gita Dan Yagna copies are included."""
    return sum(i.quantity or 0 for i in order.items if not (i.combo_id and not i.is_combo_component))


def _report_books_lines(order):
    """['Book title x1', '🎁 Combo name x1 (Book A x1, Book B x2)', ...] for the 'Books Ordered' column."""
    lines = []
    for item in order.display_items:
        line = f"{item.book_title} x{item.quantity}"
        if item.combo_id:
            line = f"🎁 {line}"
            if item.combo:
                inner = ", ".join(f"{ci.book.title} x{ci.quantity * item.quantity}"
                                  for ci in item.combo.combo_items if ci.book)
                if inner:
                    line += f" ({inner})"
        lines.append(line)
    return lines


def build_sales_report(year, month, include="paid"):
    """month = 1..12, or 0 for the whole year. Months follow IST (the DB stores UTC)."""
    start_ist = datetime(year, month or 1, 1)
    end_ist = _add_months(start_ist, 1 if month else 12)
    q = Order.query.filter(Order.is_deleted == False,
                           Order.created_at >= start_ist - _IST_OFFSET,
                           Order.created_at < end_ist - _IST_OFFSET,
                           Order.order_status != "cancelled")
    if include == "paid":
        q = q.filter(Order.payment_status == "paid")
    else:
        q = q.filter(Order.payment_status != "failed")
    orders = q.order_by(Order.created_at).all()

    rows = []
    fmt_copies = {"Paper copies": 0, "eBooks": 0, "Gita Dan Yagna (donated copies)": 0}
    lang_copies, books, combos, by_pay, by_status = {}, {}, {}, {}, {}
    for o in orders:
        count = _report_books_count(o)
        rows.append({
            "order": o,
            "date": (o.created_at + _IST_OFFSET).strftime("%d-%m-%Y %H:%M"),
            "count": count,
            "lines": _report_books_lines(o),
            "subtotal": round(o.subtotal or 0, 2),
            "shipping": round(o.shipping_charge or 0, 2),
            "discount": round(o.discount_amount or 0, 2),
            "total": round(o.total_amount or 0, 2),
        })
        yd = o.yagna_donation
        for i in o.items:
            if i.combo_id and not i.is_combo_component:           # combo header row
                c = combos.setdefault(i.book_title, {"qty": 0, "amount": 0.0})
                c["qty"] += i.quantity or 0
                c["amount"] += (i.price or 0) * (i.quantity or 0)
                continue
            qty = i.quantity or 0
            book = i.book if i.book_id else None
            if book is None and yd is not None:                    # Gita Dan Yagna donation line
                fmt, lang = "Gita Dan Yagna (donated copies)", yd.language
            elif book is not None:
                fmt, lang = ("eBooks" if book.is_ebook else "Paper copies"), (book.language or "—")
            else:
                fmt, lang = "Paper copies", "—"
            fmt_copies[fmt] += qty
            lang_copies[lang] = lang_copies.get(lang, 0) + qty
            b = books.setdefault(i.book_title, {"qty": 0, "amount": 0.0})
            b["qty"] += qty
            b["amount"] += (i.price or 0) * qty                    # 0 for books that sit inside a combo
        p = by_pay.setdefault((o.payment_method or "—").upper(), {"orders": 0, "total": 0.0})
        p["orders"] += 1
        p["total"] += o.total_amount or 0
        st = (o.order_status or "—").capitalize()
        by_status[st] = by_status.get(st, 0) + 1

    totals = {
        "orders": len(rows),
        "books": sum(r["count"] for r in rows),
        "subtotal": round(sum(r["subtotal"] for r in rows), 2),
        "shipping": round(sum(r["shipping"] for r in rows), 2),
        "discount": round(sum(r["discount"] for r in rows), 2),
        "total": round(sum(r["total"] for r in rows), 2),
    }
    totals["avg_order"] = round(totals["total"] / totals["orders"], 2) if totals["orders"] else 0
    return {
        "year": year, "month": month, "include": include,
        "period_label": (start_ist.strftime("%B %Y") if month else f"Full year {year}"),
        "include_label": SALES_REPORT_INCLUDE.get(include, ""),
        "rows": rows, "totals": totals, "has_discount": totals["discount"] > 0,
        "formats": fmt_copies,
        "languages": sorted(lang_copies.items(), key=lambda x: -x[1]),
        "books": sorted(books.items(), key=lambda x: (-x[1]["qty"], x[0])),
        "combos": sorted(combos.items(), key=lambda x: (-x[1]["qty"], x[0])),
        "payments": sorted(by_pay.items(), key=lambda x: -x[1]["orders"]),
        "statuses": sorted(by_status.items(), key=lambda x: -x[1]),
    }


def _sales_report_params():
    now_ist = datetime.utcnow() + _IST_OFFSET
    year = request.args.get("year", now_ist.year, type=int)
    month = request.args.get("month", now_ist.month, type=int)
    include = request.args.get("include", "paid")
    if not (2000 <= year <= 2100):
        year = now_ist.year
    if month is None or not (0 <= month <= 12):
        month = now_ist.month
    if include not in SALES_REPORT_INCLUDE:
        include = "paid"
    return year, month, include


@app.route("/admin/reports/sales")
@admin_required
def admin_sales_report():
    year, month, include = _sales_report_params()
    first = db.session.query(db.func.min(Order.created_at)).scalar()
    now_year = (datetime.utcnow() + _IST_OFFSET).year
    first_year = min(((first + _IST_OFFSET).year if first else now_year), year)
    years = list(range(now_year, first_year - 1, -1)) or [now_year]
    if year not in years:
        years.append(year)
        years.sort(reverse=True)
    months = [(0, "Whole year")] + [(m, datetime(2000, m, 1).strftime("%B")) for m in range(1, 13)]
    return render_template("admin/sales_report.html", rep=build_sales_report(year, month, include),
                           year=year, month=month, include=include, years=years, months=months,
                           include_options=SALES_REPORT_INCLUDE, active_page="sales_report")


@app.route("/admin/reports/sales/download")
@admin_required
def admin_sales_report_download():
    from flask import Response
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    year, month, include = _sales_report_params()
    rep = build_sales_report(year, month, include)
    t = rep["totals"]
    disc = rep["has_discount"]

    NAVY, LIGHT, GREY = "14284B", "E8EEF8", "BFBFBF"
    side = Side(style="thin", color=GREY)
    border = Border(left=side, right=side, top=side, bottom=side)
    white_bold = Font(bold=True, color="FFFFFF")
    navy_fill = PatternFill("solid", fgColor=NAVY)
    light_fill = PatternFill("solid", fgColor=LIGHT)
    money = '#,##0.00'

    headers = ["Date", "No. of Books", "Books Ordered", "Subtotal (₹)", "Shipping (₹)"]
    if disc:
        headers.append("Discount (₹)")
    headers.append("G. Total (₹)")
    n = len(headers)
    last = get_column_letter(n)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Report"

    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = f"ISKCON Book Store — Sales Report: {rep['period_label']}"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws.merge_cells(f"A2:{last}2")
    ws["A2"] = (f"Orders included: {rep['include_label']}   |   "
                f"Generated: {(datetime.utcnow() + _IST_OFFSET).strftime('%d-%m-%Y %H:%M')} IST")
    ws["A2"].font = Font(italic=True, color="595959")

    hr = 4
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=hr, column=c, value=h)
        cell.font, cell.fill, cell.border = white_bold, navy_fill, border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[hr].height = 24

    r = hr + 1
    for row in rep["rows"]:
        vals = [row["date"], row["count"], "\n".join(row["lines"]), row["subtotal"], row["shipping"]]
        if disc:
            vals.append(row["discount"])
        vals.append(row["total"])
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=(c == 3),
                                       horizontal="center" if c in (1, 2) else ("left" if c == 3 else "right"))
            if c >= 4:
                cell.number_format = money
        r += 1

    # TOTAL row (navy, like the office sheet)
    tot = ["TOTAL", t["books"], f"{t['orders']} order{'s' if t['orders'] != 1 else ''}", t["subtotal"], t["shipping"]]
    if disc:
        tot.append(t["discount"])
    tot.append(t["total"])
    for c, v in enumerate(tot, 1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.fill, cell.border = white_bold, navy_fill, border
        cell.alignment = Alignment(horizontal="center" if c <= 2 else ("left" if c == 3 else "right"), vertical="center")
        if c >= 4:
            cell.number_format = money
    ws.row_dimensions[r].height = 22
    r += 2

    def section(title):
        nonlocal r
        ws.merge_cells(f"A{r}:{last}{r}")
        c = ws.cell(row=r, column=1, value=title)
        c.font, c.fill = Font(bold=True, color=NAVY, size=12), light_fill
        r += 1

    def line(label, *vals, bold=False, fmts=None):
        """label spans A:C, values go to D, E, F ..."""
        nonlocal r
        ws.merge_cells(f"A{r}:C{r}")
        lc = ws.cell(row=r, column=1, value=label)
        lc.border = border
        lc.font = Font(bold=bold)
        for k in range(2, 4):
            ws.cell(row=r, column=k).border = border
        for k, v in enumerate(vals):
            cell = ws.cell(row=r, column=4 + k, value=v)
            cell.border = border
            cell.font = Font(bold=bold)
            cell.alignment = Alignment(horizontal="right")
            if fmts and fmts[k]:
                cell.number_format = fmts[k]
        r += 1

    def head(label, *cols):
        nonlocal r
        ws.merge_cells(f"A{r}:C{r}")
        for k in range(1, 4):
            ws.cell(row=r, column=k).border = border
            ws.cell(row=r, column=k).fill = navy_fill
        ws.cell(row=r, column=1, value=label).font = white_bold
        for k, h in enumerate(cols):
            cell = ws.cell(row=r, column=4 + k, value=h)
            cell.font, cell.fill, cell.border = white_bold, navy_fill, border
            cell.alignment = Alignment(horizontal="center")
        r += 1

    section("SUMMARY — " + rep["period_label"])
    head("Overall", "Value")
    line("Total orders", t["orders"])
    line("Total books / copies", t["books"])
    line("Subtotal (₹)", t["subtotal"], fmts=[money])
    if disc:
        line("Discount (₹)", t["discount"], fmts=[money])
    line("Shipping (₹)", t["shipping"], fmts=[money])
    line("GRAND TOTAL (₹)", t["total"], bold=True, fmts=[money])
    line("Average order value (₹)", t["avg_order"], fmts=[money])
    r += 1
    head("Format-wise", "Copies")
    for k, v in rep["formats"].items():
        if v:
            line(k, v)
    r += 1
    head("Language-wise", "Copies")
    for k, v in rep["languages"]:
        line(k, v)
    r += 1
    head("Book-wise", "Copies", "Sales (₹)")
    for title, d in rep["books"]:
        line(title, d["qty"], round(d["amount"], 2), fmts=[None, money])
    if rep["combos"]:
        r += 1
        head("Combos sold", "Qty", "Sales (₹)")
        for title, d in rep["combos"]:
            line(title, d["qty"], round(d["amount"], 2), fmts=[None, money])
        line("Note: books inside combos are counted under Book-wise copies (sales shown against the combo).")
    r += 1
    head("Payment method-wise", "Orders", "Total (₹)")
    for k, d in rep["payments"]:
        line(k, d["orders"], round(d["total"], 2), fmts=[None, money])
    r += 1
    head("Order status-wise", "Orders")
    for k, v in rep["statuses"]:
        line(k, v)

    widths = {1: 18, 2: 14, 3: 70, 4: 16, 5: 14}
    if disc:
        widths[6], widths[7] = 14, 16
    else:
        widths[6] = 16
    for c, w in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = f"{hr}:{hr}"

    buf = io.BytesIO()
    wb.save(buf)
    tag = f"{year}-{month:02d}" if month else f"{year}_full-year"
    return Response(buf.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=sales_report_{tag}.xlsx"})


@app.route("/admin/orders/export-csv")
@admin_required
def export_orders_csv():
    """Download the Order Report as CSV — respects every filter and the sort
    order currently applied, so the file matches exactly what's on screen."""
    from flask import Response

    sort = request.args.get("sort", "date_desc")
    oq = build_order_report_query(request.args)
    _, order_clause = ORDER_SORT_OPTIONS.get(sort, ORDER_SORT_OPTIONS["date_desc"])
    all_orders = oq.order_by(order_clause).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Order #", "Date", "Customer Name", "Age", "Phone", "Email",
        "Address", "City", "State", "Pincode",
        "Product Type", "Books Ordered", "Combo Details",
        "Subtotal (INR)", "Shipping (INR)", "Discount (INR)", "Total (INR)",
        "Payment Method", "Payment Status",
        "Order Status", "Coupon Code", "Notes"
    ])

    for order in all_orders:
        display_items = order.display_items
        books_list = "; ".join(
            f"{item.book_title} x{item.quantity}" for item in display_items
        )
        combo_lines = []
        for item in display_items:
            if item.combo_id and item.combo:
                contents = ", ".join(
                    f"{ci.book.title} x{ci.quantity * item.quantity}"
                    for ci in item.combo.combo_items if ci.book
                )
                combo_lines.append(f"{item.book_title}: {contents}")
        combo_details = " | ".join(combo_lines)

        writer.writerow([
            order.order_number,
            order.created_at.strftime("%d-%m-%Y %H:%M"),
            order.customer_name,
            order.age or "",
            order.customer_phone,
            order.customer_email or "",
            order.address,
            order.city or "",
            order.state or "",
            order.pincode or "",
            order.product_type,
            books_list,
            combo_details,
            int(order.subtotal),
            int(order.shipping_charge),
            int(order.discount_amount),
            int(order.total_amount),
            order.payment_method.upper(),
            order.payment_status.upper(),
            order.order_status.capitalize(),
            order.coupon_code or "",
            order.notes or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    stamp    = datetime.now().strftime("%Y%m%d_%H%M")
    suffix   = "_filtered" if any(request.args.get(k) for k in ORDER_REPORT_FILTER_KEYS) else ""
    filename = f"order_report{suffix}_{stamp}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("admin/order_detail.html", order=order)


@app.route("/admin/orders/<int:order_id>/update-contact", methods=["POST"])
@admin_required
def admin_update_order_contact(order_id):
    """Let admin correct customer name/phone/email on an existing order —
    e.g. a mistyped mobile number entered before checkout validation caught it."""
    order = Order.query.get_or_404(order_id)

    name  = request.form.get("customer_name", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    email = request.form.get("customer_email", "").strip()

    if not name:
        flash("Name cannot be empty.", "danger")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    normalized_phone = valid_indian_phone(phone)
    if not normalized_phone:
        flash("Please enter a valid 10-digit mobile number.", "danger")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    if not valid_email(email):
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    order.customer_name  = name
    order.customer_phone = normalized_phone
    order.customer_email = email or None
    db.session.commit()
    flash("Customer contact details updated.", "success")
    return redirect(url_for("admin_order_detail", order_id=order_id))


@app.route("/admin/orders/<int:order_id>/ebook/<int:item_id>/reset-download", methods=["POST"])
@admin_required
def admin_reset_ebook_download(order_id, item_id):
    """Re-activate a single-use eBook download link for one order item."""
    order = Order.query.get_or_404(order_id)
    item = next((i for i in order.items if i.id == item_id), None)
    if not item:
        abort(404)
    item.ebook_downloaded_at = None
    db.session.commit()
    flash(f"Download link reset for \"{item.book_title}\" — customer can download it again.", "success")
    return redirect(url_for("admin_order_detail", order_id=order_id))


@app.route("/admin/orders/update/<int:order_id>", methods=["POST"])
@admin_required
def admin_update_order(order_id):
    order               = Order.query.get_or_404(order_id)
    prev_order_status   = order.order_status
    prev_payment_status = order.payment_status

    new_order_status    = request.form.get("order_status", order.order_status)
    new_payment_status  = request.form.get("payment_status", order.payment_status)

    order.order_status   = new_order_status
    order.payment_status = new_payment_status
    order.status_note    = request.form.get("status_note", "").strip() or None
    order.courier_name   = request.form.get("courier_name", "").strip() or None
    order.tracking_number = request.form.get("tracking_number", "").strip() or None

    shipping_raw = request.form.get("shipping_charge", "").strip()
    if shipping_raw:
        try:
            new_shipping = max(0.0, float(shipping_raw))
        except ValueError:
            new_shipping = order.shipping_charge
        if new_shipping != order.shipping_charge:
            order.shipping_charge = new_shipping
            order.total_amount = order.subtotal + order.shipping_charge - order.discount_amount

    exp_del = request.form.get("expected_delivery", "").strip()
    if exp_del:
        try:
            from datetime import date
            order.expected_delivery = date.fromisoformat(exp_del)
        except ValueError:
            pass
    else:
        order.expected_delivery = None

    # Physical stock is deducted once the order first reaches shipped/delivered,
    # and restored if it's reverted back before that (see deduct/restore_order_stock).
    SHIPPED_OR_LATER = ("shipped", "delivered")
    if new_order_status in SHIPPED_OR_LATER and prev_order_status not in SHIPPED_OR_LATER:
        deduct_order_stock(order)
    elif new_order_status not in SHIPPED_OR_LATER and prev_order_status in SHIPPED_OR_LATER:
        restore_order_stock(order)

    db.session.commit()

    # Respect the admin's "Send email notification" checkbox
    notify = request.form.get("send_email") == "1"

    if notify:
        try:
            do_confirm = False
            do_ship    = False
            do_deliver = False

            if prev_order_status != new_order_status:
                if new_order_status == "confirmed":
                    do_confirm = True
                elif new_order_status == "shipped":
                    do_ship = True
                elif new_order_status == "delivered":
                    do_deliver = True

            # Also fire confirmation when admin manually marks payment as Paid
            # (covers UPI/manual cases where order_status was already "confirmed")
            if (new_payment_status == "paid"
                    and prev_payment_status != "paid"
                    and new_order_status in ("placed", "confirmed")
                    and not do_confirm):
                do_confirm = True

            if do_confirm:
                send_order_confirmation(order)
                if order.customer_email:
                    flash(f"Confirmation email queued for {order.customer_email}", "info")
            if do_ship:
                send_order_shipped(order)
                if order.customer_email:
                    flash(f"Shipped email queued for {order.customer_email}", "info")
            if do_deliver:
                send_order_delivered(order)
                if order.customer_email:
                    flash(f"Delivered email queued for {order.customer_email}", "info")
        except Exception as e:
            app.logger.error(f"[EMAIL] Unexpected error in admin_update_order: {e}")
            flash("Order saved, but email notification failed. Check logs.", "warning")

    flash("Order updated.", "success")
    return redirect(url_for("admin_order_detail", order_id=order_id))


@app.route("/admin/orders/delete/<int:order_id>", methods=["POST"])
@admin_required
def admin_delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_number = order.order_number
    try:
        order.is_deleted = True
        db.session.commit()
        flash(f"Order {order_number} moved to Trash. Restore it from the Trash tab if needed.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Could not delete order: {e}", "danger")
    return redirect(url_for("admin_orders"))


@app.route("/admin/orders/<int:order_id>/delhivery/book", methods=["POST"])
@admin_required
def admin_delhivery_book(order_id):
    """Book a Delhivery Prepaid pickup for this order."""
    from delhivery import create_shipment
    order = Order.query.get_or_404(order_id)
    if order.tracking_number and order.courier_name == "Delhivery":
        flash(f"Delhivery shipment already booked: {order.tracking_number}", "info")
        return redirect(url_for("admin_order_detail", order_id=order_id))
    waybill, err = create_shipment(order)
    if waybill:
        order.courier_name    = "Delhivery"
        order.tracking_number = waybill
        order.order_status    = "shipped"
        deduct_order_stock(order)
        db.session.commit()
        send_order_shipped(order)
        flash(f"Delhivery pickup booked! Waybill: {waybill}", "success")
    else:
        flash(f"Delhivery booking failed: {err}", "danger")
    return redirect(url_for("admin_order_detail", order_id=order_id))


@app.route("/admin/orders/<int:order_id>/delhivery/track")
@admin_required
def admin_delhivery_track(order_id):
    """AJAX: return live tracking JSON for this order's Delhivery waybill."""
    from delhivery import track_shipment
    order = Order.query.get_or_404(order_id)
    if not order.tracking_number:
        return jsonify({"error": "No Delhivery waybill on this order"})
    result, err = track_shipment(order.tracking_number)
    if err:
        return jsonify({"error": err})
    return jsonify(result)


@app.route("/admin/orders/<int:order_id>/delhivery/cancel", methods=["POST"])
@admin_required
def admin_delhivery_cancel(order_id):
    """Cancel a booked Delhivery shipment and revert order status."""
    from delhivery import cancel_shipment
    order = Order.query.get_or_404(order_id)
    if not order.tracking_number:
        flash("No Delhivery waybill to cancel.", "warning")
        return redirect(url_for("admin_order_detail", order_id=order_id))
    success, msg = cancel_shipment(order.tracking_number)
    if success:
        order.courier_name    = None
        order.tracking_number = None
        order.order_status    = "confirmed"
        restore_order_stock(order)
        db.session.commit()
        flash("Delhivery shipment cancelled. Order reverted to Confirmed.", "success")
    else:
        flash(f"Cancellation failed: {msg}", "danger")
    return redirect(url_for("admin_order_detail", order_id=order_id))


def sync_delhivery_deliveries():
    """
    Poll Delhivery API for all 'shipped' Delhivery orders and auto-mark them
    delivered when Delhivery confirms delivery. Safe to call from background thread.
    Returns count of orders updated.
    """
    from delhivery import track_shipment
    updated = 0
    with app.app_context():
        shipped_orders = Order.query.filter_by(
            courier_name="Delhivery",
            order_status="shipped",
            is_deleted=False,
        ).all()
        for order in shipped_orders:
            if not order.tracking_number:
                continue
            try:
                result, err = track_shipment(order.tracking_number)
                if err or not result:
                    continue
                status = (result.get("status") or "").strip().lower()
                if "delivered" in status:
                    order.order_status = "delivered"
                    db.session.commit()
                    updated += 1
                    # Email notification
                    try:
                        send_order_delivered(order)
                    except Exception:
                        pass
                    # WhatsApp notification
                    notify_admin_whatsapp(
                        f"📦 Order Delivered (auto-sync)!\n"
                        f"Order: {order.order_number}\n"
                        f"Customer: {order.customer_name} | {order.customer_phone}\n"
                        f"Waybill: {order.tracking_number}"
                    )
                    app.logger.info(f"[DELHIVERY SYNC] Auto-delivered order {order.order_number}")
            except Exception as e:
                app.logger.error(f"[DELHIVERY SYNC] Error checking {order.order_number}: {e}")
    return updated


@app.route("/admin/sync-delhivery", methods=["POST"])
@admin_required
def admin_sync_delhivery():
    """Manually trigger Delhivery delivery sync from the admin orders page."""
    updated = sync_delhivery_deliveries()
    if updated:
        flash(f"✅ {updated} order(s) auto-marked as Delivered from Delhivery tracking.", "success")
    else:
        flash("No new deliveries found — all shipped orders still in transit.", "info")
    return redirect(url_for("admin_orders"))


@app.route("/cron/sync-delhivery")
def cron_sync_delhivery():
    """
    Called by Railway Cron on a schedule (e.g. every 2 hours).
    Protected by CRON_SECRET token in the Authorization header or ?token= query param.
    """
    cron_secret = app.config.get("CRON_SECRET", "")
    if not cron_secret:
        return jsonify({"error": "CRON_SECRET not configured"}), 500

    provided = (
        request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or request.args.get("token", "").strip()
    )
    if not hmac.compare_digest(provided, cron_secret):
        return jsonify({"error": "Unauthorized"}), 401

    updated = sync_delhivery_deliveries()
    return jsonify({"ok": True, "delivered": updated})


@app.route("/admin/orders/trash")
@admin_required
def admin_trash_orders():
    page    = request.args.get("page", 1, type=int)
    deleted = Order.query.filter_by(is_deleted=True).order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/trash_orders.html", orders=deleted)


@app.route("/admin/orders/restore/<int:order_id>", methods=["POST"])
@admin_required
def admin_restore_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.is_deleted = False
    db.session.commit()
    flash(f"Order {order.order_number} restored successfully.", "success")
    return redirect(url_for("admin_trash_orders"))


@app.route("/admin/orders/hard-delete/<int:order_id>", methods=["POST"])
@admin_required
def admin_hard_delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_number = order.order_number
    OrderItem.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)
    db.session.commit()
    flash(f"Order {order_number} permanently deleted.", "danger")
    return redirect(url_for("admin_trash_orders"))


# ── Admin: Coupons ──

@app.route("/admin/coupons")
@admin_required
def admin_coupons():
    coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    return render_template("admin/coupons.html", coupons=coupons)


@app.route("/admin/coupons/add", methods=["POST"])
@admin_required
def admin_add_coupon():
    expires_str = request.form.get("expires_at", "")
    coupon = Coupon(
        code           = request.form["code"].strip().upper(),
        description    = request.form.get("description", ""),
        discount_type  = request.form.get("discount_type", "percent"),
        discount_value = float(request.form["discount_value"]),
        min_order      = float(request.form.get("min_order", 0)),
        max_discount   = float(request.form["max_discount"]) if request.form.get("max_discount") else None,
        max_uses       = int(request.form.get("max_uses", 100)),
        active         = bool(request.form.get("active")),
        auto_apply     = bool(request.form.get("auto_apply")),
        expires_at     = datetime.strptime(expires_str, "%Y-%m-%d") if expires_str else None,
    )
    db.session.add(coupon)
    db.session.commit()
    flash(f'Coupon "{coupon.code}" created!', "success")
    return redirect(url_for("admin_coupons"))


@app.route("/admin/coupons/delete/<int:coupon_id>", methods=["POST"])
@admin_required
def admin_delete_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    flash("Coupon deleted.", "info")
    return redirect(url_for("admin_coupons"))


@app.route("/admin/backup")
@admin_required
def admin_backup():
    """Download full backup as ZIP containing orders, books, and coupons CSV files."""
    from flask import Response

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        # ── 1. Orders CSV ──
        orders_buf = io.StringIO()
        w = csv.writer(orders_buf)
        w.writerow([
            "Order #", "Date", "Customer Name", "Phone", "Email",
            "Address", "City", "State", "Pincode", "Age", "Profession", "Books Ordered",
            "Subtotal (INR)", "Shipping (INR)", "Discount (INR)", "Total (INR)",
            "Payment Method", "Payment Status", "Order Status", "Coupon Code", "Notes"
        ])
        for order in Order.query.order_by(Order.created_at.desc()).all():
            books_list = "; ".join(f"{i.book_title} x{i.quantity}" for i in order.items)
            w.writerow([
                order.order_number,
                order.created_at.strftime("%d-%m-%Y %H:%M"),
                order.customer_name, order.customer_phone, order.customer_email or "",
                order.address, order.city or "", order.state or "", order.pincode or "",
                order.age or "", order.profession or "",
                books_list,
                int(order.subtotal), int(order.shipping_charge),
                int(order.discount_amount), int(order.total_amount),
                order.payment_method.upper(), order.payment_status.upper(),
                order.order_status.capitalize(), order.coupon_code or "", order.notes or "",
            ])
        zf.writestr("orders.csv", orders_buf.getvalue().encode("utf-8-sig"))

        # ── 2. Books CSV ──
        books_buf = io.StringIO()
        w = csv.writer(books_buf)
        w.writerow([
            "ID", "Title", "Author", "Category", "Language",
            "Price (INR)", "Original Price (INR)", "Stock", "Pages",
            "ISBN", "Publisher", "Featured", "Active", "Is eBook"
        ])
        for book in Book.query.order_by(Book.id).all():
            w.writerow([
                book.id, book.title, book.author,
                book.category.name if book.category else "",
                book.language or "", int(book.price),
                int(book.original_price) if book.original_price else "",
                book.stock, book.pages or "",
                book.isbn or "", book.publisher or "",
                "Yes" if book.featured else "No",
                "Yes" if book.active else "No",
                "Yes" if book.is_ebook else "No",
            ])
        zf.writestr("books.csv", books_buf.getvalue().encode("utf-8-sig"))

        # ── 3. Coupons CSV ──
        coupons_buf = io.StringIO()
        w = csv.writer(coupons_buf)
        w.writerow([
            "Code", "Description", "Type", "Discount Value",
            "Min Order (INR)", "Max Discount (INR)", "Max Uses", "Times Used", "Active"
        ])
        for c in Coupon.query.order_by(Coupon.id).all():
            w.writerow([
                c.code, c.description or "", c.discount_type,
                c.discount_value, int(c.min_order) if c.min_order else 0,
                int(c.max_discount) if c.max_discount else "",
                c.max_uses or "", c.used_count, "Yes" if c.active else "No",
            ])
        zf.writestr("coupons.csv", coupons_buf.getvalue().encode("utf-8-sig"))

    zip_buffer.seek(0)
    filename = f"iskcon_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return Response(
        zip_buffer.read(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─────────────────────────────────────────────
# UTILITY ROUTES
# ─────────────────────────────────────────────

@app.route("/api/cart-count")
def api_cart_count():
    return jsonify({"count": cart_item_count()})


# ─────────────────────────────────────────────
# SMART (SPELLING-TOLERANT) BOOK SEARCH
# Sanskrit/Hindi names are spelled many ways (Bhagavad / Bhagavat / Bhagvad /
# Bhagwad, Gita / Geeta, Gujarati / Gujrati ...), so we compare a phonetic
# "skeleton" of each word instead of the raw text, plus a light typo check.
# Works on SQLite and PostgreSQL alike (matching is done in Python).
# ─────────────────────────────────────────────
import re as _re
import time as _time
import unicodedata as _unicodedata
from difflib import SequenceMatcher as _SequenceMatcher

_SEARCH_INDEX = {"built": 0.0, "rows": []}
_SEARCH_INDEX_TTL = 30  # seconds — new/edited books appear in search within 30s


def _search_tokens(text):
    text = _unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not _unicodedata.combining(ch)).lower()
    return _re.findall(r"\w+", text)


def _skeleton(word):
    """Rough phonetic key: bhagavad/bhagavat/bhagvad/bhagwat -> 'bgvd'."""
    if not word.isascii():
        return word
    w = word.replace("w", "v").replace("ph", "f").replace("h", "")
    for a, b in (("q", "k"), ("c", "k"), ("z", "s"), ("t", "d"), ("x", "ks")):
        w = w.replace(a, b)
    w = _re.sub(r"[aeiouy]", "", w)
    w = _re.sub(r"(.)\1+", r"\1", w)
    return w or word


def _token_score(qt, qs, tt, ts):
    """How well query word qt (skeleton qs) matches one stored word tt (skeleton ts)."""
    if qt == tt:
        return 3.0
    if len(qt) >= 2 and qt in tt:
        return 2.5 if tt.startswith(qt) else 2.0
    if len(qt) <= 2:
        return 0.0
    if qs == ts:
        return 2.0
    if len(qs) >= 2 and ts.startswith(qs):
        return 1.5
    if len(qt) >= 4 and _SequenceMatcher(None, qt, tt).ratio() >= 0.8:
        return 1.2
    if len(qs) >= 4 and len(ts) >= 4 and _SequenceMatcher(None, qs, ts).ratio() >= 0.8:
        return 1.0
    return 0.0


def _search_index():
    now = _time.time()
    if now - _SEARCH_INDEX["built"] > _SEARCH_INDEX_TTL or not _SEARCH_INDEX["rows"]:
        rows = []
        for b in Book.query.filter_by(active=True, deleted=False).all():
            fmt = "eBook" if b.is_ebook else "Paperback"
            words = []
            for text, weight in ((b.title, 1.0), (b.author, 0.5),
                                 (b.language, 0.8), (fmt, 0.8)):
                for tok in _search_tokens(text):
                    words.append((tok, _skeleton(tok), weight))
            rows.append({"id": b.id, "title": b.title or "", "author": b.author or "",
                         "language": b.language or "", "fmt": fmt,
                         "norm_title": " ".join(_search_tokens(b.title)), "words": words})
        _SEARCH_INDEX["rows"] = rows
        _SEARCH_INDEX["built"] = now
    return _SEARCH_INDEX["rows"]


# Filler words people type that books rarely contain — never reject a book because of them.
_SEARCH_FILLER = {"book", "books", "pustak", "granth", "the", "of", "by", "and", "in",
                  "for", "a", "an", "shri", "shree", "sri", "sree", "srila", "swami", "sripad"}


def _query_forms(qt):
    """The word as typed, plus a singular form (books -> book)."""
    forms = [(qt, _skeleton(qt))]
    if len(qt) > 3 and qt.endswith("s") and not qt.endswith("ss"):
        forms.append((qt[:-1], _skeleton(qt[:-1])))
    return forms


def smart_search(query, limit=None):
    """Return matching index rows, best first.

    1. Rows where every meaningful query word matches (filler words like
       'book' / 'shri' are optional).
    2. If none, rows matching at least one meaningful word (best first), so a
       search with one odd word still shows relevant books.
    """
    qtokens = _search_tokens(query)
    if not qtokens:
        return []
    qwords = [(t, _query_forms(t), t in _SEARCH_FILLER) for t in qtokens]
    core = [w for w in qwords if not w[2]] or qwords      # all-filler query: treat words as required
    phrase = " ".join(qtokens)
    core_phrase = " ".join(t for t in qtokens if t not in _SEARCH_FILLER) or phrase
    full, partial = [], []
    for row in _search_index():
        total, matched, missed = 0.0, 0, 0
        for qt, forms, is_filler in qwords:
            best = 0.0
            for tt, ts, weight in row["words"]:
                for f, fs in forms:
                    sc = _token_score(f, fs, tt, ts) * weight
                    if sc > best:
                        best = sc
            if best > 0:
                total += best
                if (qt, forms, is_filler) in core:
                    matched += 1
            elif (qt, forms, is_filler) in core:
                missed += 1
        if matched == 0:
            continue
        if phrase in row["norm_title"]:
            total += 3
        if row["norm_title"].startswith(core_phrase):
            total += 3
        entry = (-total, row["title"].lower(), row)
        if missed == 0:
            full.append(entry)
        else:
            partial.append((missed, ) + entry)
    if full:
        full.sort(key=lambda x: (x[0], x[1]))
        rows = [x[2] for x in full]
    else:
        partial.sort(key=lambda x: (x[0], x[1], x[2]))
        rows = [x[3] for x in partial]
    return rows[:limit] if limit else rows


@app.route("/api/search-suggestions")
def search_suggestions():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    results = [{"title": b["title"], "author": b["author"], "id": b["id"],
                "meta": f'{b["language"]} · {b["fmt"]}' if b["language"] else b["fmt"]}
               for b in smart_search(q, limit=8)]
    return jsonify(results)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# ─────────────────────────────────────────────
# ADMIN — CUSTOMERS
# ─────────────────────────────────────────────

@app.route("/admin/customers")
@admin_required
def admin_customers():
    q    = request.args.get("q", "").strip()
    tier = request.args.get("tier", "")

    cq = Customer.query
    if q:
        pattern = f"%{q}%"
        cq = cq.filter(
            or_(Customer.name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern))
        )
    if tier:
        cq = cq.filter_by(tier=tier)

    customers = cq.order_by(Customer.created_at.desc()).all()
    return render_template("admin/customers.html",
                           customers=customers,
                           q=q, tier=tier,
                           active_page="customers")


# ─────────────────────────────────────────────
# INIT DB & RUN
# ─────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist, and add any missing columns."""
    with app.app_context():
        try:
            db.create_all()
            print("[OK] Database tables created.")
        except Exception as e:
            print(f"[ERROR] db.create_all() failed: {e}")

        # Add new columns to existing tables if they don't exist (safe for PostgreSQL & SQLite)
        migrations = [
            ("orders", "courier_name",       "VARCHAR(100)"),
            ("orders", "tracking_number",    "VARCHAR(100)"),
            ("orders", "expected_delivery",  "DATE"),
            ("orders", "upi_transaction_id", "VARCHAR(100)"),
            ("orders", "is_deleted",         "BOOLEAN DEFAULT FALSE"),
            ("books",  "deleted",            "BOOLEAN DEFAULT FALSE"),
            ("books",  "is_ebook",           "BOOLEAN DEFAULT FALSE"),
            ("books",  "ebook_file",         "VARCHAR(200)"),
            ("books",              "preview_file", "VARCHAR(200)"),
            ("books",              "weight_kg",    "FLOAT DEFAULT 0.5"),
            ("stock_receipts",     "batch_ref",    "VARCHAR(20)"),
            ("orders",             "customer_id",        "INTEGER"),
            ("customers",          "reset_token",        "VARCHAR(64)"),
            ("customers",          "reset_token_expires","TIMESTAMP"),
            ("customers",          "saved_address",      "TEXT"),
            ("customers",          "saved_city",         "VARCHAR(100)"),
            ("customers",          "saved_state",        "VARCHAR(100)"),
            ("customers",          "saved_pincode",      "VARCHAR(10)"),
            ("orders",             "status_note",        "TEXT"),
            ("books",              "review_text",        "TEXT"),
            ("books",              "review_video",       "VARCHAR(200)"),
            ("books",              "review_video_url",   "VARCHAR(500)"),
            ("books",              "review_video_url2",  "VARCHAR(500)"),
            ("books",              "review_video_url3",  "VARCHAR(500)"),
            ("orders",             "is_donation",                "BOOLEAN DEFAULT FALSE"),
            ("orders",             "donation_type",              "VARCHAR(20)"),
            ("orders",             "donation_recipient",         "VARCHAR(200)"),
            ("orders",             "donation_recipient_address", "TEXT"),
            ("orders",             "donor_message",              "TEXT"),
            ("whatsapp_inquiries", "status",                     "VARCHAR(20) DEFAULT 'open'"),
            ("whatsapp_inquiries", "admin_note",                 "TEXT"),
            ("coupons",            "auto_apply",                 "BOOLEAN DEFAULT FALSE"),
            ("admin_sessions",     "token",                      "VARCHAR(64)"),
            ("admin_sessions",     "ip_address",                 "VARCHAR(45)"),
            ("admin_sessions",     "login_at",                   "TIMESTAMP"),
            ("admin_sessions",     "last_seen",                  "TIMESTAMP"),
            ("order_items",        "ebook_downloaded_at",        "TIMESTAMP"),
            ("orders",             "age",                        "INTEGER"),
            ("orders",             "profession",                 "VARCHAR(100)"),
            ("whatsapp_inquiries", "address",                    "TEXT"),
            ("whatsapp_inquiries", "city",                       "VARCHAR(100)"),
            ("whatsapp_inquiries", "state",                      "VARCHAR(100)"),
            ("whatsapp_inquiries", "pincode",                    "VARCHAR(10)"),
            ("whatsapp_inquiries", "shipping_rate",              "FLOAT"),
            ("whatsapp_inquiries", "customer_email",             "VARCHAR(200)"),
            ("whatsapp_inquiries", "age",                        "INTEGER"),
            ("whatsapp_inquiries", "profession",                 "VARCHAR(100)"),
            ("orders",             "stock_deducted",             "BOOLEAN DEFAULT FALSE"),
            ("order_items",        "combo_id",                   "INTEGER"),
            ("order_items",        "is_combo_component",         "BOOLEAN DEFAULT FALSE"),
            ("combos",             "featured",                   "BOOLEAN DEFAULT FALSE"),
            ("gita_yagna_donations", "distribution", "VARCHAR(10) DEFAULT 'local'"),
            ("gita_yagna_donations", "courier_charge", "FLOAT DEFAULT 0"),
            ("gita_yagna_donations", "parcel_kg", "FLOAT"),
            ("gita_yagna_donations", "recipient_name", "VARCHAR(200)"),
            ("gita_yagna_donations", "recipient_phone", "VARCHAR(20)"),
            ("gita_yagna_donations", "recipient_address", "TEXT"),
            ("gita_yagna_donations", "recipient_city", "VARCHAR(100)"),
            ("gita_yagna_donations", "recipient_state", "VARCHAR(100)"),
            ("gita_yagna_donations", "recipient_pincode", "VARCHAR(10)"),
        ]
        for table, column, col_type in migrations:
            # Use a fresh connection per column so a failed ALTER doesn't
            # leave the transaction in an aborted state (PostgreSQL issue)
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    conn.commit()
                    print(f"[MIGRATE] Added column {table}.{column}")
            except Exception:
                pass  # Column already exists — ignore

        # Seed first magazine if none exist
        try:
            if Magazine.query.count() == 0:
                db.session.add(Magazine(
                    title="The God Question",
                    issue_label="Issue 1 · 2026",
                    description="Explore the most profound question ever asked — Does God exist? "
                                "This special magazine examines science, philosophy, and Vedic "
                                "wisdom to shine light on the ultimate truth.",
                    pdf_filename="the-god-question.pdf",
                    single_price=49.0,
                    is_free=False,
                    active=True,
                ))
                db.session.commit()
                print("[SEED] Added first magazine: The God Question")
        except Exception as e:
            db.session.rollback()
            print(f"[WARNING] Magazine seed failed: {e}")

        # Patch existing magazine issue_label from 2025 → 2026
        try:
            mag = Magazine.query.filter_by(issue_label="Issue 1 · 2025").first()
            if mag:
                mag.issue_label = "Issue 1 · 2026"
                db.session.commit()
                print("[MIGRATE] Updated magazine issue_label to 2026")
        except Exception as e:
            db.session.rollback()
            print(f"[WARNING] Magazine label patch failed: {e}")

        # Backfill any NULL is_deleted values so filter_by(is_deleted=False) works correctly
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("UPDATE orders SET is_deleted = FALSE WHERE is_deleted IS NULL"))
                conn.commit()
        except Exception:
            pass

        # Backfill: mark all-ebook orders Delivered if every item was already
        # downloaded before the auto-deliver logic existed (or was deployed
        # mid-download), so they don't get stuck showing Placed/Confirmed forever.
        try:
            candidates = Order.query.filter(Order.order_status.in_(["placed", "confirmed"])).all()
            for o in candidates:
                if o.items and all(
                    i.book and i.book.is_ebook and i.ebook_downloaded_at is not None
                    for i in o.items
                ):
                    o.order_status = "delivered"
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[WARNING] eBook delivered-status backfill failed: {e}")

        # One-time backfill for the stock-deduction timing fix (order-creation ->
        # ship-time). Orders already shipped/delivered had stock correctly taken
        # under the old logic, so just flag them. Orders that never shipped
        # (still open, or abandoned/cancelled) had stock wrongly taken at
        # creation and never given back — restore it. Runs exactly once,
        # guarded by a Setting marker so restarts never repeat it.
        try:
            MARKER = "stock_ship_time_backfill_2026_08_11"
            if not Setting.get(MARKER):
                shipped_marked, restored_orders, restored_units = 0, 0, 0
                for o in Order.query.filter(Order.order_status.in_(("shipped", "delivered"))).all():
                    if not o.stock_deducted:
                        o.stock_deducted = True
                        shipped_marked += 1
                for o in Order.query.filter(~Order.order_status.in_(("shipped", "delivered"))).all():
                    if o.stock_deducted:
                        continue
                    units = 0
                    for item in o.items:
                        book = item.book
                        if book and not book.is_ebook:
                            book.stock += item.quantity
                            units += item.quantity
                    if units:
                        restored_orders += 1
                        restored_units += units
                Setting.set(MARKER, f"shipped_marked={shipped_marked} restored_orders={restored_orders} restored_units={restored_units}")
                db.session.commit()
                print(f"[STOCK BACKFILL] shipped_marked={shipped_marked} restored_orders={restored_orders} restored_units={restored_units}")
        except Exception as e:
            db.session.rollback()
            print(f"[WARNING] Stock ship-time backfill failed: {e}")


@app.route("/admin/export-data")
def admin_export_data():
    """
    Export all books and categories as JSON for local sync.
    Protected by a simple token (not admin session — needed for script access).
    Usage: GET /admin/export-data?token=iskcon-sync-2024
    """
    token = request.args.get("token", "")
    if token != "iskcon-sync-2024":
        abort(403)

    categories = []
    for c in Category.query.order_by(Category.sort_order).all():
        categories.append({
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "description": c.description or "",
            "icon": c.icon or "📚",
            "sort_order": c.sort_order,
        })

    books = []
    for b in Book.query.all():
        books.append({
            "id": b.id,
            "title": b.title,
            "author": b.author,
            "description": b.description or "",
            "short_desc": b.short_desc or "",
            "price": b.price,
            "original_price": b.original_price,
            "image": b.image or "default_book.jpg",
            "category_name": b.category.name if b.category else None,
            "isbn": b.isbn or "",
            "language": b.language or "English",
            "pages": b.pages,
            "publisher": b.publisher or "The Bhaktivedanta Book Trust",
            "stock": b.stock,
            "featured": b.featured,
            "active": b.active,
            "deleted": b.deleted,
            "is_ebook": b.is_ebook,
            "ebook_file": b.ebook_file or "",
            "preview_file": b.preview_file or "",
        })

    return jsonify({"categories": categories, "books": books})


@app.route("/admin/carousel", methods=["GET", "POST"])
@admin_required
def admin_carousel():
    all_books = Book.query.filter_by(active=True).order_by(Book.title).all()
    keys = ["carousel_slide_0", "carousel_slide_1", "carousel_slide_2", "carousel_slide_3", "carousel_slide_4"]
    labels = ["Slide 0 — Welcome (brand image)", "Slide 1 — Bhagavad Gita", "Slide 2 — Srimad Bhagavatam", "Slide 3 — Krishna Book", "Slide 4 — Nectar of Devotion"]

    if request.method == "POST":
        for key in keys:
            val = request.form.get(key, "")
            Setting.set(key, val if val else None)
        flash("Carousel books updated successfully.", "success")
        return redirect(url_for("admin_carousel"))

    current = {key: Setting.get(key) for key in keys}
    return render_template("admin/carousel.html",
                           all_books=all_books,
                           keys=keys,
                           labels=labels,
                           current=current,
                           active_page="carousel")


# Auto-init DB when loaded by gunicorn
try:
    init_db()
except Exception as e:
    print(f"[ERROR] init_db failed at startup: {e}")


# Auto-sync Delhivery deliveries every 2 hours in background
def _delhivery_sync_loop():
    import time
    time.sleep(300)  # wait 5 min after boot before first check
    while True:
        try:
            n = sync_delhivery_deliveries()
            if n:
                print(f"[DELHIVERY SYNC] Auto-delivered {n} order(s)")
        except Exception as e:
            print(f"[DELHIVERY SYNC] Error: {e}")
        time.sleep(7200)  # every 2 hours

import threading as _threading
_threading.Thread(target=_delhivery_sync_loop, daemon=True).start()


if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    port  = int(os.environ.get("PORT", 5000))
    host  = os.environ.get("HOST", "0.0.0.0")
    print(f"\n[START] ISKCON Book Store running at http://{host}:{port}")
    print(f"   Admin panel: http://{host}:{port}/admin/\n")
    app.run(host=host, port=port, debug=debug)
