/*need to make two tables, one with locations and one with items 
items = id, name, category (text not null), base_unit (only allowed values g, ml, each)  */

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    base_unit TEXT NOT NULL,
    supplier_id INTEGER,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

/*just need to add category and base units that only accept certain things to the items table now */    


CREATE TABLE IF NOT EXISTS stock_transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    item_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    qty_base REAL NOT NULL, 
    type TEXT NOT NULL CHECK (type IN ('RECEIVE','TRANSFER_IN','TRANSFER_OUT','WASTE','ADJUSTMENT')),
    note TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

CREATE TABLE IF NOT EXISTS stock_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    count_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_reconciled INTEGER NOT NULL DEFAULT 0,
    reconciled_at TEXT,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

CREATE TABLE IF NOT EXISTS stock_count_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    count_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    counted_qty_base REAL NOT NULL,
    FOREIGN KEY (count_id) REFERENCES stock_counts(id),
    FOREIGN KEY (item_id) REFERENCES items(id)
);


CREATE TABLE IF NOT EXISTS par_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL, 
    item_id INTEGER NOT NULL,
    par_qty_base REAL NOT NULL, 
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(location_id, item_id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (item_id) REFERENCES items(id) 
);

-- One count per location per date (prevents duplicates)
CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_counts_location_date
ON stock_counts(location_id, count_date);

-- One count line per item per count (prevents duplicates)
CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_count_lines_count_item
ON stock_count_lines(count_id, item_id);

-- Speed up common queries
CREATE INDEX IF NOT EXISTS ix_stock_transactions_loc_item_ts
ON stock_transactions(location_id, item_id, ts);

CREATE INDEX IF NOT EXISTS ix_stock_count_lines_count
ON stock_count_lines(count_id);


CREATE TABLE IF NOT EXISTS transfer_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_location_id INTEGER NOT NULL,
    to_location_id INTEGER NOT NULL,
    request_date TEXT NOT NULL,              -- YYYY-MM-DD
    status TEXT NOT NULL DEFAULT 'OPEN',     -- OPEN, PARTIAL, FULFILLED, CANCELLED
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    fulfilled_at TEXT,
    FOREIGN KEY(from_location_id) REFERENCES locations(id),
    FOREIGN KEY(to_location_id) REFERENCES locations(id)
);

CREATE TABLE IF NOT EXISTS transfer_request_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    requested_qty_base REAL NOT NULL,
    fulfilled_qty_base REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(request_id) REFERENCES transfer_requests(id),
    FOREIGN KEY(item_id) REFERENCES items(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_transfer_request_lines_req_item
ON transfer_request_lines(request_id, item_id);

CREATE INDEX IF NOT EXISTS ix_transfer_requests_status_date
ON transfer_requests(status, request_date);


CREATE TABLE IF NOT EXISTS suppliers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

