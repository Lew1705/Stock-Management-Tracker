from .dashboard import today_iso
from ..db import generate_request_list, generate_supplier_shopping_list


def get_request_list_data(count_date: str | None = None) -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    location = "Little Shop"
    source_location = "Keele"
    rows = generate_request_list(location, normalized_date, source_location)
    return {
        "location": location,
        "count_date": normalized_date,
        "source_location": source_location,
        "rows": rows,
        "total_request_value": sum(float(row["estimated_value"]) for row in rows),
    }


def get_shopping_list_data(count_date: str | None = None) -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    location = "Keele"
    rows = generate_supplier_shopping_list(
        normalized_date,
        source_location_name="Keele",
        request_location_name="Little Shop",
    )
    return {
        "location": location,
        "count_date": normalized_date,
        "rows": rows,
    }
