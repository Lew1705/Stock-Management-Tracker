# Deployment Guide

## Goal

Run the stock tracker somewhere that stays on even when your laptop is off.

## Current architecture

- App type: Flask web app plus Python CLI
- Data store: SQLite (`stock.db`)
- External integration: Google Sheets via service account credentials JSON
- Multi-user maturity: early-stage, because SQLite is still a local file database

## Best practical option right now

Host it on one dedicated always-on machine.

Good choices:

- a small office PC or mini PC that stays on
- a Windows VPS
- a cloud VM

This works with the current code because it already assumes:

- a filesystem
- a local SQLite file
- a local Google credentials file

## Environment variables

Use these on the host machine:

- `PYTHONPATH=src`
- `PORT=5000`
- `STOCK_TIMEZONE=Europe/London`
- `STOCK_DB_PATH=C:\stock-management\stock.db`
- `STOCK_SECRET_KEY=choose-a-long-random-secret`
- `GOOGLE_APPLICATION_CREDENTIALS=C:\stock-management\secrets\creds.json`
- `STOCK_SHEET_ID=your-google-sheet-id`

## Suggested folder layout on the host

```text
C:\stock-management\
  stock.db
  app\
  secrets\
    creds.json
```

## First-time setup

1. Copy the repo to the host machine.
2. Create a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Set the environment variables above.
5. Run `python -m stock.cli init` if the database is new.
6. Test a safe command like `python -m stock.cli dashboard`.
7. Start the web app with `python -m stock.web`.

## Web access

The app now serves a browser UI.

Current pages:

- `/`
- `/items`
- `/counts`
- `/request-lists`
- `/shopping-lists`

## Important limitations

The app is now usable in a browser, but SQLite is still the main production limitation.

If several staff use the app heavily at the same time, the next upgrade should be moving the database to Postgres.

## Recommendation

For now, deploy to an always-on machine or Railway first.

That gets the app off your laptop quickly with minimal code risk.

After that, if staff rely on it daily, prioritise Postgres and better audit/history screens.
