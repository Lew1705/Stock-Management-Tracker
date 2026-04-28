from .services.counts import COUNT_LOCATIONS


def active_page_for_path(path: str) -> str:
    if path.startswith("/login"):
        return "login"
    if path.startswith("/admin/users"):
        return "admin_users"
    if path.startswith("/counts/keele"):
        return "keele_count"
    if path.startswith("/counts/little-shop"):
        return "little_shop_count"
    if path.startswith("/items"):
        return "items"
    if path.startswith("/counts"):
        return "keele_count"
    if path.startswith("/deliveries"):
        return "deliveries"
    if path.startswith("/invoices"):
        return "deliveries"
    if path.startswith("/finance"):
        return "finance"
    if path.startswith("/transfers"):
        return "transfers"
    if path.startswith("/supplier-orders"):
        return "supplier_orders"
    if path.startswith("/history"):
        return "history"
    if path.startswith("/shopping-lists"):
        return "shopping_lists"
    if path.startswith("/request-lists"):
        return "little_shop_requests"
    return "dashboard"


def group_rows_by_category(rows: list[dict]) -> dict[str, list[dict]]:
    grouped_rows: dict[str, list[dict]] = {}
    for row in rows:
        grouped_rows.setdefault(str(row["category"]), []).append(row)
    return grouped_rows


def build_items_page_context(rows) -> dict:
    grouped_items = group_rows_by_category(rows)
    return {
        "grouped_items": grouped_items,
        "item_count": len(rows),
        "category_count": len(grouped_items),
    }


def build_count_page_context(
    *,
    location: str,
    count_date: str,
    count_rows: list[dict],
    count_id: int | None,
    is_reconciled: bool,
    error_message: str = "",
    success_message: str = "",
) -> dict:
    total_items = len(count_rows)
    entered_items = sum(1 for row in count_rows if str(row["counted_qty"]).strip() != "")
    is_keele = location == "Keele"
    return {
        "location": location,
        "count_date": count_date,
        "count_id": count_id,
        "is_reconciled": is_reconciled,
        "grouped_rows": group_rows_by_category(count_rows),
        "locations": list(COUNT_LOCATIONS),
        "error_message": error_message,
        "success_message": success_message,
        "total_items": total_items,
        "entered_items": entered_items,
        "count_route": "/counts/keele" if is_keele else "/counts/little-shop",
        "page_title": "Keele Count" if is_keele else "Little Shop Count",
        "hero_eyebrow": "Count stock at Keele" if is_keele else "Count stock at Little Shop",
        "hero_heading": "Keele stock sheet" if is_keele else "Little Shop stock sheet",
        "hero_text": (
            "Use this sheet to count Keele stock and keep the supplier ordering plan up to date."
            if is_keele
            else "Use this sheet to count Little Shop stock so the team can see what needs taking round from Keele."
        ),
        "primary_link_href": "/shopping-lists?date=" + count_date if is_keele else "/request-lists?date=" + count_date,
        "primary_link_label": "View Keele shopping list" if is_keele else "View Little Shop request list",
        "secondary_link_href": "/request-lists?date=" + count_date if is_keele else "/counts/keele?date=" + count_date,
        "secondary_link_label": "View Little Shop request list" if is_keele else "Open Keele stock sheet",
    }


def build_request_list_page_context(
    location: str,
    count_date: str,
    rows: list[dict],
    source_location: str,
    total_request_value: float = 0.0,
    request_id: int | None = None,
    request_value: float | None = None,
    success_message: str = "",
    error_message: str = "",
) -> dict:
    return {
        "location": location,
        "count_date": count_date,
        "source_location": source_location,
        "grouped_rows": group_rows_by_category(rows),
        "total_items": len(rows),
        "total_request_qty": sum(float(row["request_qty"]) for row in rows),
        "total_fulfill_qty": sum(float(row["fulfill_qty"]) for row in rows),
        "total_request_value": total_request_value,
        "request_id": request_id,
        "request_value": request_value,
        "success_message": success_message,
        "error_message": error_message,
    }


def build_shopping_list_page_context(location: str, count_date: str, rows: list[dict]) -> dict:
    return {
        "location": location,
        "count_date": count_date,
        "grouped_rows": group_rows_by_category(rows),
        "total_items": len(rows),
        "total_order_qty": sum(float(row["order_qty"]) for row in rows),
    }
