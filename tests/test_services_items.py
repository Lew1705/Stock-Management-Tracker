import pytest

from stock.services.items import get_item, list_items, save_item_record


def test_save_item_record_persists_suppliers_and_par_levels(isolated_db):
    item_id = save_item_record(
        item_id=None,
        name="Oatly Barista",
        category="Milk",
        base_unit="each",
        supplier="Booker; Sainsbury's",
        ref="BK-1; SA-9",
        cost_per_unit="1.75",
        par_keele="8",
        par_little_shop="3",
    )

    item = get_item(item_id)
    catalog = list_items()

    assert item["par_keele"] == "8.0"
    assert item["par_little_shop"] == "3.0"
    assert item["supplier"] == "Booker; Sainsbury's"
    assert item["ref"] == "BK-1; SA-9"
    assert catalog[0]["suppliers"] == "Booker (BK-1) | Sainsbury's (SA-9)"


def test_save_item_record_rejects_negative_par_level(isolated_db):
    with pytest.raises(ValueError, match="Keele par level cannot be negative."):
        save_item_record(
            item_id=None,
            name="Bagels",
            category="Bread",
            base_unit="each",
            supplier="Booker",
            ref="BK-7",
            par_keele="-1",
        )
