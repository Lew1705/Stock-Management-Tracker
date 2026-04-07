# Stock Management

This project is a Python stock-tracking tool for Keele and Little Shop. It stores stock data in SQLite and can import/export working sheets with Google Sheets.

## What it is today

The current app is not a hosted website yet. It is a command-line app that:

- stores data in a local `stock.db` SQLite database
- reads Google Sheets using a service account JSON file
- runs from Python commands such as `python -m stock.cli ...`

That means staff cannot use it independently unless the app is moved onto an always-on machine or rebuilt as a web app.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Set environment variables if needed:

```powershell
$env:PYTHONPATH="src"
$env:STOCK_DB_PATH="C:\path\to\stock.db"
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\creds.json"
$env:STOCK_SHEET_ID="your-google-sheet-id"
```

4. Run a command:

```powershell
python -m stock.cli dashboard
```

## Hosting recommendation

The simplest way to stop relying on your laptop is:

1. Put this project on an always-on cloud host.
2. Store `stock.db` on a persistent disk or volume.
3. Store the Google service account JSON in environment variables or a secrets file.
4. Run the CLI there, or schedule workflows there.

This is the lowest-risk option because the app already depends on SQLite and local files.

## Railway quick start

This repo now includes a Railway-friendly `Dockerfile` and a small runner module at `python -m stock.railway_runner`.

Suggested Railway variables:

```text
STOCK_TASK=dashboard
STOCK_TIMEZONE=Europe/London
STOCK_SHEET_ID=your-google-sheet-id
GOOGLE_SERVICE_ACCOUNT_JSON={...full service account json...}
```

If you mount a Railway volume, the app will automatically store the database at `RAILWAY_VOLUME_MOUNT_PATH/stock.db`.

## Next step options

- Fastest: deploy this as-is to an always-on machine and let staff keep using Google Sheets for counts.
- Better multi-user setup: move the database from SQLite to Postgres.
- Best user experience: build a small web UI so staff do not need command-line access.

More detail is in [docs/deployment.md](/C:/Users/lewis/OneDrive/Desktop/Stock%20Management/docs/deployment.md) and [docs/railway.md](/C:/Users/lewis/OneDrive/Desktop/Stock%20Management/docs/railway.md).
