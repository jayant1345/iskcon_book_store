# ISKCON Book Store - Complete Setup Guide 🪷

A production-ready Flask e-commerce platform for ISKCON books with admin panel, Razorpay payments, and WhatsApp integration.

---

## 📁 Project Structure

```
iskon_book_store/
├── app.py                  # Main Flask application
├── seed_data.py            # Database seeder (categories, books, coupons)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── Procfile                # For Render/Railway deployment
├── gunicorn.conf.py        # Gunicorn production config
├── static/
│   ├── css/style.css       # Main stylesheet (ISKCON saffron theme)
│   └── js/main.js          # Frontend JavaScript
├── templates/
│   ├── index.html          # Homepage
│   ├── books.html          # Book listing with search/filters
│   ├── book_detail.html    # Single book page
│   ├── cart.html           # Shopping cart
│   ├── checkout.html       # Checkout form + payment selection
│   ├── order_tracking.html # Order tracking page
│   ├── payment_success.html
│   ├── payment_failed.html
│   ├── payment_razorpay.html
│   ├── 404.html / 500.html
│   └── admin/
│       ├── admin_base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── books.html
│       ├── book_form.html
│       ├── orders.html
│       ├── order_detail.html
│       ├── categories.html
│       └── coupons.html
└── static/images/books/    # Book cover images
```

---

## 🚀 STEP 1: LOCAL SETUP

### Prerequisites
- Python 3.9+
- Git

### 1. Clone / Navigate to Project
```bash
cd C:\Project_AI\iskon_book_store
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# Activate it:
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
copy .env.example .env
```
Edit `.env` with your values (Razorpay keys, admin password, etc.)

### 5. Initialize Database & Seed Data
```bash
python seed_data.py
```
This creates all tables and populates:
- 8 categories (Bhagavad Gita, Srimad Bhagavatam, etc.)
- 20+ books with descriptions
- 3 sample coupons (HARE10, KRISHNA50, WELCOME20)

### 6. Run the Application
```bash
python app.py
```

**Access locally:**
- Store: http://127.0.0.1:5000
- Admin: http://127.0.0.1:5000/admin/login

**Default credentials:**
- Username: `admin`
- Password: `Hare@Krishna108`

### LAN Access (for mobile testing)
```bash
# Run with 0.0.0.0 to allow LAN access
set HOST=0.0.0.0
python app.py
```
Then access from any device on your network: `http://YOUR_PC_IP:5000`

---

## 🛠️ ADMIN PANEL FEATURES

### Dashboard
- Total orders, revenue, active books
- Pending orders count
- Low stock alerts
- Quick actions

### Books Management
- Add / Edit / Delete books
- Upload cover images
- Set featured books
- Manage stock
- Price & discount management

### Categories
- Add / Delete categories
- Set icon and sort order

### Orders
- View all orders with status filter
- Update order status (placed → confirmed → shipped → delivered)
- Update payment status
- WhatsApp customer directly from order page

### Coupons
- Create discount coupons (% or flat)
- Set minimum order, max uses, expiry

---

## 💳 PAYMENT SETUP

### Razorpay (Recommended for India)

1. Create account at https://dashboard.razorpay.com
2. Get your `Key ID` and `Key Secret`
3. Update `.env`:
```env
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_razorpay_secret
```

### Payment Methods Supported
- UPI
- Debit/Credit Cards
- Net Banking
- Wallets
- Cash on Delivery (COD)

### Test Mode
Use Razorpay test credentials for testing. Switch to live keys for production.

---

## ☁️ STEP 2: CLOUD DEPLOYMENT

### Option A: Render (Recommended - Easiest)

1. **Push to GitHub**
```bash
git init
git add .
git commit -m "ISKCON Book Store - Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/iskon-book-store.git
git push -u origin main
```

2. **Deploy on Render**
   - Go to https://render.com
   - Connect your GitHub repo
   - Create a **Web Service**
   - Settings:
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `gunicorn app:app`
   - Add Environment Variables:
     - `SECRET_KEY` = generate at https://djecrety.ir/
     - `RAZORPAY_KEY_ID` = your_key_id
     - `RAZORPAY_KEY_SECRET` = your_key_secret
     - `DATABASE_URL` = (auto from Render PostgreSQL)
     - `ADMIN_USERNAME` = admin
     - `ADMIN_PASSWORD` = your_secure_password
     - `FLASK_ENV` = production
   - Add PostgreSQL database (Render offers free tier)

3. **Update .env on Render**
   Add your `WHATSAPP_NUMBER` and other settings.

---

### Option B: DigitalOcean (App Platform)

1. Create Droplet (Ubuntu 22.04)
2. SSH into server:
```bash
ssh root@your_server_ip
```

3. Install dependencies:
```bash
apt update && apt upgrade -y
apt install python3 python3-pip python3-venv nginx -y
```

4. Setup project:
```bash
cd /var/www
git clone https://github.com/YOUR_USERNAME/iskon-book-store.git
cd iskon-book-store
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

5. Setup PostgreSQL:
```bash
apt install postgresql postgresql-contrib -y
su - postgres
psql
CREATE DATABASE iskon_books;
CREATE USER admin WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE iskon_books TO admin;
\q
exit
```

6. Configure environment:
```bash
cp .env.example .env
nano .env  # Add your values
```

7. Configure Gunicorn & Nginx (see below)

8. Setup systemd service for Gunicorn:
```bash
nano /etc/systemd/system/iskcon-app.service
```
```
[Unit]
Description=Gunicorn for ISKCON Book Store
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/iskon-book-store
Environment="PATH=/var/www/iskon-book-store/venv/bin"
ExecStart=/var/www/iskon-book-store/venv/bin/gunicorn --config gunicorn.conf.py app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable iskon-app
systemctl start iskon-app
```

9. Configure Nginx:
```bash
nano /etc/nginx/sites-available/iskcon-book-store
```
```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static {
        alias /var/www/iskon-book-store/static;
        expires 30d;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/iskon-book-store /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

10. Enable HTTPS (Let's Encrypt):
```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d yourdomain.com
```

---

### Option C: AWS EC2

1. **Launch EC2 Instance** (Ubuntu 22.04)
2. **Configure Security Group** - Open ports 22, 80, 443
3. SSH into instance and follow DigitalOcean steps 3-10

---

## 📊 DATABASE MIGRATION (SQLite → PostgreSQL)

### Local Export
```bash
python -c "
from app import app, db
from seed_data import CATEGORIES, BOOKS, COUPONS
import sqlite3

# Connect to SQLite
conn = sqlite3.connect('iskcon_books.db')
cursor = conn.cursor()

# Export data as SQL
# ... (manual export recommended)
"
```

### Better Approach: pgloader
```bash
# Install pgloader
apt install pgloader -y

# Create migration config
# migrate.load:
# LOAD database
#      FROM sqlite://iskcon_books.db
#      INTO postgresql://user:pass@localhost/iskcon_books
# WITH include no drop, create no tables, disable triggers

pgloader migrate.load
```

### Manual Migration
1. Export data from SQLite using a script
2. Import into PostgreSQL
3. Update `DATABASE_URL` in cloud environment

---

## 🔐 SECURITY CHECKLIST

- [ ] Change `SECRET_KEY` in production
- [ ] Use strong `ADMIN_PASSWORD`
- [ ] Use Razorpay **live keys** (not test) for production
- [ ] Enable HTTPS (Let's Encrypt)
- [ ] Never commit `.env` to git
- [ ] Set `FLASK_ENV=production`
- [ ] Use PostgreSQL in production (not SQLite)
- [ ] Keep dependencies updated (`pip install -r requirements.txt --upgrade`)

---

## 🎁 BONUS FEATURES

### WhatsApp Order Integration
Enabled in order detail page. Configure `WHATSAPP_NUMBER` in `.env`.

### Discount Coupons
- HARE10: 10% off (max ₹200, min order ₹200)
- KRISHNA50: ₹50 off (min order ₹500)
- WELCOME20: 20% off for first timers (max ₹300)

### Order Tracking
Visit `/order/track` - enter order number or phone number.

### Featured Books
Featured books appear on homepage with golden badge.

---

## 📝 API ENDPOINTS (Internal)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cart-count` | GET | Returns cart item count |
| `/cart/add/<id>` | POST | Add item to cart |
| `/cart/update` | POST | Update cart quantities |
| `/apply-coupon` | POST | Apply coupon code |
| `/payment/verify` | POST | Verify Razorpay payment |
| `/admin/books/toggle-featured/<id>` | POST | Toggle featured status |

---

## 🆘 TROUBLESHOOTING

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### Database not created
```bash
python -c "from app import db; db.create_all()"
python seed_data.py
```

### Static files not loading
- Check that `static/images/books/` directory exists
- Run Flask in debug mode to see static file routes
- For production: configure nginx to serve `/static`

### Razorpay not working
- Verify key ID and secret in `.env`
- Check Razorpay dashboard for test/live mode
- Ensure callback URL is correct

### Port already in use
```bash
# Find process using port 5000
netstat -ano | findstr :5000
# Kill it
taskkill /PID <PID> /F
```

---

## 🙏 Hare Krishna!

Built with love for spreading Vedic wisdom worldwide.

**Default Admin Credentials:**
- Username: `admin`
- Password: `Hare@Krishna108`

**Test Coupons:** HARE10, KRISHNA50, WELCOME20