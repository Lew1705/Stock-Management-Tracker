from stock.db import current_stock
from stock.services.counts import save_count_data
from stock.services.items import save_item_record
from stock.services.orders import (
    create_order_from_current_plan,
    get_order_detail,
    mark_order_ordered,
    mark_order_received,
    update_order_draft_lines,
)
from stock.services.planning import get_shopping_list_data


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

    mark_order_ordered(order_id)
    receipt = mark_order_received(order_id, "Received in full")
    detail_after = get_order_detail(order_id)

    assert receipt["received_qty"] == 6.0
    assert detail_after["header"]["status"] == "RECEIVED"
    assert current_stock("Keele", "Milk") == 6.0


def test_supplier_order_uses_shopping_list_quantities_from_saved_counts(isolated_db):
    item_id = save_item_record(
        item_id=None,
        name="Coffee Beans",
        category="Coffee",
        base_unit="1kg bag",
        supplier="Booker",
        ref="CF-1",
        cost_per_unit="8.50",
        par_keele="10",
        par_little_shop="8",
    )
    save_count_data("Keele", "2026-04-25", {item_id: "10"})
    save_count_data("Little Shop", "2026-04-25", {item_id: "0"})

    shopping_list = get_shopping_list_data("2026-04-25")
    order_id = create_order_from_current_plan("2026-04-25", "Generated from shopping list")
    detail = get_order_detail(order_id)

    assert shopping_list["rows"][0]["order_qty"] == 8.0
    assert detail["ordered_qty"] == 8.0
    assert detail["lines"][0]["ordered_qty_base"] == 8.0


def test_supplier_order_draft_can_be_edited_before_ordering(isolated_db):
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
    save_item_record(
        item_id=None,
        name="Tea",
        category="Drinks",
        base_unit="each",
        supplier="Morrisons",
        ref="MR-10",
        cost_per_unit="2.50",
        par_keele="4",
        par_little_shop="0",
    )

    order_id = create_order_from_current_plan("2026-04-25", "Weekly restock")
    detail = get_order_detail(order_id)
    lines_by_name = {row["name"]: row for row in detail["lines"]}

    update_order_draft_lines(
        order_id,
        {
            f"quantity_{lines_by_name['Milk']['id']}": "3",
            f"quantity_{lines_by_name['Tea']['id']}": "0",
        },
    )
    mark_order_ordered(order_id)
    detail_after_ordered = get_order_detail(order_id)

    assert detail_after_ordered["header"]["status"] == "ORDERED"
    assert detail_after_ordered["ordered_qty"] == 3.0
    assert [row["name"] for row in detail_after_ordered["lines"]] == ["Milk"]

    mark_order_received(order_id, "Received edited order")

    assert current_stock("Keele", "Milk") == 3.0
    assert current_stock("Keele", "Tea") == 0.0
