# Railway Setup

## Recommended approach

Use Railway with:

- one persistent volume
- this repo deployed from GitHub
- a tiny protected web page for manual runs

This is the cheapest and fastest way to get the stock tracker off your laptop without rebuilding the app first.

## What the web app does

The deploy command is:

```text
python -m stock.web
```

It serves a simple page where staff can:

- choose the run date
- enter a shared access code
- manually trigger the daily workflow

## Railway variables

Set these in Railway:

```text
STOCK_TIMEZONE=Europe/London
STOCK_WEB_TOKEN=choose-a-shared-secret
STOCK_SHEET_ID=your-google-sheet-id
GOOGLE_SERVICE_ACCOUNT_JSON={paste the full Google service account JSON here}
```

## Volume

Create one Railway volume and mount it on the service.

The app automatically uses:

```text
$RAILWAY_VOLUME_MOUNT_PATH/stock.db
```

as the database path when `STOCK_DB_PATH` is not set.

## Suggested service layout

Use one Railway service from this repo with one mounted volume.

## First deployment

1. Push this repo to GitHub.
2. Create a new Railway project from the repo.
3. Add a volume and mount it.
4. Add the shared variables.
5. Redeploy.
6. Open the service URL in a browser.
7. Run the workflow manually from the page.

## Moving your existing database

If you already have a working local `stock.db`, the repo can carry it for a one-time bootstrap.

On first boot, the Railway runner will copy `/app/stock.db` into the mounted volume if the volume database does not exist yet.

That means the quickest migration path is:

1. commit your current `stock.db`
2. push to GitHub
3. redeploy Railway once

After the first successful copy, Railway will keep using the volume copy.

If you do not want to keep `stock.db` in the repo long term, you can remove it again after the Railway volume is populated.

## Important limitation

This is a very small internal tool page, not a full staff portal.

The practical workflow is:

- staff fill in Google Sheets
- staff open the Railway-hosted page
- staff click the button to run the stock logic
- the SQLite database lives on the Railway volume

If you later want a fuller multi-user app, the next step is a richer web UI plus Postgres.
