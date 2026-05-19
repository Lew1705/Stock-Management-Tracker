from stock.services.items import save_item_record
from stock.services.planning import (
    add_custom_shopping_list_item,
    edit_custom_shopping_list_item,
    get_shopping_list_data,
    remove_custom_shopping_list_item,
)


def test_custom_shopping_list_items_are_persisted_and_editable(isolated_db):
    save_item_record(
        item_id=None,
        name="Milk",
        category="Dairy",
        base_unit="each",
        supplier="Booker",
        ref="BK-55",
        cost_per_unit="1.20",
        par_keele="6",
        par_little_shop="0",
    )

    custom_item_id = add_custom_shopping_list_item("2026-05-15", "Compostable cups", "2 sleeves", None)
    data = get_shopping_list_data("2026-05-15")

    assert data["custom_items"][0]["id"] == custom_item_id
    assert data["custom_items"][0]["item_name"] == "Compostable cups"
    assert data["custom_items"][0]["quantity"] == "2 sleeves"

    edit_custom_shopping_list_item(custom_item_id, "Compostable lids", "3 sleeves")
    edited = get_shopping_list_data("2026-05-15")

    assert edited["custom_items"][0]["item_name"] == "Compostable lids"
    assert edited["custom_items"][0]["quantity"] == "3 sleeves"

    remove_custom_shopping_list_item(custom_item_id)
    assert get_shopping_list_data("2026-05-15")["custom_items"] == []


def test_custom_shopping_list_items_validate_required_fields(isolated_db):
    try:
        add_custom_shopping_list_item("2026-05-15", "", "2", None)
    except ValueError as exc:
        assert "Item name is required" in str(exc)
    else:
        raise AssertionError("Expected blank item name to fail validation")

    try:
        add_custom_shopping_list_item("2026-05-15", "Napkins", "", None)
    except ValueError as exc:
        assert "Quantity is required" in str(exc)
    else:
        raise AssertionError("Expected blank quantity to fail validation")
