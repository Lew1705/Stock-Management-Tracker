import os
import sqlite3
from pathlib import Path
import csv
from .sheets import get_spreadsheet, get_sheet, clear_row_groups, apply_collapsible_row_groups
from .core.units import VALID_BASE_UNITS, normalize_base_unit, parse_supplier_links, split_multi_value


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = (
    Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) / "stock.db"
    if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    else (PROJECT_ROOT / "stock.db")
)
DB_PATH = Path(os.environ.get("STOCK_DB_PATH", str(DEFAULT_DB_PATH))).expanduser().resolve()
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return any(str(row["name"]) == column_name for row in rows)


def _run_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
    """)

    if not _column_exists(conn, "items", "supplier_id"):
        conn.execute("ALTER TABLE items ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id);")

    if not _column_exists(conn, "items", "cost_per_unit"):
        conn.execute("ALTER TABLE items ADD COLUMN cost_per_unit REAL NOT NULL DEFAULT 0;")

    if not _column_exists(conn, "stock_transactions", "cost_per_unit_at_time"):
        conn.execute("ALTER TABLE stock_transactions ADD COLUMN cost_per_unit_at_time REAL NOT NULL DEFAULT 0;")

    if not _column_exists(conn, "stock_transactions", "transfer_request_id"):
        conn.execute("ALTER TABLE stock_transactions ADD COLUMN transfer_request_id INTEGER REFERENCES transfer_requests(id);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            ref_number TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(item_id, supplier_id),
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_item_suppliers_item_sort
        ON item_suppliers(item_id, sort_order, supplier_id);
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_stock_transactions_request_id
        ON stock_transactions(transfer_request_id);
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED')),
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ordered_at TEXT,
            received_at TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_order_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            supplier_name TEXT NOT NULL,
            ordered_qty_base REAL NOT NULL,
            received_qty_base REAL NOT NULL DEFAULT 0,
            unit_cost REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(order_id) REFERENCES supplier_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES items(id)
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_supplier_orders_status_date
        ON supplier_orders(status, order_date);
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_supplier_order_lines_order
        ON supplier_order_lines(order_id);
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            invoice_reference TEXT NOT NULL DEFAULT '',
            supplier_name TEXT NOT NULL DEFAULT '',
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            content_type TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'UPLOADED' CHECK (review_status IN ('UPLOADED', 'REVIEWED')),
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT,
            FOREIGN KEY(order_id) REFERENCES supplier_orders(id) ON DELETE CASCADE
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_supplier_invoices_order
        ON supplier_invoices(order_id, uploaded_at DESC);
    """)

    # Backfill the new link table from older single-supplier rows.
    conn.execute("""
        INSERT OR IGNORE INTO item_suppliers (item_id, supplier_id, sort_order)
        SELECT id, supplier_id, 0
        FROM items
        WHERE supplier_id IS NOT NULL;
    """)
    conn.execute("""
        UPDATE items
        SET cost_per_unit = COALESCE(cost_per_unit, 0)
        WHERE cost_per_unit IS NULL;
    """)
    conn.execute("""
        UPDATE stock_transactions
        SET cost_per_unit_at_time = COALESCE(
            (
                SELECT i.cost_per_unit
                FROM items i
                WHERE i.id = stock_transactions.item_id
            ),
            0
        )
        WHERE cost_per_unit_at_time IS NULL OR cost_per_unit_at_time = 0;
    """)


def _split_multi_value(raw_value: str) -> list[str]:
    return split_multi_value(raw_value)


def _parse_supplier_links(raw_suppliers: str, raw_refs: str) -> list[tuple[str, str]]:
    return parse_supplier_links(raw_suppliers, raw_refs)


def _sync_item_suppliers(cur: sqlite3.Cursor, item_id: int, supplier_links: list[tuple[str, str]]) -> int | None:
    cur.execute("DELETE FROM item_suppliers WHERE item_id = ?", (item_id,))

    first_supplier_id = None

    for sort_order, (supplier_name, ref_number) in enumerate(supplier_links):
        cur.execute("""
            INSERT INTO suppliers (name)
            VALUES (?)
            ON CONFLICT(name) DO NOTHING
        """, (supplier_name,))

        cur.execute("SELECT id FROM suppliers WHERE name = ?", (supplier_name,))
        supplier_row = cur.fetchone()
        if supplier_row is None:
            raise ValueError(f"Could not resolve supplier '{supplier_name}'")

        supplier_id = int(supplier_row["id"])
        if first_supplier_id is None:
            first_supplier_id = supplier_id

        cur.execute("""
            INSERT INTO item_suppliers (item_id, supplier_id, ref_number, sort_order)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id, supplier_id)
            DO UPDATE SET
                ref_number = excluded.ref_number,
                sort_order = excluded.sort_order
        """, (item_id, supplier_id, ref_number, sort_order))

    return first_supplier_id


def get_item_supplier_summary(item_id: int) -> str:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.name, isp.ref_number
            FROM item_suppliers isp
            JOIN suppliers s ON s.id = isp.supplier_id
            WHERE isp.item_id = ?
            ORDER BY isp.sort_order, s.name;
            """,
            (item_id,),
        ).fetchall()

    if not rows:
        return "Unknown"

    labels = []
    for row in rows:
        ref = (row["ref_number"] or "").strip()
        labels.append(f"{row['name']} ({ref})" if ref else str(row["name"]))
    return ", ".join(labels)



def init_db():
    with get_conn() as conn:
        schema = SCHEMA_PATH.read_text()
        conn.executescript(schema)
        _run_schema_migrations(conn)
    


def seed_locations() -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?);", ("Keele",))
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?);", ("Little Shop",))


def record_run_history(run_type: str, run_date: str, status: str, output: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO run_history (run_type, run_date, status, finished_at, output)
            VALUES (?, ?, ?, datetime('now'), ?);
            """,
            (run_type, run_date, status, output),
        )
        return int(cur.lastrowid)


def recent_run_history(limit: int = 10):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, run_type, run_date, status, started_at, finished_at, output
            FROM run_history
            ORDER BY datetime(started_at) DESC, id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()


def create_user(username: str, password_hash: str, role: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?);
            """,
            (username, password_hash, role),
        )
        return int(cur.lastrowid)


def get_user_by_username(username: str):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, username, password_hash, role, is_active, created_at
            FROM users
            WHERE username = ?;
            """,
            (username,),
        ).fetchone()


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, username, password_hash, role, is_active, created_at
            FROM users
            WHERE id = ?;
            """,
            (user_id,),
        ).fetchone()


def list_users():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            ORDER BY is_active DESC, LOWER(username);
            """
        ).fetchall()


def update_user_role(user_id: int, role: str) -> None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET role = ? WHERE id = ?;",
            (role, int(user_id)),
        )
        if cur.rowcount <= 0:
            raise ValueError(f"User {user_id} was not found.")


def set_user_active(user_id: int, is_active: bool) -> None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?;",
            (1 if is_active else 0, int(user_id)),
        )
        if cur.rowcount <= 0:
            raise ValueError(f"User {user_id} was not found.")


def update_user_password(user_id: int, password_hash: str) -> None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?;",
            (password_hash, int(user_id)),
        )
        if cur.rowcount <= 0:
            raise ValueError(f"User {user_id} was not found.")

def list_locations() -> None:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM locations ORDER BY id;").fetchall()

    for row in rows:
        print(dict(row))


def normalize_cost_per_unit(raw_value: float | int | str | None) -> float:
    text = str(raw_value or "").strip()
    if text == "":
        return 0.0
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError("Cost per unit must be a number.") from exc
    if value < 0:
        raise ValueError("Cost per unit cannot be negative.")
    return value


def insert_item(name: str, category: str, base_unit: str, cost_per_unit: float | int | str | None = 0) -> None:
    normalized_unit = normalize_base_unit(base_unit)
    normalized_cost = normalize_cost_per_unit(cost_per_unit)
    with get_conn() as conn:
        conn.execute("""
        
        INSERT OR IGNORE INTO items (name, category, base_unit, cost_per_unit)
        VALUES (?, ?, ?, ?)
                     
        """,
        (name, category, normalized_unit, normalized_cost),
    )

def list_items():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, category, base_unit, cost_per_unit
        FROM items
        ORDER BY id
    """)

    rows = cur.fetchall()

    for r in rows:
        print(
            f"{r['id']:>3} | {r['name']:<25} | {r['category']:<15} | "
            f"{r['base_unit']:<12} | {float(r['cost_per_unit'] or 0):.2f}"
        )

    conn.close()


def get_items_with_suppliers():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                i.id,
                i.name,
                i.category,
                i.base_unit,
                i.cost_per_unit,
                COALESCE(
                    GROUP_CONCAT(
                        CASE
                            WHEN COALESCE(isp.ref_number, '') = '' THEN s.name
                            ELSE s.name || ' (' || isp.ref_number || ')'
                        END,
                        ' | '
                    ),
                    ''
                ) AS suppliers
            FROM items i
            LEFT JOIN item_suppliers isp ON isp.item_id = i.id
            LEFT JOIN suppliers s ON s.id = isp.supplier_id
            GROUP BY i.id, i.name, i.category, i.base_unit, i.cost_per_unit
            ORDER BY LOWER(i.category), LOWER(i.name);
            """
        ).fetchall()


def get_count_entry_rows(location: str, count_date: str):
    location_id = get_location_id(location)

    with get_conn() as conn:
        count_row = conn.execute(
            """
            SELECT id, is_reconciled
            FROM stock_counts
            WHERE location_id = ? AND count_date = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1;
            """,
            (location_id, count_date),
        ).fetchone()

        count_id = int(count_row["id"]) if count_row else None
        is_reconciled = bool(count_row["is_reconciled"]) if count_row else False

        rows = conn.execute(
            """
            SELECT
                i.id,
                i.name,
                i.category,
                i.base_unit,
                scl.counted_qty_base AS counted_qty
            FROM items i
            LEFT JOIN stock_count_lines scl
                ON scl.item_id = i.id
               AND scl.count_id = ?
            ORDER BY LOWER(i.category), LOWER(i.name);
            """,
            (count_id,),
        ).fetchall()

    result = []
    for row in rows:
        item_name = str(row["name"])
        result.append(
            {
                "id": int(row["id"]),
                "name": item_name,
                "category": str(row["category"]),
                "base_unit": str(row["base_unit"]),
                "counted_qty": "" if row["counted_qty"] is None else str(row["counted_qty"]),
                "current_stock": current_stock(location, item_name),
            }
        )

    return {
        "count_id": count_id,
        "is_reconciled": is_reconciled,
        "rows": result,
    }


def get_saved_count_summary(location: str, count_date: str) -> dict:
    location_id = get_location_id(location)

    with get_conn() as conn:
        count_row = conn.execute(
            """
            SELECT id, is_reconciled
            FROM stock_counts
            WHERE location_id = ? AND count_date = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1;
            """,
            (location_id, count_date),
        ).fetchone()

        if count_row is None:
            return {
                "count_id": None,
                "is_reconciled": False,
                "line_count": 0,
            }

        count_id = int(count_row["id"])
        line_row = conn.execute(
            """
            SELECT COUNT(*) AS line_count
            FROM stock_count_lines
            WHERE count_id = ?;
            """,
            (count_id,),
        ).fetchone()

    return {
        "count_id": count_id,
        "is_reconciled": bool(count_row["is_reconciled"]),
        "line_count": int(line_row["line_count"] or 0),
    }


def save_web_count(location: str, count_date: str, count_values: dict[int, str]) -> int:
    count_id = get_or_create_count(location, count_date)

    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_reconciled FROM stock_counts WHERE id = ?;",
            (count_id,),
        ).fetchone()
        if row is not None and int(row["is_reconciled"]) == 1:
            raise ValueError("This count has already been reconciled and cannot be edited.")

    clear_count_lines(count_id)

    for item_id, raw_value in count_values.items():
        text = (raw_value or "").strip()
        if text == "":
            continue
        try:
            qty = float(text)
        except ValueError as exc:
            item = get_item_by_id(item_id)
            raise ValueError(f"'{text}' is not a valid number for {item['name']}.") from exc
        if qty < 0:
            item = get_item_by_id(item_id)
            raise ValueError(f"Count for {item['name']} cannot be negative.")
        add_count_line_by_item_id(count_id, item_id, qty)

    return count_id


def generate_shopping_list(location_name: str, as_of_date: str):
    init_db()
    location_id = get_location_id(location_name)

    with get_conn() as conn:
        par_rows = conn.execute(
            """
            SELECT
                i.id AS item_id,
                i.name,
                i.category,
                i.base_unit,
                i.cost_per_unit,
                p.par_qty_base
            FROM par_levels p
            JOIN items i ON i.id = p.item_id
            WHERE p.location_id = ?
            ORDER BY LOWER(i.category), LOWER(i.name);
            """,
            (location_id,),
        ).fetchall()

    results = []
    for row in par_rows:
        item_id = int(row["item_id"])
        par_qty = float(row["par_qty_base"] or 0)
        counted_qty = latest_count_qty(location_name, item_id, as_of_date)
        shortfall = max(par_qty - counted_qty, 0.0)

        if shortfall <= 1e-9:
            continue

        results.append(
            {
                "item_id": item_id,
                "name": str(row["name"]),
                "category": str(row["category"]),
                "base_unit": str(row["base_unit"]),
                "counted_qty": counted_qty,
                "par_qty": par_qty,
                "order_qty": shortfall,
                "supplier": get_item_supplier_summary(item_id),
            }
        )

    return results


def generate_request_list(location_name: str, as_of_date: str, source_location_name: str = "Keele"):
    init_db()
    location_id = get_location_id(location_name)

    with get_conn() as conn:
        par_rows = conn.execute(
            """
            SELECT
                i.id AS item_id,
                i.name,
                i.category,
                i.base_unit,
                i.cost_per_unit,
                p.par_qty_base
            FROM par_levels p
            JOIN items i ON i.id = p.item_id
            WHERE p.location_id = ?
            ORDER BY LOWER(i.category), LOWER(i.name);
            """,
            (location_id,),
        ).fetchall()

    results = []
    for row in par_rows:
        item_id = int(row["item_id"])
        par_qty = float(row["par_qty_base"] or 0)
        counted_qty = latest_count_qty(location_name, item_id, as_of_date)
        request_qty = max(par_qty - counted_qty, 0.0)

        if request_qty <= 1e-9:
            continue

        source_qty = latest_count_qty(source_location_name, item_id, as_of_date)
        fulfill_qty = min(request_qty, source_qty)
        source_shortfall = max(request_qty - source_qty, 0.0)
        cost_per_unit = float(row["cost_per_unit"] or 0.0)

        results.append(
            {
                "item_id": item_id,
                "name": str(row["name"]),
                "category": str(row["category"]),
                "base_unit": str(row["base_unit"]),
                "counted_qty": counted_qty,
                "par_qty": par_qty,
                "request_qty": request_qty,
                "estimated_value": request_qty * cost_per_unit,
                "cost_per_unit": cost_per_unit,
                "source_location": source_location_name,
                "source_available_qty": source_qty,
                "fulfill_qty": fulfill_qty,
                "source_shortfall": source_shortfall,
                "supplier": get_item_supplier_summary(item_id),
            }
        )

    return results


def generate_supplier_shopping_list(as_of_date: str, source_location_name: str = "Keele", request_location_name: str = "Little Shop"):
    init_db()
    source_location_id = get_location_id(source_location_name)
    request_location_id = get_location_id(request_location_name)

    with get_conn() as conn:
        source_par_rows = conn.execute(
            """
            SELECT
                i.id AS item_id,
                i.name,
                i.category,
                i.base_unit,
                p.par_qty_base
            FROM par_levels p
            JOIN items i ON i.id = p.item_id
            WHERE p.location_id = ?
            ORDER BY LOWER(i.category), LOWER(i.name);
            """,
            (source_location_id,),
        ).fetchall()

        request_par_map = {
            int(row["item_id"]): float(row["par_qty_base"] or 0)
            for row in conn.execute(
                """
                SELECT item_id, par_qty_base
                FROM par_levels
                WHERE location_id = ?;
                """,
                (request_location_id,),
            ).fetchall()
        }

    results = []
    for row in source_par_rows:
        item_id = int(row["item_id"])
        source_par_qty = float(row["par_qty_base"] or 0)
        source_counted_qty = latest_count_qty(source_location_name, item_id, as_of_date)
        request_par_qty = float(request_par_map.get(item_id, 0.0))
        request_counted_qty = latest_count_qty(request_location_name, item_id, as_of_date)
        request_qty = max(request_par_qty - request_counted_qty, 0.0)
        fulfill_qty = min(request_qty, source_counted_qty)
        projected_source_qty = source_counted_qty - fulfill_qty
        order_qty = max(source_par_qty - projected_source_qty, 0.0)

        if order_qty <= 1e-9:
            continue

        results.append(
            {
                "item_id": item_id,
                "name": str(row["name"]),
                "category": str(row["category"]),
                "base_unit": str(row["base_unit"]),
                "source_counted_qty": source_counted_qty,
                "source_par_qty": source_par_qty,
                "request_location": request_location_name,
                "request_counted_qty": request_counted_qty,
                "request_par_qty": request_par_qty,
                "request_qty": request_qty,
                "fulfill_qty": fulfill_qty,
                "projected_source_qty": projected_source_qty,
                "order_qty": order_qty,
                "supplier": get_item_supplier_summary(item_id),
            }
        )

    return results


def get_item_for_edit(item_id: int):
    with get_conn() as conn:
        item = conn.execute(
            """
            SELECT id, name, category, base_unit, cost_per_unit
            FROM items
            WHERE id = ?;
            """,
            (item_id,),
        ).fetchone()

        if item is None:
            raise ValueError(f"Unknown item_id: {item_id}")

        supplier_rows = conn.execute(
            """
            SELECT s.name, isp.ref_number
            FROM item_suppliers isp
            JOIN suppliers s ON s.id = isp.supplier_id
            WHERE isp.item_id = ?
            ORDER BY isp.sort_order, s.name;
            """,
            (item_id,),
        ).fetchall()

    supplier_names = [str(row["name"]) for row in supplier_rows]
    refs = [str(row["ref_number"] or "") for row in supplier_rows]

    return {
        "id": int(item["id"]),
        "name": str(item["name"]),
        "category": str(item["category"]),
        "base_unit": str(item["base_unit"]),
        "cost_per_unit": str(float(item["cost_per_unit"] or 0)),
        "supplier": "; ".join(supplier_names),
        "ref": "; ".join(refs),
    }


def get_item_par_levels(item_id: int) -> dict[str, float | None]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT l.name AS location_name, p.par_qty_base
            FROM locations l
            LEFT JOIN par_levels p
              ON p.location_id = l.id
             AND p.item_id = ?
            WHERE l.name IN ('Keele', 'Little Shop')
            ORDER BY l.name;
            """,
            (item_id,),
        ).fetchall()

    result = {"Keele": None, "Little Shop": None}
    for row in rows:
        value = row["par_qty_base"]
        result[str(row["location_name"])] = None if value is None else float(value)
    return result


def save_item(
    item_id: int | None,
    name: str,
    category: str,
    base_unit: str,
    supplier_text: str,
    ref_text: str,
    cost_per_unit: float | int | str | None = 0,
) -> int:
    normalized_name = " ".join((name or "").strip().split())
    normalized_category = " ".join((category or "").strip().split())

    if not normalized_name:
        raise ValueError("Item name is required.")
    if not normalized_category:
        raise ValueError("Category is required.")

    normalized_unit = normalize_base_unit(base_unit)
    normalized_cost = normalize_cost_per_unit(cost_per_unit)
    supplier_links = _parse_supplier_links(supplier_text, ref_text)

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            if item_id is None:
                cur.execute(
                    """
                    INSERT INTO items (name, category, base_unit, cost_per_unit, supplier_id)
                    VALUES (?, ?, ?, ?, NULL);
                    """,
                    (normalized_name, normalized_category, normalized_unit, normalized_cost),
                )
                saved_item_id = int(cur.lastrowid)
            else:
                cur.execute(
                    """
                    UPDATE items
                    SET name = ?, category = ?, base_unit = ?, cost_per_unit = ?, supplier_id = NULL
                    WHERE id = ?;
                    """,
                    (normalized_name, normalized_category, normalized_unit, normalized_cost, int(item_id)),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"Unknown item_id: {item_id}")
                saved_item_id = int(item_id)

            primary_supplier_id = _sync_item_suppliers(cur, saved_item_id, supplier_links)
            cur.execute(
                "UPDATE items SET supplier_id = ? WHERE id = ?",
                (primary_supplier_id, saved_item_id),
            )
            conn.commit()
            return saved_item_id
        except sqlite3.IntegrityError as exc:
            if "items.name" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError(f"An item named '{normalized_name}' already exists.") from exc
            raise


def set_par_level_by_item_id(location: str, item_id: int, par_qty_base: float) -> None:
    location_id = get_location_id(location)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO par_levels (location_id, item_id, par_qty_base)
            VALUES (?, ?, ?)
            ON CONFLICT(location_id, item_id)
            DO UPDATE SET par_qty_base = excluded.par_qty_base;
            """,
            (location_id, int(item_id), par_qty_base),
        )


def delete_par_level_by_item_id(location: str, item_id: int) -> None:
    location_id = get_location_id(location)

    with get_conn() as conn:
        conn.execute(
            """
            DELETE FROM par_levels
            WHERE location_id = ? AND item_id = ?;
            """,
            (location_id, int(item_id)),
        )


def get_location_id(name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM locations WHERE name = ?;", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown location: {name}")
        return int(row["id"])
    
def get_item_id(name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM items WHERE name = ?;", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown items: {name}")
        return int(row["id"])

def get_item_cost_per_unit(item_id: int) -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT cost_per_unit FROM items WHERE id = ?;",
            (item_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Unknown item_id: {item_id}")
    return float(row["cost_per_unit"] or 0.0)


def add_transaction(
    location: str,
    item: str,
    qty_base: float,
    tx_type: str,
    note: str = "",
    transfer_request_id: int | None = None,
) -> None:
    location_id = get_location_id(location)
    item_id = get_item_id(item)
    cost_per_unit = get_item_cost_per_unit(item_id)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stock_transactions (
                location_id,
                item_id,
                qty_base,
                cost_per_unit_at_time,
                transfer_request_id,
                type,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (location_id, item_id, qty_base, cost_per_unit, transfer_request_id, tx_type, note),
        )

def receive_into_keele(item: str, qty_base: float, note: str = "") -> None:
    add_transaction("Keele", item, abs(qty_base), "RECEIVE", note)


def transfer_keele_to_little(item: str, qty_base: float, note: str = "") -> None:
    q = abs(qty_base)
    add_transaction("Keele", item, -q, "TRANSFER_OUT", note)
    add_transaction("Little Shop", item, q, "TRANSFER_IN", note)


def waste(location: str, item: str, qty_base: float, note: str = "") -> None:
    add_transaction(location, item, -abs(qty_base), "WASTE", note)

def stock_on_hand(location: str, item: str) -> float:
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_base), 0) AS qty
            FROM stock_transactions
            WHERE location_id = ? AND item_id = ?;
            """,
            (location_id, item_id),
        ).fetchone()

    return float(row["qty"])




def create_count(location: str, count_date: str) -> int:
    """
    Creates a stock count 'header' for a location + week ending date.
    Returns the new count_id.
    """
    location_id = get_location_id(location)

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO stock_counts (location_id, count_date)
            VALUES (?, ?);
            """,
            (location_id, count_date),
        )
        return int(cur.lastrowid) #gives u the id of the last row inserted 
    
def add_count_line(count_id: int, item: str, counted_qty_base: float) -> None:
    """
    Adds (or updates) a single item line to an existing stock count.
    Refuses to modify a count once it has been reconciled.
    """
    item_id = get_item_id(item)

    with get_conn() as conn:
        # Lock: block edits after reconcile
        row = conn.execute(
            "SELECT is_reconciled FROM stock_counts WHERE id = ?;",
            (count_id,),
        ).fetchone()

        if row is not None and int(row["is_reconciled"]) == 1:
            raise ValueError(f"Count {count_id} is reconciled; you can't change lines.")

        # Upsert count line (lets you correct mistakes before reconcile)
        conn.execute(
            """
            INSERT INTO stock_count_lines (count_id, item_id, counted_qty_base)
            VALUES (?, ?, ?)
            ON CONFLICT(count_id, item_id)
            DO UPDATE SET counted_qty_base = excluded.counted_qty_base;
            """,
            (count_id, item_id, float(counted_qty_base)),
        )


def list_count_lines(count_id: int) -> None:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.name, i.base_unit, l.counted_qty_base
            FROM stock_count_lines l
            JOIN items i ON i.id = l.item_id
            WHERE l.count_id = ?
            ORDER BY i.name;
            """,
            (count_id,),
        ).fetchall()

    for row in rows:
        print(dict(row))

def get_count(count_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM stock_counts
            WHERE id = ?;
            """,
            (count_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"Unknown count_id: {count_id}")

    return row  # sqlite3.Row

def get_counted_qty(count_id: int, item: str) -> float:
    item_id = get_item_id(item)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT counted_qty_base
            FROM stock_count_lines
            WHERE count_id = ? AND item_id = ?;
            """,
            (count_id, item_id),
        ).fetchone()

    if row is None:
        #if it wasnst counted treat it as 0
        return 0.0

    return float(row["counted_qty_base"])


def get_last_two_count_ids(location: str) -> tuple[int, int]:
    """
    Returns (open_count_id, close_count_id) for the most recent two counts
    at a location. 'close' is the newest, 'open' is the one before it.
    """
    rows = list_counts(location=location, limit=2)

    if len(rows) < 2:
        raise ValueError(f"Need at least 2 counts for {location} to calculate usage.")

    close_id = int(rows[0]["id"])
    open_id = int(rows[1]["id"])
    return open_id, close_id



def usage_since_last_count(location: str, item: str | None = None):
    """
    If item is provided -> returns usage for that item since last count.
    If item is None -> returns list of rows: [{item, used}, ...] for all items.
    """
    open_id, close_id = get_last_two_count_ids(location)

    # Single item mode
    if item:
        used = usage_between_counts(location, item, open_id, close_id)
        return {"open_count_id": open_id, "close_count_id": close_id, "item": item, "used": used}

    # All items mode
    results = []
    for row in get_items():
        name = str(row["name"])
        used = usage_between_counts(location, name, open_id, close_id)
        results.append({"item": name, "used": used, "base_unit": row["base_unit"]})

    return {"open_count_id": open_id, "close_count_id": close_id, "rows": results}



def sum_transactions_between(location: str, item: str, start_ts: str, end_ts: str) -> float: #takes all these inputs as input and returns a float 
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_base), 0) AS qty
            FROM stock_transactions
            WHERE location_id = ?
              AND item_id = ?
              AND ts > ?
              AND ts <= ?;
            """,
            (location_id, item_id, start_ts, end_ts),
        ).fetchone()

    return float(row["qty"])

def usage_between_counts(location: str, item: str, opening_count_id: int, closing_count_id: int) -> float:
    opening = get_counted_qty(opening_count_id, item)
    closing = get_counted_qty(closing_count_id, item)

    open_meta = get_count(opening_count_id)
    close_meta = get_count(closing_count_id)

    # ensure both counts are for same location
    loc_id = get_location_id(location)
    if int(open_meta["location_id"]) != loc_id or int(close_meta["location_id"]) != loc_id:
        raise ValueError("Counts do not match the given location")

    net_tx = sum_transactions_between(location, item, open_meta["created_at"], close_meta["created_at"])

    # Residual usage:
    return opening + net_tx - closing








def latest_count_for_location(location: str):
    """Return latest stock_counts row for a location (or None)."""
    location_id = get_location_id(location)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, created_at, count_date
            FROM stock_counts
            WHERE location_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1;
            """,
            (location_id,),
        ).fetchone()
    return row  # sqlite3.Row or None


def latest_counted_qty(location: str, item: str) -> tuple[float, str | None]:
    """
    Returns (counted_qty_base, count_created_at) for the latest count at that location.
    If no count exists, returns (0.0, None).
    If count exists but item wasn't counted, returns (0.0, created_at).
    """
    count = latest_count_for_location(location)
    if count is None:
        return 0.0, None

    count_id = int(count["id"])
    created_at = str(count["created_at"])
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT counted_qty_base
            FROM stock_count_lines
            WHERE count_id = ? AND item_id = ?;
            """,
            (count_id, item_id),
        ).fetchone()

    qty = float(row["counted_qty_base"]) if row else 0.0
    return qty, created_at

def net_transactions_since(location: str, item: str, start_ts: str) -> float:
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_base), 0) AS qty
            FROM stock_transactions
            WHERE location_id = ?
              AND item_id = ?
              AND datetime(ts) > datetime(?);
            """,
            (location_id, item_id, start_ts),
        ).fetchone()

    return float(row["qty"])


def current_stock(location: str, item: str) -> float:
    """
    Partial-count friendly:
    current = last_count_line(item, location) + transactions since that count.
    If the item has never been counted at that location, baseline = 0 and we
    use all transactions.
    """
    baseline_qty, baseline_ts = last_count_line(location, item)

    if baseline_qty is None:
        baseline_qty = 0.0
        baseline_ts = None

    delta = transaction_delta_since(location, item, baseline_ts)
    return baseline_qty + delta

def get_items():
    """Return all items as sqlite3.Row objects (for CLI dashboards, etc)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, category, base_unit, cost_per_unit FROM items ORDER BY name;"
        ).fetchall()


def get_or_create_count(location: str, count_date: str) -> int:
    """Return an existing count_id for (location, count_date) or create one."""
    location_id = get_location_id(location)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM stock_counts
            WHERE location_id = ? AND count_date = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1;
            """,
            (location_id, count_date),
        ).fetchone()

    if row is not None:
        return int(row["id"])

    return create_count(location, count_date)


def list_counts(location: str | None = None, limit: int = 25):
    """
    List recent stock counts.
    If location is provided, filter to that location.
    """
    params: list[object] = []
    where_sql = ""

    if location:
        location_id = get_location_id(location)
        where_sql = "WHERE sc.location_id = ?"
        params.append(location_id)

    params.append(limit)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT sc.id, l.name AS location, sc.count_date, sc.created_at
            FROM stock_counts sc
            JOIN locations l ON l.id = sc.location_id
            {where_sql}
            ORDER BY sc.count_date DESC
            LIMIT ?;
            """,
            tuple(params),
        ).fetchall()








#PAR LEVELS 
def set_par_level(location: str, item: str, par_qty_base: float) -> None:
    """
    Create or update the recommended stock level (par) for an item at a location.
    """
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO par_levels (location_id, item_id, par_qty_base)
            VALUES (?, ?, ?)
            ON CONFLICT(location_id, item_id)
            DO UPDATE SET par_qty_base = excluded.par_qty_base;
            """,
            (location_id, item_id, par_qty_base),
        )

def get_par_level(location: str, item: str) -> float | None:
    """
    Return the par level for an item at a location, or None if not set.
    """
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT par_qty_base
            FROM par_levels
            WHERE location_id = ? AND item_id = ?;
            """,
            (location_id, item_id),
        ).fetchone()

    return float(row["par_qty_base"]) if row else None


def combined_order_sheet():
    """
    One combined order for both shops.
    Returns a list of dicts with:
    item, category, unit,
    keele_current, keele_par, keele_shortfall,
    little_current, little_par, little_shortfall,
    total_shortfall, order_qty
    """
    rows = []

    for item_row in get_items():
        name = str(item_row["name"])
        category = str(item_row["category"])
        unit = str(item_row["base_unit"])

        keele_current = current_stock("Keele", name)
        little_current = current_stock("Little Shop", name)

        keele_par = get_par_level("Keele", name) or 0.0
        little_par = get_par_level("Little Shop", name) or 0.0

        keele_shortfall = max(0.0, keele_par - keele_current)
        little_shortfall = max(0.0, little_par - little_current)

        total_shortfall = keele_shortfall + little_shortfall

        rows.append(
            {
                "item": name,
                "category": category,
                "unit": unit,
                "keele_current": keele_current,
                "keele_par": keele_par,
                "keele_shortfall": keele_shortfall,
                "little_current": little_current,
                "little_par": little_par,
                "little_shortfall": little_shortfall,
                "total_shortfall": total_shortfall,
                "order_qty": total_shortfall, 
            }
        )




    # Most useful: biggest total shortfall first
    rows.sort(key=lambda r: r["total_shortfall"], reverse=True)
    return rows




def last_count_line(location: str, item: str):
    """
    Returns (counted_qty_base, baseline_ts) for the most recent count line
    for this item at this location.
    baseline_ts is a datetime string (uses stock_counts.created_at).
    Returns (None, None) if the item has never been counted there.
    """
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT scl.counted_qty_base, sc.created_at
            FROM stock_count_lines scl
            JOIN stock_counts sc ON sc.id = scl.count_id
            WHERE sc.location_id = ? AND scl.item_id = ?
            ORDER BY sc.count_date DESC, datetime(sc.created_at) DESC
            LIMIT 1;
            """,
            (location_id, item_id),
        ).fetchone()

    if not row:
        return None, None

    return float(row["counted_qty_base"]), str(row["created_at"])

def transaction_delta_since(location: str, item: str, since_ts: str | None) -> float:
    """
    Returns signed sum of transactions for this item/location AFTER since_ts.
    Assumes qty_base is already signed by the inserting functions:
      +RECEIVE / +TRANSFER_IN
      -TRANSFER_OUT / -WASTE
      ADJUSTMENT can be +/-.
    """
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    where_since = ""
    params: list[object] = [item_id, location_id]

    if since_ts is not None:
        where_since = "AND datetime(ts) > datetime(?)"
        params.append(since_ts)

    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(qty_base), 0) AS delta
            FROM stock_transactions
            WHERE item_id = ? AND location_id = ?
            {where_since};
            """,
            tuple(params),
        ).fetchone()

    return float(row["delta"])


def _previous_count_baseline(location_id: int, item_id: int, before_created_at: str):
    """
    Returns (baseline_qty, baseline_ts) from the most recent count line BEFORE before_created_at.
    If none exists, returns (0.0, None).
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT scl.counted_qty_base AS qty, sc.created_at AS ts
            FROM stock_count_lines scl
            JOIN stock_counts sc ON sc.id = scl.count_id
            WHERE sc.location_id = ?
              AND scl.item_id = ?
              AND datetime(sc.created_at) < datetime(?)
            ORDER BY datetime(sc.created_at) DESC
            LIMIT 1;
            """,
            (location_id, item_id, before_created_at),
        ).fetchone()

    if row is None:
        return 0.0, None

    return float(row["qty"]), str(row["ts"])


def _tx_delta_between(location_id: int, item_id: int, after_ts: str | None, up_to_ts: str) -> float:
    """
    Sum signed qty_base for (location_id,item_id) where ts is:
      - > after_ts (if provided)
      - <= up_to_ts
    """
    params: list[object] = [location_id, item_id, up_to_ts]
    where_after = ""

    if after_ts is not None:
        where_after = "AND datetime(ts) > datetime(?)"
        params.insert(2, after_ts)  # location_id, item_id, after_ts, up_to_ts

    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(qty_base), 0) AS delta
            FROM stock_transactions
            WHERE location_id = ?
              AND item_id = ?
              {where_after}
              AND datetime(ts) <= datetime(?);
            """,
            tuple(params),
        ).fetchone()

    return float(row["delta"])


def reconcile_count(count_id: int, note: str = "") -> list[dict]:
    """
    Turns a stock count into a true 'reset to reality' by inserting ADJUSTMENT transactions
    for any variance between expected stock-at-count-time and counted quantity.

    Returns a variance report list of dicts:
      {item, unit, expected, counted, diff}
    """
    count = get_count(count_id)

    # block double reconcile
    try:
        already = int(count["is_reconciled"])
    except Exception:
        already = 0

    if already == 1:
        raise ValueError(f"Count {count_id} is already reconciled.")

    location_id = int(count["location_id"])
    count_date = str(count["count_date"])
    count_created_at = str(count["created_at"])

    with get_conn() as conn:
        # Get all lines in this count
        lines = conn.execute(
            """
            SELECT scl.item_id, i.name AS item, i.base_unit AS unit, scl.counted_qty_base AS counted
            FROM stock_count_lines scl
            JOIN items i ON i.id = scl.item_id
            WHERE scl.count_id = ?
            ORDER BY i.name;
            """,
            (count_id,),
        ).fetchall()

        if not lines:
            raise ValueError(f"Count {count_id} has no lines to reconcile.")

        report: list[dict] = []
        eps = 1e-9

        for ln in lines:
            item_id = int(ln["item_id"])
            item = str(ln["item"])
            unit = str(ln["unit"])
            counted = float(ln["counted"])

            baseline_qty, baseline_ts = _previous_count_baseline(location_id, item_id, count_created_at)
            delta = _tx_delta_between(location_id, item_id, baseline_ts, count_created_at)
            expected = baseline_qty + delta

            diff = counted - expected

            report.append(
                {"item": item, "unit": unit, "expected": expected, "counted": counted, "diff": diff}
            )

            if abs(diff) > eps:
                adj_note = note.strip() or f"Reconcile count {count_id} ({count_date})"
                conn.execute(
                    """
                    INSERT INTO stock_transactions (
                        ts,
                        item_id,
                        location_id,
                        qty_base,
                        cost_per_unit_at_time,
                        type,
                        note
                    )
                    VALUES (?, ?, ?, ?, ?, 'ADJUSTMENT', ?);
                    """,
                    (
                        count_created_at,
                        item_id,
                        location_id,
                        diff,
                        get_item_cost_per_unit(item_id),
                        adj_note,
                    ),
                )

        # mark reconciled (locks count)
        conn.execute(
            """
            UPDATE stock_counts
            SET is_reconciled = 1,
                reconciled_at = datetime('now')
            WHERE id = ?;
            """,
            (count_id,),
        )

    return report


def create_transfer_request(from_location: str, to_location: str, request_date: str, note: str = "") -> int:
    init_db()
    from_id = get_location_id(from_location)
    to_id = get_location_id(to_location)

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO transfer_requests (from_location_id, to_location_id, request_date, status, note)
            VALUES (?, ?, ?, 'OPEN', ?)
            """,
            (from_id, to_id, request_date, note or ""),
        )
        return int(cur.lastrowid)

def add_transfer_request_line(request_id: int, item_name: str, requested_qty_base: float) -> None:
    init_db()
    item_id = get_item_id(item_name)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transfer_request_lines (request_id, item_id, requested_qty_base)
            VALUES (?, ?, ?)
            ON CONFLICT(request_id, item_id)
            DO UPDATE SET requested_qty_base = excluded.requested_qty_base;
            """,
            (request_id, item_id, float(requested_qty_base)),
        )

def list_transfer_requests(status: str | None = "OPEN", limit: int = 25):
    init_db()
    where = ""
    params: list[object] = []

    if status:
        where = "WHERE tr.status = ?"
        params.append(status)

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT tr.id,
                   lf.name AS from_location,
                   lt.name AS to_location,
                   tr.request_date,
                   tr.status,
                   tr.note,
                   tr.created_at,
                   tr.fulfilled_at
            FROM transfer_requests tr
            JOIN locations lf ON lf.id = tr.from_location_id
            JOIN locations lt ON lt.id = tr.to_location_id
            {where}
            ORDER BY datetime(tr.created_at) DESC
            LIMIT ?;
            """,
            (*params, int(limit)),
        ).fetchall()
    return rows

def fulfill_transfer_request(request_id: int, note: str = "") -> None:
    """
    Creates TRANSFER_OUT (from) and TRANSFER_IN (to) transactions for outstanding quantities.
    Marks request as FULFILLED if everything is fulfilled, otherwise PARTIAL.
    """
    init_db()

    with get_conn() as conn:
        req = conn.execute(
            """
            SELECT id, from_location_id, to_location_id, status
            FROM transfer_requests
            WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if req is None:
            raise ValueError(f"transfer request {request_id} not found")

        if req["status"] in ("FULFILLED", "CANCELLED"):
            raise 

        from_id = int(req["from_location_id"])
        to_id = int(req["to_location_id"])

        lines = conn.execute(
            """
            SELECT trl.id AS line_id,
                   trl.item_id,
                   i.name AS item,
                   trl.requested_qty_base,
                   trl.fulfilled_qty_base
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            WHERE trl.request_id = ?
            ORDER BY i.name;
            """,
            (request_id,),
        ).fetchall()

        if not lines:
            raise ValueError("request has no lines")

        # Fulfill outstanding qty per line
        for ln in lines:
            requested = float(ln["requested_qty_base"])
            fulfilled = float(ln["fulfilled_qty_base"])
            outstanding = requested - fulfilled

            if outstanding <= 1e-9:
                continue

            item_id = int(ln["item_id"])
            item_name = str(ln["item"])

            # Create stock ledger movements
            tx_note = note.strip() or f"Fulfill transfer request {request_id}"
            # OUT of Keele (from)
            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_OUT', ?)
                """,
                (
                    item_id,
                    from_id,
                    -outstanding,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )
            # IN to Little (to)
            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_IN', ?)
                """,
                (
                    item_id,
                    to_id,
                    outstanding,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )

            # Mark line fulfilled
            conn.execute(
                """
                UPDATE transfer_request_lines
                SET fulfilled_qty_base = fulfilled_qty_base + ?
                WHERE id = ?
                """,
                (outstanding, int(ln["line_id"])),
            )

        # Update request status
        remaining = conn.execute(
            """
            SELECT COUNT(*) AS remaining
            FROM transfer_request_lines
            WHERE request_id = ?
              AND (requested_qty_base - fulfilled_qty_base) > 1e-9
            """,
            (request_id,),
        ).fetchone()

        new_status = "FULFILLED" if int(remaining["remaining"]) == 0 else "PARTIAL"

        conn.execute(
            """
            UPDATE transfer_requests
            SET status = ?, fulfilled_at = CASE WHEN ?='FULFILLED' THEN datetime('now') ELSE fulfilled_at END
            WHERE id = ?
            """,
            (new_status, new_status, request_id),
        )



def create_request_from_par(to_location: str, request_date: str, note: str = "") -> int:
    """
    Creates or reuses a transfer request (from Keele -> to_location) for request_date using PAR shortfalls at to_location.
    Adds/updates one line per item where (par - current_stock) > 0.

    Because we enforce a UNIQUE constraint on (from_location_id, to_location_id, request_date),
    this function must reuse the existing request if one already exists.
    """
    init_db()

    from_location = "Keele"

    from_id = get_location_id(from_location)
    to_id = get_location_id(to_location)

    with get_conn() as conn:
        # 1) Get-or-create request header
        existing = conn.execute(
            """
            SELECT id
            FROM transfer_requests
            WHERE from_location_id = ?
              AND to_location_id = ?
              AND request_date = ?
            LIMIT 1;
            """,
            (from_id, to_id, request_date),
        ).fetchone()

        if existing is not None:
            req_id = int(existing["id"])
            # Optional: update note if provided (keep existing if blank)
            if note.strip():
                conn.execute(
                    "UPDATE transfer_requests SET note = ? WHERE id = ?;",
                    (note.strip(), req_id),
                )
        else:
            cur = conn.execute(
                """
                INSERT INTO transfer_requests (from_location_id, to_location_id, request_date, status, note)
                VALUES (?, ?, ?, 'OPEN', ?)
                """,
                (from_id, to_id, request_date, note or ""),
            )
            req_id = int(cur.lastrowid)

        # 2) Pull PAR levels for the destination location
        rows = conn.execute(
            """
            SELECT i.id AS item_id,
                   i.name AS item,
                   i.base_unit AS unit,
                   p.par_qty_base AS par_qty
            FROM par_levels p
            JOIN items i ON i.id = p.item_id
            WHERE p.location_id = ?
            ORDER BY i.name;
            """,
            (to_id,),
        ).fetchall()

    # 3) For each PAR item, compute shortfall and upsert request lines
    # (use existing helpers which open their own connection — ok for now)
    for r in rows:
        item_id = int(r["item_id"])
        item = str(r["item"])
        par_qty = float(r["par_qty"])

        on_hand = latest_count_qty(to_location, item_id, request_date)
        short = par_qty - on_hand

        if short > 1e-9:
            add_transfer_request_line(req_id, item, short)
        else:
            add_transfer_request_line(req_id, item, 0.0)

    return req_id


def confirm_request_transfer(request_date: str, note: str = "") -> dict:
    """
    Create or refresh the Little Shop request for request_date, then fulfill only the
    quantities that Keele can actually supply right now based on current stock.
    """
    init_db()
    request_id = create_request_from_par("Little Shop", request_date, note=note or "Web request confirmation")

    moved_lines = 0
    moved_qty = 0.0

    with get_conn() as conn:
        req = conn.execute(
            """
            SELECT id, from_location_id, to_location_id, status
            FROM transfer_requests
            WHERE id = ?;
            """,
            (request_id,),
        ).fetchone()

        if req is None:
            raise ValueError(f"transfer request {request_id} not found")

        from_id = int(req["from_location_id"])
        to_id = int(req["to_location_id"])

        lines = conn.execute(
            """
            SELECT trl.id AS line_id,
                   trl.item_id,
                   i.name AS item,
                   trl.requested_qty_base,
                   trl.fulfilled_qty_base
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            WHERE trl.request_id = ?
            ORDER BY i.name;
            """,
            (request_id,),
        ).fetchall()

        if not lines:
            raise ValueError("request has no lines")

        for ln in lines:
            requested = float(ln["requested_qty_base"] or 0.0)
            fulfilled = float(ln["fulfilled_qty_base"] or 0.0)
            outstanding = max(requested - fulfilled, 0.0)
            if outstanding <= 1e-9:
                continue

            item_id = int(ln["item_id"])
            item_name = str(ln["item"])
            available = max(current_stock("Keele", item_name), 0.0)
            transfer_qty = min(outstanding, available)
            if transfer_qty <= 1e-9:
                continue

            tx_note = note.strip() or f"Transfer request {request_id} confirmed in web app"

            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_OUT', ?)
                """,
                (
                    item_id,
                    from_id,
                    -transfer_qty,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )

            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_IN', ?)
                """,
                (
                    item_id,
                    to_id,
                    transfer_qty,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )

            conn.execute(
                """
                UPDATE transfer_request_lines
                SET fulfilled_qty_base = fulfilled_qty_base + ?
                WHERE id = ?;
                """,
                (transfer_qty, int(ln["line_id"])),
            )

            moved_lines += 1
            moved_qty += transfer_qty

        remaining = conn.execute(
            """
            SELECT COUNT(*) AS remaining
            FROM transfer_request_lines
            WHERE request_id = ?
              AND (requested_qty_base - fulfilled_qty_base) > 1e-9;
            """,
            (request_id,),
        ).fetchone()

        new_status = "FULFILLED" if int(remaining["remaining"] or 0) == 0 else "PARTIAL"
        conn.execute(
            """
            UPDATE transfer_requests
            SET status = ?,
                fulfilled_at = CASE WHEN ?='FULFILLED' THEN datetime('now') ELSE fulfilled_at END
            WHERE id = ?;
            """,
            (new_status, new_status, request_id),
        )

    return {
        "request_id": request_id,
        "moved_lines": moved_lines,
        "moved_qty": moved_qty,
    }


def confirm_transfer_request_by_id(request_id: int, note: str = "") -> dict:
    init_db()

    moved_lines = 0
    moved_qty = 0.0

    with get_conn() as conn:
        req = conn.execute(
            """
            SELECT id, from_location_id, to_location_id, status
            FROM transfer_requests
            WHERE id = ?;
            """,
            (request_id,),
        ).fetchone()

        if req is None:
            raise ValueError(f"transfer request {request_id} not found")

        if str(req["status"]) == "CANCELLED":
            raise ValueError("Cancelled requests cannot be confirmed.")

        from_id = int(req["from_location_id"])
        to_id = int(req["to_location_id"])

        lines = conn.execute(
            """
            SELECT trl.id AS line_id,
                   trl.item_id,
                   i.name AS item,
                   trl.requested_qty_base,
                   trl.fulfilled_qty_base
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            WHERE trl.request_id = ?
            ORDER BY i.name;
            """,
            (request_id,),
        ).fetchall()

        if not lines:
            raise ValueError("request has no lines")

        for ln in lines:
            requested = float(ln["requested_qty_base"] or 0.0)
            fulfilled = float(ln["fulfilled_qty_base"] or 0.0)
            outstanding = max(requested - fulfilled, 0.0)
            if outstanding <= 1e-9:
                continue

            item_id = int(ln["item_id"])
            item_name = str(ln["item"])
            available = max(current_stock("Keele", item_name), 0.0)
            transfer_qty = min(outstanding, available)
            if transfer_qty <= 1e-9:
                continue

            tx_note = note.strip() or f"Transfer request {request_id} confirmed"

            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_OUT', ?)
                """,
                (
                    item_id,
                    from_id,
                    -transfer_qty,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )

            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, ?, 'TRANSFER_IN', ?)
                """,
                (
                    item_id,
                    to_id,
                    transfer_qty,
                    get_item_cost_per_unit(item_id),
                    request_id,
                    tx_note,
                ),
            )

            conn.execute(
                """
                UPDATE transfer_request_lines
                SET fulfilled_qty_base = fulfilled_qty_base + ?
                WHERE id = ?;
                """,
                (transfer_qty, int(ln["line_id"])),
            )

            moved_lines += 1
            moved_qty += transfer_qty

        remaining = conn.execute(
            """
            SELECT COUNT(*) AS remaining
            FROM transfer_request_lines
            WHERE request_id = ?
              AND (requested_qty_base - fulfilled_qty_base) > 1e-9;
            """,
            (request_id,),
        ).fetchone()

        new_status = "FULFILLED" if int(remaining["remaining"] or 0) == 0 else "PARTIAL"
        conn.execute(
            """
            UPDATE transfer_requests
            SET status = ?,
                fulfilled_at = CASE WHEN ?='FULFILLED' THEN datetime('now') ELSE fulfilled_at END
            WHERE id = ?;
            """,
            (new_status, new_status, request_id),
        )

    return {
        "request_id": request_id,
        "moved_lines": moved_lines,
        "moved_qty": moved_qty,
    }


def cancel_transfer_request(request_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM transfer_requests WHERE id = ?;",
            (int(request_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"transfer request {request_id} not found")
        if str(row["status"]) == "FULFILLED":
            raise ValueError("Fulfilled requests cannot be cancelled.")
        conn.execute(
            "UPDATE transfer_requests SET status = 'CANCELLED' WHERE id = ?;",
            (int(request_id),),
        )


def get_transfer_request(request_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT tr.id,
                   lf.name AS from_location,
                   lt.name AS to_location,
                   tr.request_date,
                   tr.status,
                   tr.note,
                   tr.created_at,
                   tr.fulfilled_at
            FROM transfer_requests tr
            JOIN locations lf ON lf.id = tr.from_location_id
            JOIN locations lt ON lt.id = tr.to_location_id
            WHERE tr.id = ?;
            """,
            (int(request_id),),
        ).fetchone()
    if row is None:
        raise ValueError(f"transfer request {request_id} not found")
    return row


def get_transfer_request_lines(request_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT trl.id,
                   i.id AS item_id,
                   i.name,
                   i.category,
                   i.base_unit,
                   trl.requested_qty_base,
                   trl.fulfilled_qty_base
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            WHERE trl.request_id = ?
            ORDER BY LOWER(i.category), LOWER(i.name);
            """,
            (int(request_id),),
        ).fetchall()


def get_transfer_request_activity(request_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT st.id,
                   st.ts,
                   st.type,
                   ABS(st.qty_base) AS qty_base,
                   st.note,
                   i.name AS item_name,
                   l.name AS location_name
            FROM stock_transactions st
            JOIN items i ON i.id = st.item_id
            JOIN locations l ON l.id = st.location_id
            WHERE st.transfer_request_id = ?
            ORDER BY datetime(st.ts) DESC, st.id DESC;
            """,
            (int(request_id),),
        ).fetchall()


def recent_transfer_requests(limit: int = 12):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT tr.id,
                   lf.name AS from_location,
                   lt.name AS to_location,
                   tr.request_date,
                   tr.status,
                   tr.note,
                   tr.created_at,
                   tr.fulfilled_at,
                   COALESCE(SUM(trl.requested_qty_base), 0) AS requested_qty,
                   COALESCE(SUM(trl.fulfilled_qty_base), 0) AS fulfilled_qty,
                   COUNT(trl.id) AS line_count
            FROM transfer_requests tr
            JOIN locations lf ON lf.id = tr.from_location_id
            JOIN locations lt ON lt.id = tr.to_location_id
            LEFT JOIN transfer_request_lines trl ON trl.request_id = tr.id
            GROUP BY tr.id, lf.name, lt.name, tr.request_date, tr.status, tr.note, tr.created_at, tr.fulfilled_at
            ORDER BY datetime(tr.created_at) DESC, tr.id DESC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()


def outstanding_request_qty(from_location: str = "Keele", to_location: str = "Little Shop") -> dict[str, float]:
    """
    Returns {item_name: outstanding_qty_base} for OPEN/PARTIAL requests from->to.
    """
    init_db()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.name AS item,
                   SUM(trl.requested_qty_base - trl.fulfilled_qty_base) AS outstanding
            FROM transfer_requests tr
            JOIN locations lf ON lf.id = tr.from_location_id
            JOIN locations lt ON lt.id = tr.to_location_id
            JOIN transfer_request_lines trl ON trl.request_id = tr.id
            JOIN items i ON i.id = trl.item_id
            WHERE lf.name = ?
              AND lt.name = ?
              AND tr.status IN ('OPEN', 'PARTIAL')
              AND (trl.requested_qty_base - trl.fulfilled_qty_base) > 1e-9
            GROUP BY i.name
            ORDER BY i.name;
            """,
            (from_location, to_location),
        ).fetchall()

    return {str(r["item"]): float(r["outstanding"]) for r in rows}

def generate_supplier_order(request_location_name="Little Shop", source_location_name="Keele"):
    conn = get_conn()
    cur = conn.cursor()

    # get location ids
    cur.execute("SELECT id FROM locations WHERE name = ?", (request_location_name,))
    req_loc = cur.fetchone()
    if not req_loc:
        raise ValueError(f"Unknown request location: {request_location_name}")

    cur.execute("SELECT id FROM locations WHERE name = ?", (source_location_name,))
    src_loc = cur.fetchone()
    if not src_loc:
        raise ValueError(f"Unknown source location: {source_location_name}")

    request_location_id = req_loc["id"]
    source_location_id = src_loc["id"]

    # get Keele par levels
    cur.execute("""
        SELECT
            i.id AS item_id,
            i.name,
            i.category,
            i.base_unit,
            p.par_qty_base
        FROM par_levels p
        JOIN items i ON i.id = p.item_id
        WHERE p.location_id = ?
        ORDER BY i.name, i.id
    """, (source_location_id,))
    keele_par_rows = cur.fetchall()

    results = []

    for row in keele_par_rows:
        item_id = row["item_id"]
        keele_par_qty = float(row["par_qty_base"] or 0)

        # current stock at Keele
        cur.execute("""
            SELECT COALESCE(SUM(qty_base), 0) AS stock_on_hand
            FROM stock_transactions
            WHERE location_id = ? AND item_id = ?
        """, (source_location_id, item_id))
        keele_stock = float(cur.fetchone()["stock_on_hand"] or 0)

        # how much Little Shop needs
        cur.execute("""
            SELECT par_qty_base
            FROM par_levels
            WHERE location_id = ? AND item_id = ?
        """, (request_location_id, item_id))
        req_par_row = cur.fetchone()

        pick_qty = 0.0
        request_qty = 0.0

        if req_par_row:
            request_par_qty = float(req_par_row["par_qty_base"] or 0)

            cur.execute("""
                SELECT COALESCE(SUM(qty_base), 0) AS stock_on_hand
                FROM stock_transactions
                WHERE location_id = ? AND item_id = ?
            """, (request_location_id, item_id))
            req_stock = float(cur.fetchone()["stock_on_hand"] or 0)

            request_qty = max(request_par_qty - req_stock, 0)
            pick_qty = min(request_qty, keele_stock)

        projected_keele_stock = keele_stock - pick_qty
        supplier_order_qty = max(keele_par_qty - projected_keele_stock, 0)

        if supplier_order_qty > 0:
            supplier_summary = get_item_supplier_summary(item_id)
            results.append({
                "supplier": supplier_summary,
                "item_id": item_id,
                "name": row["name"],
                "category": row["category"],
                "base_unit": row["base_unit"],
                "keele_par_qty": keele_par_qty,
                "keele_stock": keele_stock,
                "pick_qty": pick_qty,
                "projected_keele_stock": projected_keele_stock,
                "supplier_order_qty": supplier_order_qty,
            })

    conn.close()

    # sort by supplier then item
    results.sort(key=lambda r: (r["supplier"], r["name"]))

    return results


def create_supplier_order(order_date: str, note: str = "") -> int:
    init_db()
    rows = generate_supplier_order()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO supplier_orders (order_date, status, note)
            VALUES (?, 'DRAFT', ?);
            """,
            (order_date, note or ""),
        )
        order_id = int(cur.lastrowid)

        for row in rows:
            conn.execute(
                """
                INSERT INTO supplier_order_lines (
                    order_id,
                    item_id,
                    supplier_name,
                    ordered_qty_base,
                    received_qty_base,
                    unit_cost
                )
                VALUES (?, ?, ?, ?, 0, ?);
                """,
                (
                    order_id,
                    int(row["item_id"]),
                    str(row["supplier"] or "Unknown"),
                    float(row["supplier_order_qty"] or 0.0),
                    float(get_item_cost_per_unit(int(row["item_id"]))),
                ),
            )

    return order_id


def list_supplier_orders(status: str | None = None, limit: int = 20):
    with get_conn() as conn:
        params: list[object] = []
        where = ""
        if status:
            where = "WHERE so.status = ?"
            params.append(status)
        return conn.execute(
            f"""
            SELECT so.id,
                   so.order_date,
                   so.status,
                   so.note,
                   so.created_at,
                   so.ordered_at,
                   so.received_at,
                   COUNT(sol.id) AS line_count,
                   COALESCE(SUM(sol.ordered_qty_base), 0) AS ordered_qty,
                   COALESCE(SUM(sol.received_qty_base), 0) AS received_qty
            FROM supplier_orders so
            LEFT JOIN supplier_order_lines sol ON sol.order_id = so.id
            {where}
            GROUP BY so.id, so.order_date, so.status, so.note, so.created_at, so.ordered_at, so.received_at
            ORDER BY datetime(so.created_at) DESC, so.id DESC
            LIMIT ?;
            """,
            (*params, int(limit)),
        ).fetchall()


def get_supplier_order(order_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, order_date, status, note, created_at, ordered_at, received_at
            FROM supplier_orders
            WHERE id = ?;
            """,
            (int(order_id),),
        ).fetchone()
    if row is None:
        raise ValueError(f"Supplier order {order_id} not found.")
    return row


def get_supplier_order_lines(order_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT sol.id,
                   sol.order_id,
                   sol.supplier_name,
                   sol.ordered_qty_base,
                   sol.received_qty_base,
                   sol.unit_cost,
                   i.id AS item_id,
                   i.name,
                   i.category,
                   i.base_unit
            FROM supplier_order_lines sol
            JOIN items i ON i.id = sol.item_id
            WHERE sol.order_id = ?
            ORDER BY LOWER(sol.supplier_name), LOWER(i.category), LOWER(i.name);
            """,
            (int(order_id),),
        ).fetchall()


def create_supplier_invoice(
    order_id: int,
    original_filename: str,
    stored_filename: str,
    content_type: str = "",
    invoice_reference: str = "",
    supplier_name: str = "",
    note: str = "",
) -> int:
    get_supplier_order(order_id)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO supplier_invoices (
                order_id,
                invoice_reference,
                supplier_name,
                original_filename,
                stored_filename,
                content_type,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(order_id),
                invoice_reference.strip(),
                supplier_name.strip(),
                original_filename.strip(),
                stored_filename.strip(),
                content_type.strip(),
                note.strip(),
            ),
        )
        return int(cur.lastrowid)


def list_supplier_invoices(order_id: int | None = None, limit: int = 50):
    with get_conn() as conn:
        if order_id is None:
            return conn.execute(
                """
                SELECT si.id,
                       si.order_id,
                       si.invoice_reference,
                       si.supplier_name,
                       si.original_filename,
                       si.stored_filename,
                       si.content_type,
                       si.note,
                       si.review_status,
                       si.uploaded_at,
                       si.reviewed_at,
                       so.order_date,
                       so.status AS order_status
                FROM supplier_invoices si
                JOIN supplier_orders so ON so.id = si.order_id
                ORDER BY datetime(si.uploaded_at) DESC, si.id DESC
                LIMIT ?;
                """,
                (int(limit),),
            ).fetchall()

        return conn.execute(
            """
            SELECT si.id,
                   si.order_id,
                   si.invoice_reference,
                   si.supplier_name,
                   si.original_filename,
                   si.stored_filename,
                   si.content_type,
                   si.note,
                   si.review_status,
                   si.uploaded_at,
                   si.reviewed_at,
                   so.order_date,
                   so.status AS order_status
            FROM supplier_invoices si
            JOIN supplier_orders so ON so.id = si.order_id
            WHERE si.order_id = ?
            ORDER BY datetime(si.uploaded_at) DESC, si.id DESC
            LIMIT ?;
            """,
            (int(order_id), int(limit)),
        ).fetchall()


def get_supplier_invoice(invoice_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT si.id,
                   si.order_id,
                   si.invoice_reference,
                   si.supplier_name,
                   si.original_filename,
                   si.stored_filename,
                   si.content_type,
                   si.note,
                   si.review_status,
                   si.uploaded_at,
                   si.reviewed_at,
                   so.order_date,
                   so.status AS order_status
            FROM supplier_invoices si
            JOIN supplier_orders so ON so.id = si.order_id
            WHERE si.id = ?;
            """,
            (int(invoice_id),),
        ).fetchone()
    if row is None:
        raise ValueError(f"Supplier invoice {invoice_id} not found.")
    return row


def mark_supplier_invoice_reviewed(invoice_id: int, invoice_reference: str = "", note: str = "") -> None:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE supplier_invoices
            SET invoice_reference = CASE WHEN ? = '' THEN invoice_reference ELSE ? END,
                note = CASE WHEN ? = '' THEN note ELSE ? END,
                review_status = 'REVIEWED',
                reviewed_at = datetime('now')
            WHERE id = ?;
            """,
            (
                invoice_reference.strip(),
                invoice_reference.strip(),
                note.strip(),
                note.strip(),
                int(invoice_id),
            ),
        )
        if cur.rowcount <= 0:
            raise ValueError(f"Supplier invoice {invoice_id} not found.")


def mark_supplier_order_ordered(order_id: int) -> None:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE supplier_orders
            SET status = 'ORDERED',
                ordered_at = datetime('now')
            WHERE id = ?
              AND status = 'DRAFT';
            """,
            (int(order_id),),
        )
        if cur.rowcount <= 0:
            raise ValueError("Only draft supplier orders can be marked as ordered.")


def cancel_supplier_order(order_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM supplier_orders WHERE id = ?;",
            (int(order_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Supplier order {order_id} not found.")
        if str(row["status"]) == "RECEIVED":
            raise ValueError("Received supplier orders cannot be cancelled.")
        conn.execute(
            "UPDATE supplier_orders SET status = 'CANCELLED' WHERE id = ?;",
            (int(order_id),),
        )


def receive_supplier_order(order_id: int, note: str = "") -> dict:
    order = get_supplier_order(order_id)
    if str(order["status"]) == "CANCELLED":
        raise ValueError("Cancelled supplier orders cannot be received.")

    received_lines = 0
    received_qty = 0.0
    tx_note = note.strip() or f"Supplier order {order_id} received"
    keele_id = get_location_id("Keele")

    with get_conn() as conn:
        lines = conn.execute(
            """
            SELECT id, item_id, ordered_qty_base, received_qty_base, unit_cost
            FROM supplier_order_lines
            WHERE order_id = ?;
            """,
            (int(order_id),),
        ).fetchall()
        if not lines:
            raise ValueError("Supplier order has no lines.")

        for line in lines:
            outstanding = float(line["ordered_qty_base"] or 0.0) - float(line["received_qty_base"] or 0.0)
            if outstanding <= 1e-9:
                continue

            item_id = int(line["item_id"])
            conn.execute(
                """
                INSERT INTO stock_transactions (
                    item_id,
                    location_id,
                    qty_base,
                    cost_per_unit_at_time,
                    transfer_request_id,
                    type,
                    note
                )
                VALUES (?, ?, ?, ?, NULL, 'RECEIVE', ?);
                """,
                (
                    item_id,
                    keele_id,
                    outstanding,
                    float(line["unit_cost"] or 0.0),
                    tx_note,
                ),
            )
            conn.execute(
                """
                UPDATE supplier_order_lines
                SET received_qty_base = ordered_qty_base
                WHERE id = ?;
                """,
                (int(line["id"]),),
            )
            received_lines += 1
            received_qty += outstanding

        conn.execute(
            """
            UPDATE supplier_orders
            SET status = 'RECEIVED',
                received_at = datetime('now'),
                ordered_at = COALESCE(ordered_at, datetime('now'))
            WHERE id = ?;
            """,
            (int(order_id),),
        )

    return {
        "order_id": int(order_id),
        "received_lines": received_lines,
        "received_qty": received_qty,
    }

def export_supplier_order_to_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "item_id",
            "item_name",
            "category",
            "base_unit",
            "keele_par_qty",
            "keele_stock",
            "pick_qty",
            "projected_keele_stock",
            "supplier_order_qty",
        ])

        for row in rows:
            writer.writerow([
                row["item_id"],
                row["name"],
                row["category"],
                row["base_unit"],
                row["keele_par_qty"],
                row["keele_stock"],
                row["pick_qty"],
                row["projected_keele_stock"],
                row["supplier_order_qty"],
            ])


def count_line_count(count_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM stock_count_lines WHERE count_id = ?;",
            (count_id,),
        ).fetchone()
    return int(row["n"])


def get_request_lines(request_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT i.name AS item,
                   i.base_unit AS unit,
                   i.cost_per_unit AS cost_per_unit,
                   trl.requested_qty_base AS requested,
                   trl.fulfilled_qty_base AS fulfilled,
                   (trl.requested_qty_base - trl.fulfilled_qty_base) AS outstanding
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            WHERE trl.request_id = ?
            ORDER BY i.name;
            """,
            (request_id,),
        ).fetchall()


def get_item_by_id(item_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, base_unit, cost_per_unit FROM items WHERE id = ?;",
            (item_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Unknown item_id: {item_id}")
    return row  # sqlite3.Row


def add_count_line_by_item_id(count_id: int, item_id: int, counted_qty_base: float) -> None:
    """
    Same as add_count_line, but uses item_id directly (for CSV imports).
    Refuses to modify a count once reconciled.
    """
    with get_conn() as conn:
        # Lock: block edits after reconcile (if column exists in your DB)
        try:
            row = conn.execute(
                "SELECT is_reconciled FROM stock_counts WHERE id = ?;",
                (count_id,),
            ).fetchone()
            if row is not None and int(row["is_reconciled"]) == 1:
                raise ValueError(f"Count {count_id} is reconciled; you can't change lines.")
        except sqlite3.OperationalError:
            # if is_reconciled column isn't present in some DBs, ignore
            pass

        conn.execute(
            """
            INSERT INTO stock_count_lines (count_id, item_id, counted_qty_base)
            VALUES (?, ?, ?)
            ON CONFLICT(count_id, item_id)
            DO UPDATE SET counted_qty_base = excluded.counted_qty_base;
            """,
            (count_id, int(item_id), float(counted_qty_base)),
        )



def latest_count_qty(location_name: str, item_id: int, as_of_date: str) -> float:
    """
    Returns counted_qty_base for the most recent stock count line at location on/before as_of_date.
    If no count found, returns 0.0
    """
    init_db()
    loc_id = get_location_id(location_name)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT scl.counted_qty_base AS qty
            FROM stock_counts sc
            JOIN stock_count_lines scl ON scl.count_id = sc.id
            WHERE sc.location_id = ?
              AND sc.count_date <= ?
              AND scl.item_id = ?
            ORDER BY sc.count_date DESC, sc.created_at DESC
            LIMIT 1;
            """,
            (loc_id, as_of_date, item_id),
        ).fetchone()

    return float(row["qty"]) if row is not None else 0.0

import csv


def import_items_and_par_levels(csv_path):
    conn = get_conn()
    cur = conn.cursor()

    # get location ids
    cur.execute("SELECT id FROM locations WHERE name = 'Little Shop'")
    little_shop_id = cur.fetchone()["id"]

    cur.execute("SELECT id FROM locations WHERE name = 'Keele'")
    keele_id = cur.fetchone()["id"]

    imported_rows = 0
    skipped_rows = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        raw_headers = reader.fieldnames or []
        normalized_headers = {"_".join((header or "").strip().lower().split()) for header in raw_headers}
        required_headers = {"item_name", "category", "base_unit", "par_little_shop", "par_keele", "supplier"}
        if not required_headers.issubset(normalized_headers):
            raise ValueError(
                "CSV must contain headers: item_name, category, base_unit, par_little_shop, par_keele, supplier"
            )

        for line_no, row in enumerate(reader, start=2):
            normalized_row = {
                "_".join((key or "").strip().lower().split()): (value or "").strip()
                for key, value in row.items()
            }

            name = normalized_row.get("item_name", "")
            category = normalized_row.get("category", "")
            base_unit_raw = normalized_row.get("base_unit", "")
            supplier_name = normalized_row.get("supplier", "")
            reference_raw = (
                normalized_row.get("ref")
                or normalized_row.get("reference")
                or normalized_row.get("reference_number")
                or normalized_row.get("supplier_ref")
                or ""
            )
            little_par_raw = normalized_row.get("par_little_shop", "")
            keele_par_raw = normalized_row.get("par_keele", "")
            cost_per_unit_raw = (
                normalized_row.get("cost_per_unit")
                or normalized_row.get("unit_cost")
                or normalized_row.get("cost")
                or "0"
            )

            # Ignore fully blank/spacer rows from Sheets exports.
            if not any([name, category, base_unit_raw, supplier_name, reference_raw, little_par_raw, keele_par_raw]):
                skipped_rows += 1
                continue

            if not name:
                raise ValueError(f"Line {line_no}: item_name is required")
            if not category:
                raise ValueError(f"Line {line_no}: category is required for '{name}'")
            if not base_unit_raw:
                raise ValueError(f"Line {line_no}: base_unit is required for '{name}'")
            try:
                base_unit = normalize_base_unit(base_unit_raw)
            except ValueError as exc:
                raise ValueError(f"Line {line_no}: {exc} for '{name}'") from exc
            try:
                cost_per_unit = normalize_cost_per_unit(cost_per_unit_raw)
            except ValueError as exc:
                raise ValueError(f"Line {line_no}: {exc} for '{name}'") from exc

            cur.execute("""
                INSERT INTO items (name, category, base_unit, cost_per_unit, supplier_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name)
                DO UPDATE SET
                    category = excluded.category,
                    base_unit = excluded.base_unit,
                    cost_per_unit = excluded.cost_per_unit,
                    supplier_id = excluded.supplier_id
            """, (name, category, base_unit, cost_per_unit, None))

            cur.execute("SELECT id FROM items WHERE name = ?", (name,))
            item_id = cur.fetchone()["id"]

            try:
                supplier_links = _parse_supplier_links(supplier_name, reference_raw)
            except ValueError as exc:
                raise ValueError(f"Line {line_no}: {exc} for '{name}'") from exc

            primary_supplier_id = _sync_item_suppliers(cur, item_id, supplier_links)
            cur.execute(
                "UPDATE items SET supplier_id = ? WHERE id = ?",
                (primary_supplier_id, item_id),
            )

            if little_par_raw:
                par = float(little_par_raw)
                cur.execute("""
                    INSERT INTO par_levels (item_id, location_id, par_qty_base)
                    VALUES (?, ?, ?)
                    ON CONFLICT(item_id, location_id)
                    DO UPDATE SET par_qty_base = excluded.par_qty_base
                """, (item_id, little_shop_id, par))

            if keele_par_raw:
                par = float(keele_par_raw)
                cur.execute("""
                    INSERT INTO par_levels (item_id, location_id, par_qty_base)
                    VALUES (?, ?, ?)
                    ON CONFLICT(item_id, location_id)
                    DO UPDATE SET par_qty_base = excluded.par_qty_base
                """, (item_id, keele_id, par))

            imported_rows += 1

    conn.commit()
    conn.close()

    print(f"Imported {imported_rows} item rows.")
    if skipped_rows:
        print(f"Skipped {skipped_rows} blank rows.")


def generate_request_from_par(location_name):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM locations WHERE name = ?", (location_name,))
    loc = cur.fetchone()
    if not loc:
        raise ValueError(f"Unknown location: {location_name}")

    location_id = loc["id"]

    cur.execute("""
        SELECT
            i.id AS item_id,
            i.name,
            i.category,
            i.base_unit,
            p.par_qty_base
        FROM par_levels p
        JOIN items i ON i.id = p.item_id
        WHERE p.location_id = ?
        ORDER BY i.id
    """, (location_id,))
    par_rows = cur.fetchall()

    results = []

    for row in par_rows:
        item_id = row["item_id"]
        par_qty = float(row["par_qty_base"] or 0)

        cur.execute("""
            SELECT COALESCE(SUM(qty_base), 0) AS stock_on_hand
            FROM stock_transactions
            WHERE location_id = ? AND item_id = ?
        """, (location_id, item_id))
        stock_row = cur.fetchone()
        stock_on_hand = float(stock_row["stock_on_hand"] or 0)

        request_qty = max(par_qty - stock_on_hand, 0)

        if request_qty > 0:
            results.append({
                "item_id": item_id,
                "name": row["name"],
                "category": row["category"],
                "base_unit": row["base_unit"],
                "par_qty": par_qty,
                "stock_on_hand": stock_on_hand,
                "request_qty": request_qty,
            })

    conn.close()
    return results


def export_request_to_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "item_id",
            "item_name",
            "category",
            "base_unit",
            "par_qty",
            "stock_on_hand",
            "request_qty",
        ])

        for row in rows:
            writer.writerow([
                row["item_id"],
                row["name"],
                row["category"],
                row["base_unit"],
                row["par_qty"],
                row["stock_on_hand"],
                row["request_qty"],
            ])


def generate_keele_pick_list(request_location_name="Little Shop", source_location_name="Keele"):
    conn = get_conn()
    cur = conn.cursor()

    # get location ids
    cur.execute("SELECT id FROM locations WHERE name = ?", (request_location_name,))
    req_loc = cur.fetchone()
    if not req_loc:
        raise ValueError(f"Unknown request location: {request_location_name}")

    cur.execute("SELECT id FROM locations WHERE name = ?", (source_location_name,))
    src_loc = cur.fetchone()
    if not src_loc:
        raise ValueError(f"Unknown source location: {source_location_name}")

    request_location_id = req_loc["id"]
    source_location_id = src_loc["id"]

    # get par levels for request location
    cur.execute("""
        SELECT
            i.id AS item_id,
            i.name,
            i.category,
            i.base_unit,
            p.par_qty_base
        FROM par_levels p
        JOIN items i ON i.id = p.item_id
        WHERE p.location_id = ?
        ORDER BY i.id
    """, (request_location_id,))
    par_rows = cur.fetchall()

    results = []

    for row in par_rows:
        item_id = row["item_id"]
        par_qty = float(row["par_qty_base"] or 0)

        # stock at requesting location
        cur.execute("""
            SELECT COALESCE(SUM(qty_base), 0) AS stock_on_hand
            FROM stock_transactions
            WHERE location_id = ? AND item_id = ?
        """, (request_location_id, item_id))
        req_stock = float(cur.fetchone()["stock_on_hand"] or 0)

        request_qty = max(par_qty - req_stock, 0)
        if request_qty <= 0:
            continue

        # stock at Keele
        cur.execute("""
            SELECT COALESCE(SUM(qty_base), 0) AS stock_on_hand
            FROM stock_transactions
            WHERE location_id = ? AND item_id = ?
        """, (source_location_id, item_id))
        keele_stock = float(cur.fetchone()["stock_on_hand"] or 0)

        pick_qty = min(request_qty, keele_stock)
        short_qty = max(request_qty - keele_stock, 0)

        results.append({
            "item_id": item_id,
            "name": row["name"],
            "category": row["category"],
            "base_unit": row["base_unit"],
            "request_qty": request_qty,
            "keele_stock": keele_stock,
            "pick_qty": pick_qty,
            "short_qty": short_qty,
        })

    conn.close()
    return results

def export_pick_list_to_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "item_id",
            "item_name",
            "category",
            "base_unit",
            "request_qty",
            "keele_stock",
            "pick_qty",
            "short_qty",
        ])

        for row in rows:
            writer.writerow([
                row["item_id"],
                row["name"],
                row["category"],
                row["base_unit"],
                row["request_qty"],
                row["keele_stock"],
                row["pick_qty"],
                row["short_qty"],
            ])





from .sheets import get_spreadsheet


def export_count_to_sheet(location: str):
    sheet = get_sheet(f"{location} Count")
    items = get_items()

    data = [["Category", "Item Name", "Unit", "Counted Qty"]]
    row_groups: list[tuple[int, int]] = []

    items_sorted = sorted(
        items,
        key=lambda item: (
            str(item["category"]).strip().lower(),
            str(item["name"]).strip().lower(),
        ),
    )

    current_category = None
    current_group_start = None

    for item in items_sorted:
        category = str(item["category"]).strip()

        if category != current_category:
            if current_group_start is not None:
                row_groups.append((current_group_start, len(data)))

            if current_category is not None:
                data.append(["", "", "", ""])

            # Category header row. Item name stays blank so imports ignore it.
            data.append([category, "", "", ""])
            current_category = category
            current_group_start = len(data)

        data.append([
            category,
            item["name"],
            item["base_unit"],
            "",
        ])

    if current_group_start is not None:
        row_groups.append((current_group_start, len(data)))

    sheet.clear()
    sheet.update("A1", data)
    clear_row_groups(sheet)
    apply_collapsible_row_groups(sheet, row_groups)
    print(f"{location} count sheet updated successfully.")

def import_count_from_sheet(location: str, count_date: str):
    sheet = get_sheet(f"{location} Count")
    rows = sheet.get_all_records()

    location_id = get_location_id(location)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, is_reconciled
            FROM stock_counts
            WHERE location_id = ? AND count_date = ?
            """,
            (location_id, count_date),
        ).fetchone()

    if row:
        count_id = int(row["id"])

        if int(row["is_reconciled"]) == 1:
            with get_conn() as conn:
                conn.execute("DELETE FROM stock_count_lines WHERE count_id = ?", (count_id,))
                conn.execute("DELETE FROM stock_counts WHERE id = ?", (count_id,))
            count_id = create_count(location, count_date)
        else:
            clear_count_lines(count_id)
    else:
        count_id = create_count(location, count_date)

    for row in rows:
        normalized = {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}

        item = normalized.get("item_name")
        qty = float(normalized.get("counted_qty") or 0)

        if not item:
            continue

        add_count_line(count_id, item, qty)

    return count_id


def export_pick_list_to_sheet(rows):
    ss = get_spreadsheet()

    try:
        sheet = ss.worksheet("Pick List")
    except:
        sheet = ss.add_worksheet(title="Pick List", rows="100", cols="10")

    sheet.clear()

    # headers
    sheet.append_row(["Item", "Pick Qty", "Unit"])

    for r in rows:
        sheet.append_row([
            r["name"],
            round(r["pick_qty"], 2),
            r["base_unit"],
        ])

from collections import defaultdict

def export_supplier_order_to_sheet(rows):
    ss = get_spreadsheet()

    try:
        sheet = ss.worksheet("Supplier Orders")
    except:
        sheet = ss.add_worksheet(title="Supplier Orders", rows="100", cols="10")

    sheet.clear()

    sheet.append_row(["Supplier", "Item", "Order Qty", "Unit"])

    grouped = defaultdict(list)

    for r in rows:
        supplier = r.get("supplier", "Unknown")
        grouped[supplier].append(r)

    for supplier, items in grouped.items():
        for r in items:
            sheet.append_row([
                supplier,
                r["name"],
                round(r["supplier_order_qty"], 2),
                r["base_unit"],
            ])



def clear_count_lines(count_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM stock_count_lines WHERE count_id = ?;",
            (count_id,),
        )

