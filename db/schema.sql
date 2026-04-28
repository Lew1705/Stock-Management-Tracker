/*need to make two tables, one with locations and one with items 
items = id, name, category (text not null), base_unit (only allowed values g, ml, each)  */

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS suppliers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    base_unit TEXT NOT NULL,
    cost_per_unit REAL NOT NULL DEFAULT 0,
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
    cost_per_unit_at_time REAL NOT NULL DEFAULT 0,
    transfer_request_id INTEGER,
    type TEXT NOT NULL CHECK (type IN ('RECEIVE','TRANSFER_IN','TRANSFER_OUT','WASTE','ADJUSTMENT')),
    note TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (transfer_request_id) REFERENCES transfer_requests(id)
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

CREATE INDEX IF NOT EXISTS ix_item_suppliers_item_sort
ON item_suppliers(item_id, sort_order, supplier_id);

CREATE TABLE IF NOT EXISTS run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    run_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    output TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_run_history_started_at
ON run_history(started_at DESC);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS supplier_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    ordered_at TEXT,
    received_at TEXT
);

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

CREATE INDEX IF NOT EXISTS ix_supplier_orders_status_date
ON supplier_orders(status, order_date);

CREATE INDEX IF NOT EXISTS ix_supplier_order_lines_order
ON supplier_order_lines(order_id);

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

CREATE INDEX IF NOT EXISTS ix_supplier_invoices_order
ON supplier_invoices(order_id, uploaded_at DESC);

