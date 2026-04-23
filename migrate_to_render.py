"""
Migrate local SQLite data to Render PostgreSQL.
Usage: python migrate_to_render.py
Paste your Render External Database URL when prompted.
"""
import sqlite3
import os
import sys

def migrate():
    render_url = input("\nPaste your Render EXTERNAL Database URL: ").strip()
    if not render_url:
        print("No URL provided. Exiting.")
        return

    if render_url.startswith("postgres://"):
        render_url = render_url.replace("postgres://", "postgresql://", 1)

    # Find local SQLite
    db = "iskcon_books.db" if os.path.exists("iskcon_books.db") else "instance/iskcon_books.db"
    if not os.path.exists(db):
        print(f"SQLite DB not found at {db}")
        return

    print(f"\nReading from: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    import psycopg2
    pg = psycopg2.connect(render_url, sslmode="require")
    pg_cur = pg.cursor()

    # ── Categories ──────────────────────────────
    cur.execute("SELECT * FROM categories")
    cats = cur.fetchall()
    for r in cats:
        pg_cur.execute("""
            INSERT INTO categories (id, name, slug, description, icon, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (r["id"], r["name"], r["slug"], r["description"], r["icon"], r["sort_order"]))
    pg_cur.execute("SELECT setval('categories_id_seq', (SELECT MAX(id) FROM categories))")
    print(f"  Categories: {len(cats)} rows migrated")

    # ── Books ────────────────────────────────────
    cur.execute("SELECT * FROM books")
    books = cur.fetchall()
    for r in books:
        pg_cur.execute("""
            INSERT INTO books (id, title, author, description, short_desc, price, original_price,
                image, category_id, isbn, language, pages, publisher, stock, featured, active,
                created_at, preview_file, is_ebook, ebook_file, deleted)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            r["id"], r["title"], r["author"], r["description"], r["short_desc"],
            r["price"], r["original_price"], r["image"], r["category_id"],
            r["isbn"], r["language"], r["pages"], r["publisher"], r["stock"],
            bool(r["featured"]), bool(r["active"]), r["created_at"],
            r["preview_file"], bool(r["is_ebook"]), r["ebook_file"], bool(r["deleted"])
        ))
    pg_cur.execute("SELECT setval('books_id_seq', (SELECT MAX(id) FROM books))")
    print(f"  Books: {len(books)} rows migrated")

    # ── Coupons ──────────────────────────────────
    cur.execute("SELECT * FROM coupons")
    coupons = cur.fetchall()
    for r in coupons:
        pg_cur.execute("""
            INSERT INTO coupons (id, code, description, discount_type, discount_value,
                min_order, max_discount, max_uses, used_count, active, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            r["id"], r["code"], r["description"], r["discount_type"], r["discount_value"],
            r["min_order"], r["max_discount"], r["max_uses"], r["used_count"],
            bool(r["active"]), r["expires_at"]
        ))
    if coupons:
        pg_cur.execute("SELECT setval('coupons_id_seq', (SELECT MAX(id) FROM coupons))")
    print(f"  Coupons: {len(coupons)} rows migrated")

    pg.commit()
    pg.close()
    conn.close()
    print("\nMigration complete! All data is now on Render PostgreSQL.")
    print("Note: Book images need to be re-uploaded via Admin panel → Edit each book.")

if __name__ == "__main__":
    migrate()
