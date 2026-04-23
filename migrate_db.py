"""
Database Migration Script: Render → Railway
Run: python migrate_db.py
"""
import psycopg2
import psycopg2.extras

OLD_DB = "postgresql://iskconbook_db_user:Nef1ZTBpYPzNQJjMhwHExSmXme1GOsfR@dpg-d7g83mpj2pic7388a350-a.oregon-postgres.render.com/iskconbook_db?sslmode=require"
NEW_DB = "postgresql://postgres:OQqXPjsriUTLwnuQsokuFOfCyDxFAIdn@nozomi.proxy.rlwy.net:28837/railway"

def get_columns(cur):
    return [desc[0] for desc in cur.description]

def migrate_table(old_cur, new_cur, table, conflict_col="id"):
    print(f"  Migrating {table}...")
    old_cur.execute(f"SELECT * FROM {table} ORDER BY id")
    rows = old_cur.fetchall()
    if not rows:
        print(f"    No data in {table}, skipping.")
        return 0
    cols = get_columns(old_cur)
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({conflict_col}) DO NOTHING"
    count = 0
    for row in rows:
        new_cur.execute(sql, list(row))
        count += 1
    print(f"    {count} rows migrated.")
    return count

def main():
    print("Connecting to databases...")
    try:
        old_conn = psycopg2.connect(OLD_DB)
        print("  ✅ Connected to Render (old DB)")
    except Exception as e:
        print(f"  ❌ Cannot connect to Render DB: {e}")
        print("  Make sure you are using the EXTERNAL Render URL with .oregon-postgres.render.com")
        return

    try:
        new_conn = psycopg2.connect(NEW_DB)
        print("  ✅ Connected to Railway (new DB)")
    except Exception as e:
        print(f"  ❌ Cannot connect to Railway DB: {e}")
        return

    old_cur = old_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    new_cur = new_conn.cursor()

    try:
        print("\nStarting migration...")

        # 1. Categories
        migrate_table(old_cur, new_cur, "category")
        new_conn.commit()

        # 2. Books
        migrate_table(old_cur, new_cur, "book")
        new_conn.commit()

        # 3. Coupons
        try:
            migrate_table(old_cur, new_cur, "coupon")
            new_conn.commit()
        except Exception as e:
            new_conn.rollback()
            print(f"    Coupon table skipped: {e}")

        # 4. Orders
        migrate_table(old_cur, new_cur, "orders", conflict_col="id")
        new_conn.commit()

        # 5. Order Items
        migrate_table(old_cur, new_cur, "order_item", conflict_col="id")
        new_conn.commit()

        print("\n✅ Migration complete! All data transferred to Railway.")
        print("\nNext steps:")
        print("  1. Go to your Railway app URL and verify books/orders appear")
        print("  2. Re-upload book cover images via Admin panel")
        print("  3. Delete this migrate_db.py file (contains DB passwords)")

    except Exception as e:
        new_conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        old_cur.close()
        new_cur.close()
        old_conn.close()
        new_conn.close()

if __name__ == "__main__":
    main()
