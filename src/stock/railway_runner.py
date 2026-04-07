import argparse
import sqlite3
import shutil
import os
from datetime import datetime
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


def _db_has_items(db_path) -> bool:
    if not db_path.exists():
        return False

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'items';"
            ).fetchone()
            if not row or int(row[0]) == 0:
                return False

            row = conn.execute("SELECT COUNT(*) FROM items;").fetchone()
            return bool(row and int(row[0]) > 0)
    except sqlite3.Error:
        return False


def _bootstrap() -> None:
    bundled_db = PROJECT_ROOT / "stock.db"
    should_copy = (
        bundled_db.exists()
        and bundled_db.resolve() != DB_PATH.resolve()
        and _db_has_items(bundled_db)
        and (not DB_PATH.exists() or not _db_has_items(DB_PATH))
    )

    if should_copy:
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
