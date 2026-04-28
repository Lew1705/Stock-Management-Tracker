# Architecture

## Overview

This is a Python stock-management app with two interfaces:

- a Flask web app for staff-facing workflows
- a small JSON API layer for structured app data
- a CLI for imports, exports, setup, and legacy commands

SQLite is currently the database. The schema lives in `db/schema.sql`.

The architecture is now split into layers so future features are easier to understand and place:

- `core`: pure reusable rules and parsing
- `services`: app workflows and use-cases
- `api` / `web`: HTTP routes
- `templates`: HTML presentation
- `db.py`: legacy data-access and compatibility functions while the refactor continues

## Main Modules

### `src/stock/core/units.py`

Pure domain helpers.

It currently contains:

- valid base-unit definitions
- base-unit normalisation
- supplier/reference parsing

This is the safest place for logic we want to reuse across CLI, web, and API without pulling in Flask.

### `src/stock/services/`

Application services that answer questions like:

- what should the dashboard show?
- what data belongs on a count page?
- how do we save an item or count?
- what should a request list or shopping list contain?
- how does the daily run workflow execute across both locations?

These modules give us a cleaner middle layer between routes and storage.

### `src/stock/api.py`

JSON API endpoints.

Current routes include:

- `/api/dashboard`
- `/api/items`
- `/api/counts`
- `/api/request-lists`
- `/api/shopping-lists`

This layer is useful for any future JavaScript-enhanced UI, mobile view, or external integration.

### `src/stock/web.py`

The HTML web layer.

Current pages:

- dashboard
- item list
- add/edit item
- stock count entry
- Little Shop request list
- Keele supplier shopping list

`web.py` should mostly do three jobs:

- read HTTP input
- call services
- render templates or redirect

### `src/stock/db.py`

Database access plus legacy business logic.

It currently still handles:

- database setup
- items
- suppliers
- par levels
- counts
- request lists
- shopping lists
- stock transactions

This file is still too broad, but the active web app is now routed through `services` first. That gives us a cleaner direction for future extraction without breaking old CLI commands.

### `src/stock/services/daily_run.py`

Shared workflow orchestration for the daily run.

This is a good example of why the service layer exists: both the CLI and web app can call the same business workflow without the web layer importing CLI code.

### `src/stock/services/auth.py`

Authentication and authorization helpers.

It handles:

- password hashing and login checks
- loading the signed-in user from the session
- role checks for staff, manager, and admin access
- reusable decorators for protected routes

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
- `users`

### `templates/`

Frontend templates only.

Templates should stay focused on presentation and should not contain stock-calculation rules.

## How To Place New Code

- If it is a pure rule or parser, put it in `core`.
- If it is a business workflow, put it in `services`.
- If it is an HTTP endpoint, put it in `api.py` or `web.py`.
- If it is HTML rendering, put it in `templates`.
- If it is legacy DB plumbing or a migration helper, keep it in `db.py`.

## Source Of Truth

The database should be treated as the source of truth.

Google Sheets can still be used for importing/exporting, but the long-term direction is for staff to use the web app directly.
