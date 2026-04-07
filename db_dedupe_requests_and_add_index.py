import sqlite3

DB = "stock.db"

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Find duplicate groups (same from,to,date)
    dups = cur.execute("""
        SELECT from_location_id, to_location_id, request_date, COUNT(*) AS n
        FROM transfer_requests
        GROUP BY from_location_id, to_location_id, request_date
        HAVING COUNT(*) > 1
        ORDER BY request_date, from_location_id, to_location_id;
    """).fetchall()

    if not dups:
        print("No duplicates found. Creating index...")
    else:
        print(f"Found {len(dups)} duplicate group(s). Deduping...")

    for g in dups:
        from_id = g["from_location_id"]
        to_id = g["to_location_id"]
        date = g["request_date"]

        # Keep the most recently created request (highest created_at; fallback highest id)
        reqs = cur.execute("""
            SELECT id, created_at
            FROM transfer_requests
            WHERE from_location_id = ? AND to_location_id = ? AND request_date = ?
            ORDER BY datetime(created_at) DESC, id DESC;
        """, (from_id, to_id, date)).fetchall()

        keep_id = reqs[0]["id"]
        drop_ids = [r["id"] for r in reqs[1:]]

        print(f"  {date} from={from_id} to={to_id}: keeping request {keep_id}, dropping {drop_ids}")

        # Merge request lines into the kept request
        for drop_id in drop_ids:
            lines = cur.execute("""
                SELECT item_id, requested_qty_base, fulfilled_qty_base
                FROM transfer_request_lines
                WHERE request_id = ?;
            """, (drop_id,)).fetchall()

            for ln in lines:
                item_id = ln["item_id"]
                req_qty = float(ln["requested_qty_base"])
                ful_qty = float(ln["fulfilled_qty_base"])

                # Upsert into kept request by summing quantities
                existing = cur.execute("""
                    SELECT requested_qty_base, fulfilled_qty_base
                    FROM transfer_request_lines
                    WHERE request_id = ? AND item_id = ?;
                """, (keep_id, item_id)).fetchone()

                if existing is None:
                    cur.execute("""
                        INSERT INTO transfer_request_lines (request_id, item_id, requested_qty_base, fulfilled_qty_base)
                        VALUES (?, ?, ?, ?);
                    """, (keep_id, item_id, req_qty, ful_qty))
                else:
                    cur.execute("""
                        UPDATE transfer_request_lines
                        SET requested_qty_base = requested_qty_base + ?,
                            fulfilled_qty_base = fulfilled_qty_base + ?
                        WHERE request_id = ? AND item_id = ?;
                    """, (req_qty, ful_qty, keep_id, item_id))

            # Delete old request lines + request header
            cur.execute("DELETE FROM transfer_request_lines WHERE request_id = ?;", (drop_id,))
            cur.execute("DELETE FROM transfer_requests WHERE id = ?;", (drop_id,))

    conn.commit()

    # Now create the unique index
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_transfer_requests_from_to_date
        ON transfer_requests(from_location_id, to_location_id, request_date);
    """)
    conn.commit()
    conn.close()

    print("Deduped (if needed) and unique index ensured: ux_transfer_requests_from_to_date")

if __name__ == "__main__":
    main()
