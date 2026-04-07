import sqlite3

conn = sqlite3.connect("stock.db")
conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_transfer_requests_from_to_date
    ON transfer_requests(from_location_id, to_location_id, request_date)
""")
conn.commit()
conn.close()

print("Unique index ensured.")
