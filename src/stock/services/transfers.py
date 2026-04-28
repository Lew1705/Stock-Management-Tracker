from .dashboard import today_iso
from ..db import (
    cancel_transfer_request,
    confirm_request_transfer,
    confirm_transfer_request_by_id,
    get_transfer_request,
    get_transfer_request_activity,
    get_transfer_request_lines,
    recent_transfer_requests,
)


def list_recent_transfer_requests():
    rows = recent_transfer_requests(limit=20)
    return [
        {
            **dict(row),
            "progress_pct": 0 if float(row["requested_qty"] or 0) <= 0 else round((float(row["fulfilled_qty"] or 0) / float(row["requested_qty"])) * 100),
        }
        for row in rows
    ]


def get_transfer_request_detail(request_id: int) -> dict:
    header = get_transfer_request(request_id)
    lines = get_transfer_request_lines(request_id)
    activity = get_transfer_request_activity(request_id)
    requested_qty = sum(float(row["requested_qty_base"] or 0.0) for row in lines)
    fulfilled_qty = sum(float(row["fulfilled_qty_base"] or 0.0) for row in lines)
    return {
        "header": dict(header),
        "lines": [dict(row) for row in lines],
        "activity": [dict(row) for row in activity],
        "requested_qty": requested_qty,
        "fulfilled_qty": fulfilled_qty,
        "outstanding_qty": max(requested_qty - fulfilled_qty, 0.0),
    }


def confirm_transfer_for_date(count_date: str, note: str = "") -> dict:
    normalized_date = (count_date or today_iso()).strip() or today_iso()
    return confirm_request_transfer(normalized_date, note.strip())


def confirm_transfer_by_request(request_id: int, note: str = "") -> dict:
    return confirm_transfer_request_by_id(request_id, note.strip())


def cancel_transfer(request_id: int) -> None:
    cancel_transfer_request(request_id)
