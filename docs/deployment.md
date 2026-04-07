# Deployment Guide

## Goal

Run the stock tracker somewhere that stays on even when your laptop is off.

## Current architecture

- App type: Python CLI
- Data store: SQLite (`stock.db`)
- External integration: Google Sheets via service account credentials JSON
- Multi-user maturity: limited, because SQLite is a local file database

## Best practical option right now

Host it on one dedicated always-on machine.

Good choices:

- a small office PC or mini PC that stays on
- a Windows VPS
- a cloud VM

This works well with the current code because it already assumes:

- a filesystem
- a local SQLite file
- a local Google credentials file

## Environment variables

Use these on the host machine:

- `PYTHONPATH=src`
- `STOCK_DB_PATH=C:\stock-management\stock.db`
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

## Important limitations

This version is not a web app, so staff cannot just open a browser and use it directly.

Right now, your realistic operating models are:

- you or staff remote into the host machine and run commands there
- staff keep using Google Sheets, while the host machine runs imports/exports
- scheduled tasks run on the host machine for repeat workflows

## If you want browser access

The next upgrade should be:

1. add a small web UI
2. move from SQLite to Postgres
3. deploy the app to a proper web host

That would let staff use it without terminal access and would be much safer for concurrent use.

## Recommendation

For now, deploy to an always-on machine first.

That gets you off your laptop quickly with minimal code risk.

After that, if staff need direct day-to-day access, the next project should be converting this into a small web app.
