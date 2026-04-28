from .dashboard import today_iso
from ..db import get_count_entry_rows, get_saved_count_summary, save_web_count

COUNT_LOCATIONS = ("Keele", "Little Shop")


def normalize_count_location(location: str) -> str:
    cleaned = (location or "").strip() or "Keele"
    return cleaned if cleaned in COUNT_LOCATIONS else "Keele"


def build_count_data(location: str, count_date: str | None = None) -> dict:
    normalized_location = normalize_count_location(location)
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    count_data = get_count_entry_rows(normalized_location, normalized_date)
    return {
        "location": normalized_location,
        "count_date": normalized_date,
        **count_data,
    }


def save_count_data(location: str, count_date: str, count_values: dict[int, str]) -> int:
    normalized_location = normalize_count_location(location)
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    return save_web_count(normalized_location, normalized_date, count_values)


def get_daily_sync_readiness(count_date: str | None = None) -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    locations: list[dict] = []

    for location in COUNT_LOCATIONS:
        summary = get_saved_count_summary(location, normalized_date)
        is_ready = summary["count_id"] is not None and summary["line_count"] > 0
        locations.append(
            {
                "location": location,
                "count_id": summary["count_id"],
                "line_count": summary["line_count"],
                "is_reconciled": summary["is_reconciled"],
                "is_ready": is_ready,
            }
        )

    missing_locations = [row["location"] for row in locations if not row["is_ready"]]
    return {
        "count_date": normalized_date,
        "locations": locations,
        "is_ready": not missing_locations,
        "missing_locations": missing_locations,
    }


def get_count_status_overview(count_date: str | None = None) -> dict:
    readiness = get_daily_sync_readiness(count_date)
    status_rows = []

    for row in readiness["locations"]:
        if row["count_id"] is None:
            status_name = "Not started"
            status_class = "warning"
            status_message = "No saved count exists for this date yet."
        elif row["line_count"] <= 0:
            status_name = "In progress"
            status_class = "warning"
            status_message = "A count record exists, but no lines have been saved yet."
        else:
            status_name = "Ready"
            status_class = "success"
            status_message = "This location has a saved count and can be used in daily sync."

        status_rows.append(
            {
                **row,
                "status_name": status_name,
                "status_class": status_class,
                "status_message": status_message,
            }
        )

    return {
        **readiness,
        "locations": status_rows,
    }
