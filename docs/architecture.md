# Architecture

## Overview

This is a Python stock-management app with two interfaces:

- a Flask web app for staff-facing workflows
- a CLI for imports, exports, setup, and legacy commands

SQLite is currently the database. The schema lives in `db/schema.sql`, and most business logic lives in `src/stock/db.py`.

## Main Modules

### `src/stock/web.py`

The Flask app.

Current pages:

- dashboard
- item list
- add/edit item
- stock count entry
- Little Shop request list
- Keele supplier shopping list

### `src/stock/db.py`

Database access and business logic.

It handles:

- database setup
- items
- suppliers
- par levels
- counts
- request lists
- shopping lists
- stock transactions

### `src/stock/cli.py`

Command-line interface for admin and legacy workflows.

Useful for:

- initialising the database
- importing item CSV files
- exporting Google Sheets
- running daily workflows

### `src/stock/sheets.py`

Google Sheets authentication and worksheet helpers.

## Main Tables

- `locations`
- `items`
- `suppliers`
- `item_suppliers`
- `par_levels`
- `stock_counts`
- `stock_count_lines`
- `stock_transactions`
- `transfer_requests`
- `transfer_request_lines`
- `run_history`

## Source Of Truth

The database should be treated as the source of truth.

Google Sheets can still be used for importing/exporting, but the long-term direction is for staff to use the web app directly.
