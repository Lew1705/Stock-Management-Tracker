import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "stock.db"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn



def init_db():
    with get_conn() as conn:
        schema = SCHEMA_PATH.read_text()
        conn.executescript(schema)

def seed_locations() -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?);", ("Keele",))
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?);", ("Little Shop",))

def list_locations() -> None:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM locations ORDER BY id;").fetchall()

    for row in rows:
        print(dict(row))


def insert_item(name: str, category: str, base_unit: str) -> None:
    with get_conn() as conn:
        conn.execute("""
        
        INSERT OR IGNORE INTO items (name, category, base_unit)
        VALUES (?, ?, ?)
                     
        """,
        (name, category, base_unit),
    )

def list_items() -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, category, base_unit FROM items ORDER BY id;"
        ).fetchall()

    for row in rows:
        print(dict(row))


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

def add_transaction(location: str, item: str, qty_base: float, tx_type: str, note: str = "") -> None:
    location_id = get_location_id(location)
    item_id = get_item_id(item)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stock_transactions (location_id, item_id, qty_base, type, note)
            VALUES (?, ?, ?, ?, ?);
            """,
            (location_id, item_id, qty_base, tx_type, note),
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




def create_count(location: str, week_ending: str) -> int:
    """
    Creates a stock count 'header' for a location + week ending date.
    Returns the new count_id.
    """
    location_id = get_location_id(location)

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO stock_counts (location_id, week_ending)
            VALUES (?, ?);
            """,
            (location_id, week_ending),
        )
        return int(cur.lastrowid) #gives u the id of the last row inserted 
    
def add_count_line(count_id: int, item: str, counted_qty_base: float) -> None:
    """
    Adds a single item line to an existing stock count.
    """
    item_id = get_item_id(item)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stock_count_lines (count_id, item_id, counted_qty_base)
            VALUES (?, ?, ?);
            """,
            (count_id, item_id, counted_qty_base),
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
            SELECT id, location_id, week_ending, created_at
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
            SELECT id, created_at, week_ending
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
    Option 2:
    Current stock = latest count for location+item + transactions AFTER that count.
    If no count exists yet, fallback to ledger sum (all transactions).
    """
    counted, count_ts = latest_counted_qty(location, item)

    if count_ts is None:
        # No count yet: fallback to ledger total
        return stock_on_hand(location, item)

    return counted + net_transactions_since(location, item, count_ts)


def get_items():
    """Return all items as sqlite3.Row objects (for CLI dashboards, etc)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, category, base_unit FROM items ORDER BY name;"
        ).fetchall()


def get_or_create_count(location: str, week_ending: str) -> int:
    """Return an existing count_id for (location, week_ending) or create one."""
    location_id = get_location_id(location)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM stock_counts
            WHERE location_id = ? AND week_ending = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1;
            """,
            (location_id, week_ending),
        ).fetchone()

    if row is not None:
        return int(row["id"])

    return create_count(location, week_ending)


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
            SELECT sc.id, l.name AS location, sc.week_ending, sc.created_at
            FROM stock_counts sc
            JOIN locations l ON l.id = sc.location_id
            {where_sql}
            ORDER BY datetime(sc.created_at) DESC
            LIMIT ?;
            """,
            tuple(params),
        ).fetchall()
