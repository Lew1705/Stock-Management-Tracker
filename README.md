# Stock Management

A Python and Flask stock tracker for managing stock between 2 coffee shop locations for the **Keele** and **Little Shop**.

The project stores stock data in SQLite, supports item/par-level imports from CSV, can still integrate with Google Sheets, and now includes a browser-based workflow for stock counts, request lists, and supplier shopping lists.

## Screenshot

![Keele shopping list screen](docs/images/keele-shopping-list.png)

## Features

- Web dashboard
- Login and role-based access
- Item list grouped by category
- Add/edit items
- Multiple suppliers per item
- Supplier reference numbers
- Stock counts for Keele and Little Shop
- Little Shop request list from Keele
- Keele supplier shopping list
- CSV import for items and par levels
- Google Sheets import/export support
- Railway-friendly Docker deployment

## Workflow

1. Staff count stock for Little Shop and Keele.
2. The counts are saved in the database.
3. The app generates the **Little Shop request list**.
4. Staff take stock from Keele to Little Shop.
5. The app generates the **Keele supplier shopping list**.
6. Someone orders stock from suppliers.

## Tech Stack

- Python
- Flask
- SQLite
- Jinja templates
- Google Sheets API via `gspread`
- Waitress
- Docker

## Project Structure

```text
.
├── db/
│   └── schema.sql
├── docs/
│   ├── architecture.md
│   ├── development.md
│   ├── deployment.md
│   ├── railway.md
│   ├── roadmap.md
│   └── workflows.md
├── src/
│   └── stock/
│       ├── cli.py
│       ├── db.py
│       ├── sheets.py
│       └── web.py
├── templates/
│   ├── base.html
│   ├── count_form.html
│   ├── dashboard.html
│   ├── item_form.html
│   ├── items.html
│   ├── request_list.html
│   ├── run_day_result.html
│   └── shopping_list.html
├── Dockerfile
├── requirements.txt
└── README.md
```

## Local Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

For local development and tests:

```powershell
pip install -r requirements-dev.txt
```

Set local environment variables:

```powershell
$env:PYTHONPATH="src"
$env:PORT="5000"
```

Initialise the database:

```powershell
python -m stock.cli init
```

Create the first user:

```powershell
python -m stock.cli create-user --username admin --role admin
```

Run the web app:

```powershell
python -m stock.web
```

Run tests:

```powershell
pytest
```

Open:

[http://localhost:5000](http://localhost:5000)

## Main Web Pages

- `/` dashboard
- `/items` item list
- `/items/new` add item
- `/counts` enter stock counts
- `/request-lists` Little Shop request list from Keele
- `/shopping-lists` Keele supplier shopping list

## Import Items And Par Levels

The CSV import expects these columns:

```csv
item_name,category,base_unit,par_little_shop,par_keele,supplier,ref
```

Example:

```csv
Oatly,Milk,pack of 6,3,6,Booker,BK-001
New York Bakery Bagels,Bread,pack of 5,4,4,Sainsbury's; Morrisons,SA-1; MO-2
```

Run:

```powershell
python -m stock.cli import-items "C:\path\to\items_par_levels_template.csv"
```

Supported unit examples:

- `each`
- `g`
- `ml`
- `pack`
- `pack of 6`
- `tray of 30`
- `roll`
- `bundle`

## Useful CLI Commands

```powershell
python -m stock.cli init
python -m stock.cli create-user --username admin --role admin
python -m stock.cli import-items path\to\items.csv
python -m stock.cli export-sheets
python -m stock.cli run-day --date 2026-04-18
```

## Environment Variables

Copy `.env.example` as a reference.

```text
PYTHONPATH=src
PORT=5000
STOCK_TIMEZONE=Europe/London
STOCK_DB_PATH=stock.db
STOCK_SECRET_KEY=choose-a-long-random-secret
STOCK_SHEET_ID=your-google-sheet-id
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
```

## Roles

- `staff`: dashboard, counts, request lists, shopping lists, and daily workflow
- `manager`: everything staff can do, plus deliveries and item management
- `admin`: everything managers can do, plus reserved for future user-management tasks

For Railway, you can use:

```text
GOOGLE_SERVICE_ACCOUNT_JSON={...full service account json...}
```

## Important Notes

- Do not commit real Google credentials.
- Do not commit a live production database unless you intentionally want to bootstrap a deployment.
- SQLite is fine for local development and early testing.
- Postgres is recommended once multiple staff rely on the app at the same time.

## Documentation

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Workflows](docs/workflows.md)
- [Deployment](docs/deployment.md)
- [Railway](docs/railway.md)
- [Roadmap](docs/roadmap.md)
