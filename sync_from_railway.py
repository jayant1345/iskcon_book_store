"""
Sync local database and images FROM Railway live site.

Run this script whenever Railway has newer data than your local machine:
    python sync_from_railway.py

What it does:
  1. Downloads all book and category data from Railway as JSON
  2. Updates your local SQLite database to match Railway
  3. Downloads any missing book cover images from Railway to local folder

What it does NOT touch:
  - Orders (kept separate — local dev orders are test orders)
  - eBook files (too large; manage these manually)
"""

import os
import re
import sys
import json
import sqlite3
import requests
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────
RAILWAY_URL   = "https://iskconbooks.in"
SYNC_TOKEN    = "iskcon-sync-2024"
LOCAL_DB      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iskcon_books.db")
LOCAL_IMAGES  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "books")
# ─────────────────────────────────────────────────────────────────────────────


def fetch_data():
    print("⬇️  Fetching data from Railway...")
    resp = requests.get(f"{RAILWAY_URL}/admin/export-data", params={"token": SYNC_TOKEN}, timeout=30)
    if resp.status_code == 403:
        print("❌ Access denied — wrong token.")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch data (HTTP {resp.status_code})")
        sys.exit(1)
    data = resp.json()
    print(f"   ✅ Got {len(data['categories'])} categories, {len(data['books'])} books")
    return data


def sync_db(data):
    print("\n🗄️  Syncing local database...")
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Sync categories ──────────────────────────────────────────────────────
    cat_name_to_local_id = {}

    for cat in data["categories"]:
        # Match by name OR slug (handles case where name differs slightly)
        cur.execute(
            "SELECT id FROM categories WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) OR slug = ?",
            (cat["name"], cat["slug"])
        )
        row = cur.fetchone()
        if row:
            # Update existing
            cur.execute("""
                UPDATE categories
                SET name=?, slug=?, description=?, icon=?, sort_order=?
                WHERE id=?
            """, (cat["name"], cat["slug"], cat["description"], cat["icon"], cat["sort_order"], row["id"]))
            cat_name_to_local_id[cat["name"]] = row["id"]
        else:
            # Insert new
            cur.execute("""
                INSERT INTO categories (name, slug, description, icon, sort_order)
                VALUES (?, ?, ?, ?, ?)
            """, (cat["name"], cat["slug"], cat["description"], cat["icon"], cat["sort_order"]))
            cat_name_to_local_id[cat["name"]] = cur.lastrowid
            print(f"   ➕ New category: {cat['name']}")

    # ── Sync books ───────────────────────────────────────────────────────────
    added = updated = 0

    for book in data["books"]:
        local_cat_id = cat_name_to_local_id.get(book["category_name"]) if book["category_name"] else None

        # Match by title + language (robust across different DB IDs)
        cur.execute("""
            SELECT id FROM books
            WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) AND LOWER(COALESCE(language,'English')) = LOWER(?)
        """, (book["title"], book["language"] or "English"))
        row = cur.fetchone()

        if row:
            cur.execute("""
                UPDATE books SET
                    author=?, description=?, short_desc=?, price=?,
                    original_price=?, image=?, category_id=?, isbn=?,
                    language=?, pages=?, publisher=?, stock=?,
                    featured=?, active=?, deleted=?, is_ebook=?,
                    ebook_file=?, preview_file=?
                WHERE id=?
            """, (
                book["author"], book["description"], book["short_desc"],
                book["price"], book["original_price"], book["image"],
                local_cat_id, book["isbn"], book["language"], book["pages"],
                book["publisher"], book["stock"], int(book["featured"]),
                int(book["active"]), int(book["deleted"]), int(book["is_ebook"]),
                book["ebook_file"] or None, book["preview_file"] or None,
                row["id"]
            ))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO books (
                    title, author, description, short_desc, price, original_price,
                    image, category_id, isbn, language, pages, publisher, stock,
                    featured, active, deleted, is_ebook, ebook_file, preview_file
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                book["title"], book["author"], book["description"], book["short_desc"],
                book["price"], book["original_price"], book["image"],
                local_cat_id, book["isbn"], book["language"], book["pages"],
                book["publisher"], book["stock"], int(book["featured"]),
                int(book["active"]), int(book["deleted"]), int(book["is_ebook"]),
                book["ebook_file"] or None, book["preview_file"] or None,
            ))
            added += 1
            print(f"   ➕ New book: {book['title']}")

    conn.commit()
    conn.close()
    print(f"   ✅ Books — Updated: {updated} | Added: {added}")


def sync_images(data):
    print("\n🖼️  Syncing images...")
    os.makedirs(LOCAL_IMAGES, exist_ok=True)

    missing = [
        b["image"] for b in data["books"]
        if b["image"] and b["image"] != "default_book.jpg"
        and not os.path.exists(os.path.join(LOCAL_IMAGES, b["image"]))
    ]

    if not missing:
        print("   ✅ All images already present locally — nothing to download")
        return

    print(f"   Found {len(missing)} missing image(s) — downloading...")
    ok = fail = 0

    for filename in missing:
        url = f"{RAILWAY_URL}/static/images/books/{filename}"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                with open(os.path.join(LOCAL_IMAGES, filename), "wb") as f:
                    f.write(r.content)
                print(f"   ✅ {filename}")
                ok += 1
            else:
                print(f"   ❌ {filename} (HTTP {r.status_code})")
                fail += 1
        except Exception as e:
            print(f"   ❌ {filename} ({e})")
            fail += 1

    print(f"   Images — Downloaded: {ok} | Failed: {fail}")


if __name__ == "__main__":
    print("=" * 55)
    print("  ISKCON Book Store — Sync FROM Railway to Local")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    data = fetch_data()
    sync_db(data)
    sync_images(data)

    print("\n✅ Sync complete! Restart your local server to see changes.")
    print("   python app.py")
