# Railway Setup

## Recommended approach

Use Railway with:

- one persistent volume
- this repo deployed from GitHub
- Google Sheets as the staff-facing workflow

This is the cheapest and fastest way to get the stock tracker off your laptop without rebuilding the app first.

## What the Railway runner does

The deploy command is:

```text
python -m stock.railway_runner
```

It supports these tasks through the `STOCK_TASK` variable:

- `dashboard`
- `export-sheets`
- `run-day`
- `import-little-shop-count`
- `import-keele-count`

`run-day` and the import tasks use `STOCK_RUN_DATE` if set, otherwise they use today's date in `STOCK_TIMEZONE`.

## Railway variables

Set these in Railway:

```text
STOCK_TIMEZONE=Europe/London
STOCK_SHEET_ID=your-google-sheet-id
GOOGLE_SERVICE_ACCOUNT_JSON={paste the full Google service account JSON here}
```

For each Railway service, also set:

```text
STOCK_TASK=export-sheets
```

or:

```text
STOCK_TASK=run-day
```

## Volume

Create one Railway volume and mount it on the service.

The app automatically uses:

```text
$RAILWAY_VOLUME_MOUNT_PATH/stock.db
```

as the database path when `STOCK_DB_PATH` is not set.

## Suggested service layout

Use two Railway services from the same repo:

1. `stock-export-sheets`
2. `stock-run-day`

Suggested variables:

For `stock-export-sheets`:

```text
STOCK_TASK=export-sheets
```

For `stock-run-day`:

```text
STOCK_TASK=run-day
```

Mount the same volume on both services so they share the same `stock.db`.

## Cron suggestions

Because Railway cron runs in UTC, set schedules carefully for UK time.

Examples:

- morning export: `0 8 * * *`
- end-of-day processing: `0 18 * * *`

Check whether British Summer Time is active when choosing the final UTC schedule.

## First deployment

1. Push this repo to GitHub.
2. Create a new Railway project from the repo.
3. Add a volume and mount it.
4. Add the shared variables.
5. Deploy one service with `STOCK_TASK=export-sheets`.
6. Deploy a second service with `STOCK_TASK=run-day`.
7. Add cron schedules in Railway.

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

This still is not a browser app.

The practical workflow is:

- staff fill in Google Sheets
- Railway runs the stock logic
- the SQLite database lives on the Railway volume

If you later want staff to use a proper app directly, the next step is a web UI plus Postgres.
