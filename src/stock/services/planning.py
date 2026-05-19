from .dashboard import today_iso
from ..db import (
    create_shopping_list_custom_item,
    delete_shopping_list_custom_item,
    generate_request_list,
    generate_supplier_shopping_list,
    get_or_create_shopping_list,
    get_shopping_list_custom_item,
    list_shopping_list_custom_items,
    update_shopping_list_custom_item,
)


def _normalize_custom_text(value: str, field_name: str) -> str:
    cleaned = " ".join((value or "").strip().split())
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def _custom_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "shopping_list_id": int(row["shopping_list_id"]),
        "item_name": str(row["item_name"]),
        "quantity": str(row["quantity"]),
        "created_by": row["created_by"],
        "created_by_username": str(row["created_by_username"] or ""),
        "created_at": str(row["created_at"]),
    }


def get_request_list_data(count_date: str | None = None, visible_categories=None) -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    location = "Little Shop"
    source_location = "Keele"
    rows = generate_request_list(location, normalized_date, source_location, visible_categories=visible_categories)
    return {
        "location": location,
        "count_date": normalized_date,
        "source_location": source_location,
        "rows": rows,
        "total_request_value": sum(float(row["estimated_value"]) for row in rows),
    }


def get_shopping_list_data(count_date: str | None = None, visible_categories=None) -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    location = "Keele"
    shopping_list_id = get_or_create_shopping_list(location, normalized_date)
    rows = generate_supplier_shopping_list(
        normalized_date,
        source_location_name="Keele",
        request_location_name="Little Shop",
        visible_categories=visible_categories,
    )
    return {
        "location": location,
        "count_date": normalized_date,
        "shopping_list_id": shopping_list_id,
        "rows": rows,
        "custom_items": [_custom_row(row) for row in list_shopping_list_custom_items(shopping_list_id)],
    }


def add_custom_shopping_list_item(count_date: str, item_name: str, quantity: str, created_by: int | None) -> int:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    shopping_list_id = get_or_create_shopping_list("Keele", normalized_date)
    return create_shopping_list_custom_item(
        shopping_list_id,
        _normalize_custom_text(item_name, "Item name"),
        _normalize_custom_text(quantity, "Quantity"),
        created_by,
    )


def edit_custom_shopping_list_item(custom_item_id: int, item_name: str, quantity: str) -> None:
    get_shopping_list_custom_item(custom_item_id)
    update_shopping_list_custom_item(
        custom_item_id,
        _normalize_custom_text(item_name, "Item name"),
        _normalize_custom_text(quantity, "Quantity"),
    )


def remove_custom_shopping_list_item(custom_item_id: int) -> None:
    get_shopping_list_custom_item(custom_item_id)
    delete_shopping_list_custom_item(custom_item_id)
