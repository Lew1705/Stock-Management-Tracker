# Development Guide

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="src"
$env:PORT="5000"
```

Initialise the database:

```powershell
python -m stock.cli init
```

Run the app:

```powershell
python -m stock.web
```

Open:

```text
http://localhost:5000
```

## Useful Commands

Import item master data:

```powershell
python -m stock.cli import-items "src\items_par_levels_template.csv"
```

Run syntax checks:

```powershell
python -m py_compile src\stock\db.py src\stock\web.py src\stock\cli.py src\stock\sheets.py
```

If `py_compile` hits Windows/OneDrive `__pycache__` permissions, use a no-write check:

```powershell
python -B -c "import pathlib; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in pathlib.Path('src/stock').glob('*.py')]"
```

## Adding A New Page

1. Add a route in `src/stock/web.py`.
2. Add database helper functions in `src/stock/db.py` if needed.
3. Add a template in `templates/`.
4. Add navigation in `templates/base.html` if the page is top-level.
5. Run a syntax check.

## Coding Style

- Keep business rules in `db.py`.
- Keep route handling in `web.py`.
- Keep HTML in templates.
- Avoid putting secrets in code.
- Prefer clear names over clever abstractions.
