from .dashboard import today_iso
from .orders import list_orders
from ..db import confirm_request_transfer, receive_into_keele


def build_delivery_form_data() -> dict:
    ordered_orders = list_orders(status="ORDERED")
    draft_orders = list_orders(status="DRAFT")
    return {
        "location": "Keele",
        "delivery_date": today_iso(),
        "ordered_orders": ordered_orders,
        "draft_orders": draft_orders,
        "ordered_count": len(ordered_orders),
        "draft_count": len(draft_orders),
    }


def confirm_little_shop_transfer(request_date: str, note: str = "") -> dict:
    normalized_date = (request_date or today_iso()).strip() or today_iso()
    return confirm_request_transfer(normalized_date, note.strip())


def record_keele_delivery(item_name: str, quantity: str, note: str = "") -> None:
    try:
        normalized_quantity = float(str(quantity).strip())
    except ValueError as exc:
        raise ValueError("Delivery quantity must be a number.") from exc

    if normalized_quantity <= 0:
        raise ValueError("Delivery quantity must be greater than zero.")

    receive_into_keele(item_name.strip(), normalized_quantity, note.strip())
