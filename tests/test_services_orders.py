from stock.db import current_stock
from stock.services.items import save_item_record
from stock.services.orders import create_order_from_current_plan, get_order_detail, mark_order_received


def test_supplier_order_can_be_created_and_received(isolated_db):
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

    order_id = create_order_from_current_plan("2026-04-25", "Weekly restock")
    detail = get_order_detail(order_id)

    assert detail["header"]["status"] == "DRAFT"
    assert detail["ordered_qty"] == 6.0

    receipt = mark_order_received(order_id, "Received in full")
    detail_after = get_order_detail(order_id)

    assert receipt["received_qty"] == 6.0
    assert detail_after["header"]["status"] == "RECEIVED"
    assert current_stock("Keele", "Milk") == 6.0
