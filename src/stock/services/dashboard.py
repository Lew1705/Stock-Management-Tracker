import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..db import get_items_with_suppliers, recent_run_history


def today_iso() -> str:
    timezone_name = os.environ.get("STOCK_TIMEZONE", "Europe/London")
    try:
        return datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    except ZoneInfoNotFoundError:
        return datetime.now().date().isoformat()


def get_dashboard_summary() -> dict:
    history = recent_run_history(limit=8)
    items = get_items_with_suppliers()
    categories = sorted({str(row["category"]) for row in items if row["category"]})
    return {
        "today": today_iso(),
        "timezone_name": os.environ.get("STOCK_TIMEZONE", "Europe/London"),
        "history": history,
        "item_count": len(items),
        "category_count": len(categories),
        "run_count": len(history),
    }
