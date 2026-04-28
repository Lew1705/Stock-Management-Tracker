import pytest

from stock.db import current_stock
from stock.services.items import save_item_record
from stock.services.operations import record_keele_delivery


def test_record_keele_delivery_updates_stock(isolated_db):
    save_item_record(
        item_id=None,
        name="Croissant",
        category="Bakery",
        base_unit="each",
        supplier="Booker",
        ref="BK-2",
    )

    record_keele_delivery("Croissant", "4.5", "Morning delivery")

    assert current_stock("Keele", "Croissant") == 4.5


def test_record_keele_delivery_rejects_invalid_quantity(isolated_db):
    with pytest.raises(ValueError, match="Delivery quantity must be greater than zero."):
        record_keele_delivery("Croissant", "0")
