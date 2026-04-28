from .dashboard import today_iso
from ..db import (
    cancel_supplier_order,
    create_supplier_order,
    get_supplier_order,
    get_supplier_order_lines,
    list_supplier_invoices,
    list_supplier_orders,
    mark_supplier_order_ordered,
    receive_supplier_order,
)


def list_orders(status: str | None = None):
    return [dict(row) for row in list_supplier_orders(status=status, limit=30)]


def create_order_from_current_plan(order_date: str, note: str = "") -> int:
    normalized_date = (order_date or today_iso()).strip() or today_iso()
    return create_supplier_order(normalized_date, note.strip())


def get_order_detail(order_id: int) -> dict:
    header = dict(get_supplier_order(order_id))
    lines = [dict(row) for row in get_supplier_order_lines(order_id)]
    invoices = [dict(row) for row in list_supplier_invoices(order_id=order_id, limit=20)]
    return {
        "header": header,
        "lines": lines,
        "invoices": invoices,
        "ordered_qty": sum(float(row["ordered_qty_base"] or 0.0) for row in lines),
        "received_qty": sum(float(row["received_qty_base"] or 0.0) for row in lines),
    }


def mark_order_ordered(order_id: int) -> None:
    mark_supplier_order_ordered(order_id)


def mark_order_received(order_id: int, note: str = "") -> dict:
    return receive_supplier_order(order_id, note.strip())


def mark_order_cancelled(order_id: int) -> None:
    cancel_supplier_order(order_id)
