import argparse
import shutil
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .cli import (
    cmd_dashboard,
    cmd_export_sheets,
    cmd_import_count_sheet,
    cmd_run_day,
)
from .db import DB_PATH, PROJECT_ROOT, init_db, seed_locations


def _today() -> str:
    timezone_name = os.environ.get("STOCK_TIMEZONE", "Europe/London")
    return datetime.now(ZoneInfo(timezone_name)).date().isoformat()


def _date_arg() -> str:
    return os.environ.get("STOCK_RUN_DATE", _today())


def _bootstrap() -> None:
    bundled_db = PROJECT_ROOT / "stock.db"
    if not DB_PATH.exists() and bundled_db.exists() and bundled_db.resolve() != DB_PATH.resolve():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_db, DB_PATH)
        print(f"Copied bundled database into {DB_PATH}")

    init_db()
    seed_locations()


def main() -> None:
    task = os.environ.get("STOCK_TASK", "dashboard").strip().lower()
    _bootstrap()

    if task == "dashboard":
        cmd_dashboard(argparse.Namespace())
        return

    if task == "export-sheets":
        cmd_export_sheets(argparse.Namespace())
        return

    if task == "run-day":
        cmd_run_day(argparse.Namespace(date=_date_arg()))
        return

    if task == "import-little-shop-count":
        cmd_import_count_sheet(argparse.Namespace(location="Little Shop", date=_date_arg()))
        return

    if task == "import-keele-count":
        cmd_import_count_sheet(argparse.Namespace(location="Keele", date=_date_arg()))
        return

    raise SystemExit(
        "Unknown STOCK_TASK. Expected one of: "
        "dashboard, export-sheets, run-day, import-little-shop-count, import-keele-count"
    )


if __name__ == "__main__":
    main()
