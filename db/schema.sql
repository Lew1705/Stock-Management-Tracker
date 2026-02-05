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
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each', 'g', 'ml'))
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
    week_ending TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
