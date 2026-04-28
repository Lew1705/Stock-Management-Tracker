from ..core.units import VALID_BASE_UNITS
from ..db import (
    delete_par_level_by_item_id,
    get_item_for_edit,
    get_item_par_levels,
    get_items_with_suppliers,
    save_item,
    set_par_level_by_item_id,
)


def list_items():
    return get_items_with_suppliers()


def get_item(item_id: int) -> dict:
    item = get_item_for_edit(item_id)
    par_levels = get_item_par_levels(item_id)
    item["par_keele"] = "" if par_levels["Keele"] is None else str(par_levels["Keele"])
    item["par_little_shop"] = "" if par_levels["Little Shop"] is None else str(par_levels["Little Shop"])
    return item


def save_item_record(
    item_id: int | None,
    name: str,
    category: str,
    base_unit: str,
    supplier: str,
    ref: str,
    cost_per_unit: str = "",
    par_keele: str = "",
    par_little_shop: str = "",
) -> int:
    saved_item_id = save_item(
        item_id,
        name,
        category,
        base_unit,
        supplier,
        ref,
        cost_per_unit,
    )
    save_item_par_levels(saved_item_id, par_keele=par_keele, par_little_shop=par_little_shop)
    return saved_item_id


def save_item_par_levels(item_id: int, *, par_keele: str, par_little_shop: str) -> None:
    for location, raw_value in (("Keele", par_keele), ("Little Shop", par_little_shop)):
        text = (raw_value or "").strip()
        if text == "":
            delete_par_level_by_item_id(location, item_id)
            continue
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{location} par level must be a number.") from exc
        if value < 0:
            raise ValueError(f"{location} par level cannot be negative.")
        set_par_level_by_item_id(location, item_id, value)


def get_base_units() -> tuple[str, ...]:
    return VALID_BASE_UNITS
