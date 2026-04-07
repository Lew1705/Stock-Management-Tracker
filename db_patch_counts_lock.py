import sqlite3

DB_PATH = "stock.db"

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Add columns if missing
    if not col_exists(cur, "stock_counts", "is_reconciled"):
        cur.execute("ALTER TABLE stock_counts ADD COLUMN is_reconciled INTEGER NOT NULL DEFAULT 0")
        print("Added column: is_reconciled")
    else:
        print("Column exists: is_reconciled")

    if not col_exists(cur, "stock_counts", "reconciled_at"):
        cur.execute("ALTER TABLE stock_counts ADD COLUMN reconciled_at TEXT")
        print("Added column: reconciled_at")
    else:
        print("Column exists: reconciled_at")

    # Create index
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_stock_counts_reconciled
        ON stock_counts(location_id, count_date, is_reconciled)
    """)
    print("Index ensured: ix_stock_counts_reconciled")

    conn.commit()
    conn.close()
    print("Patch complete.")

if __name__ == "__main__":
    main()
