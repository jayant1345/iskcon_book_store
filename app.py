"""
ISKCON Book Store - Complete Flask Application
=============================================
A production-ready e-commerce platform for ISKCON books.
"""

import os
import uuid
import hmac
import hashlib
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, session, redirect,
    url_for, flash, jsonify, abort, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_

# ─────────────────────────────────────────────
# App & Configuration
# ─────────────────────────────────────────────

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "iskcon-books-super-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'iskcon_books.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "images", "books")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024          # 16 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    EBOOK_FOLDER = os.path.join(BASE_DIR, "ebooks")
    ALLOWED_EBOOK_EXTENSIONS = {"pdf", "epub"}
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_your_key_id")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "your_razorpay_secret")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "Hare@Krishna108"))
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "+919999999999")
    UPI_ID   = os.environ.get("UPI_ID", "")
    UPI_NAME = os.environ.get("UPI_NAME", "ISKCON Book Store")
    STORE_NAME = "ISKCON Book Store"
    SHIPPING_CHARGE = float(os.environ.get("SHIPPING_CHARGE", "50"))
    FREE_SHIPPING_ABOVE = float(os.environ.get("FREE_SHIPPING_ABOVE", "500"))


app.config.from_object(Config)

# Fix Heroku/Render postgres:// → postgresql://
db_url = app.config["SQLALCHEMY_DATABASE_URI"]
if db_url.startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url.replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["EBOOK_FOLDER"], exist_ok=True)


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
    publisher      = db.Column(db.String(200), default="The Bhaktivedanta Book Trust")
    stock          = db.Column(db.Integer, default=100)
    featured       = db.Column(db.Boolean, default=False)
    active         = db.Column(db.Boolean, default=True)
    is_ebook       = db.Column(db.Boolean, default=False)
    ebook_file     = db.Column(db.String(200), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    order_items    = db.relationship("OrderItem", backref="book", lazy=True)

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
    items              = db.relationship("OrderItem", backref="order", lazy=True)

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

    @property
    def subtotal(self):
        return self.price * self.quantity


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


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def save_image(file):
    """Save uploaded image and return filename."""
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return filename
    return None


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


def generate_order_number():
    return "ISKCON" + datetime.now().strftime("%Y%m%d") + uuid.uuid4().hex[:6].upper()


# ── Cart helpers (stored in Flask session) ──

def get_cart():
    return session.get("cart", {})


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


def cart_item_count():
    return sum(item["qty"] for item in get_cart().values())


def cart_totals():
    cart = get_cart()
    if not cart:
        return {"subtotal": 0, "shipping": 0, "discount": 0, "total": 0, "items": []}

    book_ids = [int(k) for k in cart.keys()]
    books = {b.id: b for b in Book.query.filter(Book.id.in_(book_ids)).all()}

    items, subtotal = [], 0
    for book_id_str, item in cart.items():
        book = books.get(int(book_id_str))
        if not book:
            continue
        line_total = book.price * item["qty"]
        subtotal += line_total
        items.append({
            "book":       book,
            "qty":        item["qty"],
            "line_total": line_total,
        })

    shipping = 0 if subtotal >= app.config["FREE_SHIPPING_ABOVE"] else app.config["SHIPPING_CHARGE"]
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

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login to access the admin panel.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ── Context processors ──

@app.context_processor
def inject_globals():
    return {
        "cart_count":   cart_item_count(),
        "categories":   Category.query.order_by(Category.sort_order).all(),
        "store_name":   app.config["STORE_NAME"],
        "whatsapp_num": app.config["WHATSAPP_NUMBER"],
        "upi_id":       app.config["UPI_ID"],
        "upi_name":     app.config["UPI_NAME"],
    }


# ─────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    featured_books  = Book.query.filter_by(featured=True, active=True).limit(8).all()
    new_arrivals    = Book.query.filter_by(active=True).order_by(Book.created_at.desc()).limit(6).all()
    categories      = Category.query.order_by(Category.sort_order).all()
    return render_template("index.html",
                           featured_books=featured_books,
                           new_arrivals=new_arrivals,
                           categories=categories)


@app.route("/books")
def books():
    query  = request.args.get("q", "").strip()
    cat    = request.args.get("category", "")
    lang   = request.args.get("language", "")
    sort   = request.args.get("sort", "title")
    page   = request.args.get("page", 1, type=int)

    bq = Book.query.filter_by(active=True)

    if query:
        bq = bq.filter(or_(
            Book.title.ilike(f"%{query}%"),
            Book.author.ilike(f"%{query}%"),
            Book.description.ilike(f"%{query}%"),
        ))
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


@app.route("/book/<int:book_id>")
def book_detail(book_id):
    book    = Book.query.get_or_404(book_id)
    related = Book.query.filter_by(category_id=book.category_id, active=True)\
                        .filter(Book.id != book_id).limit(4).all()
    return render_template("book_detail.html", book=book, related=related)


# ─────────────────────────────────────────────
# CART ROUTES
# ─────────────────────────────────────────────

@app.route("/cart/add/<int:book_id>", methods=["POST"])
def add_to_cart(book_id):
    book = Book.query.get_or_404(book_id)
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
    return redirect(request.referrer or url_for("cart"))


@app.route("/cart")
def cart():
    totals = cart_totals()
    coupon_code = session.get("coupon_code", "")
    return render_template("cart.html", **totals, coupon_code=coupon_code)


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
    # Reset coupon if cart changed
    session.pop("coupon_code", None)
    session.pop("coupon_discount", None)
    flash("Cart updated.", "success")
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
    session.modified = True
    flash(f"Coupon applied! You saved ₹{discount:.0f}.", "success")
    return redirect(url_for("cart"))


# ─────────────────────────────────────────────
# CHECKOUT & PAYMENT
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
        payment = request.form.get("payment_method", "cod")
        app.logger.info(f"[CHECKOUT] payment_method received: '{payment}' | form keys: {list(request.form.keys())}")
        notes   = request.form.get("notes", "").strip()

        if not all([name, phone, address, city, pincode]):
            flash("Please fill all required fields.", "danger")
            return render_template("checkout.html", **totals)

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
            subtotal        = totals["subtotal"],
            shipping_charge = totals["shipping"],
            discount_amount = totals["discount"],
            total_amount    = totals["total"],
            payment_method  = payment,
            coupon_code     = session.get("coupon_code"),
            notes           = notes,
            payment_status  = "pending",
            order_status    = "placed",
        )
        db.session.add(order)
        db.session.flush()  # get order.id

        for cart_item in totals["items"]:
            oi = OrderItem(
                order_id   = order.id,
                book_id    = cart_item["book"].id,
                book_title = cart_item["book"].title,
                quantity   = cart_item["qty"],
                price      = cart_item["book"].price,
            )
            # Reduce stock
            cart_item["book"].stock = max(0, cart_item["book"].stock - cart_item["qty"])
            db.session.add(oi)

        # Update coupon usage
        if order.coupon_code:
            coupon = Coupon.query.filter_by(code=order.coupon_code).first()
            if coupon:
                coupon.used_count += 1

        db.session.commit()

        # Clear cart & coupon from session
        session.pop("cart", None)
        session.pop("coupon_code", None)
        session.pop("coupon_discount", None)

        if payment == "razorpay":
            # Create Razorpay order
            try:
                import razorpay
                client = razorpay.Client(auth=(
                    app.config["RAZORPAY_KEY_ID"],
                    app.config["RAZORPAY_KEY_SECRET"]
                ))
                rp_order = client.order.create({
                    "amount":   int(order.total_amount * 100),  # paise
                    "currency": "INR",
                    "receipt":  order.order_number,
                })
                order.razorpay_order_id = rp_order["id"]
                db.session.commit()
                return render_template("payment_razorpay.html",
                                       order=order,
                                       rp_order=rp_order,
                                       key_id=app.config["RAZORPAY_KEY_ID"])
            except Exception as e:
                # Roll back order and restore cart so user can try again
                db.session.delete(order)
                db.session.commit()
                # Restore cart items in session
                restored_cart = {}
                for item in totals["items"]:
                    key = str(item["book"].id)
                    restored_cart[key] = {"qty": item["qty"], "title": item["book"].title}
                    item["book"].stock += item["qty"]
                db.session.commit()
                session["cart"] = restored_cart
                session.modified = True
                flash(f"Payment gateway error: {e}. Please try again or choose Cash on Delivery.", "danger")
                return redirect(url_for("checkout"))

        flash(f"Order #{order.order_number} placed successfully! 🎉", "success")
        return redirect(url_for("order_success", order_number=order.order_number))

    return render_template("checkout.html", **totals,
                           razorpay_key=app.config["RAZORPAY_KEY_ID"])


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
            return jsonify({"success": True, "redirect": url_for("order_success", order_number=order.order_number)})
    except Exception:
        pass

    order.payment_status = "failed"
    db.session.commit()
    return jsonify({"success": False, "redirect": url_for("payment_failed", order_number=order.order_number)})


@app.route("/order/success/<order_number>")
def order_success(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return render_template("payment_success.html", order=order)


@app.route("/ebook/download/<order_number>/<int:book_id>")
def ebook_download(order_number, book_id):
    order = Order.query.filter_by(order_number=order_number).first_or_404()

    # Access control: COD denied; Razorpay must be paid; UPI allowed (trust-based)
    if order.payment_method == "cod":
        abort(403)
    if order.payment_method == "razorpay" and order.payment_status != "paid":
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

    ext = book.ebook_file.rsplit(".", 1)[1]
    return send_from_directory(
        app.config["EBOOK_FOLDER"],
        book.ebook_file,
        as_attachment=True,
        download_name=f"{book.title}.{ext}"
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
        order = Order.query.filter(
            or_(Order.order_number == query, Order.customer_phone == query)
        ).order_by(Order.created_at.desc()).first()
        if not order:
            flash("No order found with that order number or phone.", "warning")
    return render_template("order_tracking.html", order=order)


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
            flash("Welcome back, Admin! 🙏", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    total_orders   = Order.query.count()
    total_revenue  = db.session.query(db.func.sum(Order.total_amount))\
                                .filter(Order.payment_status != "failed").scalar() or 0
    total_books    = Book.query.filter_by(active=True).count()
    pending_orders = Order.query.filter_by(order_status="placed").count()
    recent_orders  = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    low_stock      = Book.query.filter(Book.stock < 5, Book.active == True).all()
    return render_template("admin/dashboard.html",
                           total_orders=total_orders,
                           total_revenue=total_revenue,
                           total_books=total_books,
                           pending_orders=pending_orders,
                           recent_orders=recent_orders,
                           low_stock=low_stock)


# ── Admin: Books ──

@app.route("/admin/books")
@admin_required
def admin_books():
    page  = request.args.get("page", 1, type=int)
    query = request.args.get("q", "")
    bq    = Book.query
    if query:
        bq = bq.filter(Book.title.ilike(f"%{query}%"))
    books = bq.order_by(Book.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/books.html", books=books, query=query)


@app.route("/admin/books/add", methods=["GET", "POST"])
@admin_required
def admin_add_book():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        image_file = request.files.get("image")
        image_name = save_image(image_file) or "default_book.jpg"

        ebook_file_obj = request.files.get("ebook_file")
        ebook_filename = save_ebook(ebook_file_obj)
        is_ebook = bool(request.form.get("is_ebook"))

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
            publisher      = request.form.get("publisher", "The Bhaktivedanta Book Trust").strip(),
            stock          = int(request.form.get("stock", 100)),
            featured       = bool(request.form.get("featured")),
            active         = bool(request.form.get("active", True)),
            is_ebook       = is_ebook,
            ebook_file     = ebook_filename,
        )
        db.session.add(book)
        db.session.commit()
        flash("Book added successfully!", "success")
        return redirect(url_for("admin_books"))

    return render_template("admin/book_form.html", book=None, categories=categories)


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
        book.publisher      = request.form.get("publisher", "").strip()
        book.stock          = int(request.form.get("stock", 100))
        book.featured       = bool(request.form.get("featured"))
        book.active         = bool(request.form.get("active"))

        is_ebook = bool(request.form.get("is_ebook"))
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

        db.session.commit()
        flash("Book updated!", "success")
        return redirect(url_for("admin_books"))

    return render_template("admin/book_form.html", book=book, categories=categories)


@app.route("/admin/books/delete/<int:book_id>", methods=["POST"])
@admin_required
def admin_delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    book.active = False   # Soft delete
    db.session.commit()
    flash(f'Book "{book.title}" removed from store.', "info")
    return redirect(url_for("admin_books"))


@app.route("/admin/books/toggle-featured/<int:book_id>", methods=["POST"])
@admin_required
def toggle_featured(book_id):
    book = Book.query.get_or_404(book_id)
    book.featured = not book.featured
    db.session.commit()
    return jsonify({"featured": book.featured})


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

@app.route("/admin/orders")
@admin_required
def admin_orders():
    status = request.args.get("status", "")
    page   = request.args.get("page", 1, type=int)
    oq     = Order.query
    if status:
        oq = oq.filter_by(order_status=status)
    orders = oq.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/orders.html", orders=orders, status=status)


@app.route("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("admin/order_detail.html", order=order)


@app.route("/admin/orders/update/<int:order_id>", methods=["POST"])
@admin_required
def admin_update_order(order_id):
    order              = Order.query.get_or_404(order_id)
    order.order_status = request.form.get("order_status", order.order_status)
    order.payment_status = request.form.get("payment_status", order.payment_status)
    db.session.commit()
    flash("Order updated.", "success")
    return redirect(url_for("admin_order_detail", order_id=order_id))


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


# ─────────────────────────────────────────────
# UTILITY ROUTES
# ─────────────────────────────────────────────

@app.route("/api/cart-count")
def api_cart_count():
    return jsonify({"count": cart_item_count()})


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# ─────────────────────────────────────────────
# INIT DB & RUN
# ─────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    with app.app_context():
        db.create_all()
        print("[OK] Database tables created.")


if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    port  = int(os.environ.get("PORT", 5000))
    host  = os.environ.get("HOST", "0.0.0.0")
    print(f"\n[START] ISKCON Book Store running at http://{host}:{port}")
    print(f"   Admin panel: http://{host}:{port}/admin/\n")
    app.run(host=host, port=port, debug=debug)
