from collections import defaultdict
from datetime import date, timedelta

from .dashboard import today_iso
from ..db import get_conn


def _normalize_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _transaction_value_sum(start_date: str, end_date: str, *, location: str, tx_types: tuple[str, ...]) -> float:
    normalized_start, normalized_end = _normalize_date_range(start_date, end_date)
    placeholders = ", ".join("?" for _ in tx_types)
    params: list[object] = [location, normalized_start, normalized_end, *tx_types]

    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(ABS(st.qty_base) * st.cost_per_unit_at_time), 0) AS total_value
            FROM stock_transactions st
            JOIN locations l ON l.id = st.location_id
            WHERE l.name = ?
              AND date(st.ts) BETWEEN ? AND ?
              AND st.type IN ({placeholders});
            """,
            tuple(params),
        ).fetchone()

    return float(row["total_value"] or 0.0)


def get_little_shop_spend(start_date: str, end_date: str) -> float:
    return _transaction_value_sum(
        start_date,
        end_date,
        location="Little Shop",
        tx_types=("TRANSFER_IN",),
    )


def get_kit_transfer_value(start_date: str, end_date: str) -> float:
    return _transaction_value_sum(
        start_date,
        end_date,
        location="Keele",
        tx_types=("TRANSFER_OUT",),
    )


def get_kit_supplier_spend(start_date: str, end_date: str) -> float:
    return _transaction_value_sum(
        start_date,
        end_date,
        location="Keele",
        tx_types=("RECEIVE",),
    )


def get_net_kit_spend(start_date: str, end_date: str) -> float:
    return get_kit_supplier_spend(start_date, end_date) - get_kit_transfer_value(start_date, end_date)


def get_request_list_value(request_id: int) -> float:
    with get_conn() as conn:
        header = conn.execute(
            "SELECT id FROM transfer_requests WHERE id = ?;",
            (request_id,),
        ).fetchone()
        if header is None:
            raise ValueError(f"transfer request {request_id} not found")

        rows = conn.execute(
            """
            SELECT
                trl.item_id,
                trl.requested_qty_base,
                trl.fulfilled_qty_base,
                i.cost_per_unit,
                COALESCE(tx.fulfilled_value, 0) AS fulfilled_value
            FROM transfer_request_lines trl
            JOIN items i ON i.id = trl.item_id
            LEFT JOIN (
                SELECT
                    transfer_request_id,
                    item_id,
                    SUM(ABS(qty_base) * cost_per_unit_at_time) AS fulfilled_value
                FROM stock_transactions
                WHERE transfer_request_id = ?
                  AND type = 'TRANSFER_IN'
                GROUP BY transfer_request_id, item_id
            ) tx
              ON tx.transfer_request_id = trl.request_id
             AND tx.item_id = trl.item_id
            WHERE trl.request_id = ?;
            """,
            (request_id, request_id),
        ).fetchall()

    total_value = 0.0
    for row in rows:
        requested_qty = float(row["requested_qty_base"] or 0.0)
        fulfilled_qty = float(row["fulfilled_qty_base"] or 0.0)
        current_cost = float(row["cost_per_unit"] or 0.0)
        fulfilled_value = float(row["fulfilled_value"] or 0.0)
        outstanding_qty = max(requested_qty - fulfilled_qty, 0.0)
        total_value += fulfilled_value + (outstanding_qty * current_cost)

    return total_value


def get_breakdown_per_item(start_date: str, end_date: str, location: str) -> list[dict]:
    normalized_start, normalized_end = _normalize_date_range(start_date, end_date)

    location_map = {
        "Little Shop": ("Little Shop", ("TRANSFER_IN",)),
        "Keele": ("Keele", ("RECEIVE", "TRANSFER_OUT")),
        "Keele Suppliers": ("Keele", ("RECEIVE",)),
        "Keele Transfers": ("Keele", ("TRANSFER_OUT",)),
    }
    resolved = location_map.get(location)
    if resolved is None:
        raise ValueError(f"Unsupported audit location: {location}")

    location_name, tx_types = resolved
    placeholders = ", ".join("?" for _ in tx_types)
    params: list[object] = [location_name, normalized_start, normalized_end, *tx_types]

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                i.id AS item_id,
                i.name,
                i.category,
                i.base_unit,
                SUM(ABS(st.qty_base)) AS total_qty,
                SUM(ABS(st.qty_base) * st.cost_per_unit_at_time) AS total_value
            FROM stock_transactions st
            JOIN items i ON i.id = st.item_id
            JOIN locations l ON l.id = st.location_id
            WHERE l.name = ?
              AND date(st.ts) BETWEEN ? AND ?
              AND st.type IN ({placeholders})
            GROUP BY i.id, i.name, i.category, i.base_unit
            ORDER BY total_value DESC, LOWER(i.name);
            """,
            tuple(params),
        ).fetchall()

    return [
        {
            "item_id": int(row["item_id"]),
            "name": str(row["name"]),
            "category": str(row["category"]),
            "base_unit": str(row["base_unit"]),
            "total_qty": float(row["total_qty"] or 0.0),
            "total_value": float(row["total_value"] or 0.0),
        }
        for row in rows
    ]


def get_time_series_data(start_date: str, end_date: str, interval: str) -> list[dict]:
    normalized_start, normalized_end = _normalize_date_range(start_date, end_date)

    if interval not in {"day", "week", "month"}:
        raise ValueError("interval must be one of: day, week, month")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT date(st.ts) AS tx_date, ABS(st.qty_base) * st.cost_per_unit_at_time AS row_value
            FROM stock_transactions st
            JOIN locations l ON l.id = st.location_id
            WHERE l.name = 'Little Shop'
              AND st.type = 'TRANSFER_IN'
              AND date(st.ts) BETWEEN ? AND ?
            ORDER BY date(st.ts);
            """,
            (normalized_start, normalized_end),
        ).fetchall()

    buckets: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        tx_date = date.fromisoformat(str(row["tx_date"]))
        if interval == "day":
            key = tx_date.isoformat()
        elif interval == "week":
            key = (tx_date - timedelta(days=tx_date.weekday())).isoformat()
        else:
            key = tx_date.replace(day=1).isoformat()
        buckets[key] += float(row["row_value"] or 0.0)

    return [
        {"date": bucket_date, "value": round(total_value, 2)}
        for bucket_date, total_value in sorted(buckets.items())
    ]


def _build_chart_geometry(time_series_data: list[dict]) -> dict:
    width = 640
    height = 260
    padding = 32
    inner_width = width - (padding * 2)
    inner_height = height - (padding * 2)

    if not time_series_data:
        return {
            "chart_points": [],
            "chart_path": "",
            "chart_guides": [],
            "chart_width": width,
            "chart_height": height,
            "chart_max_value": 0.0,
        }

    raw_max_value = max(float(point["value"] or 0.0) for point in time_series_data)
    scale_max_value = raw_max_value if raw_max_value > 0 else 1.0
    chart_points = []

    for index, point in enumerate(time_series_data):
        if len(time_series_data) == 1:
            x = padding + (inner_width / 2)
        else:
            x = padding + ((inner_width * index) / (len(time_series_data) - 1))
        value = float(point["value"] or 0.0)
        y = padding + inner_height - ((value / scale_max_value) * inner_height)
        chart_points.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "date": str(point["date"]),
                "value": value,
            }
        )

    chart_path = " ".join(
        f"{'M' if index == 0 else 'L'} {point['x']} {point['y']}"
        for index, point in enumerate(chart_points)
    )

    chart_guides = []
    for ratio in (0.0, 0.5, 1.0):
        guide_value = raw_max_value * ratio
        y = padding + inner_height - ((guide_value / scale_max_value) * inner_height)
        chart_guides.append(
            {
                "y": round(y, 2),
                "label": f"{guide_value:.2f}",
            }
        )

    return {
        "chart_points": chart_points,
        "chart_path": chart_path,
        "chart_guides": chart_guides,
        "chart_width": width,
        "chart_height": height,
        "chart_max_value": raw_max_value,
    }


def get_finance_date_range(selected_month: str | None = None) -> dict:
    if selected_month:
        month_text = selected_month.strip()
        try:
            month_start = date.fromisoformat(f"{month_text}-01")
        except ValueError:
            month_start = date.fromisoformat(today_iso()).replace(day=1)
    else:
        month_start = date.fromisoformat(today_iso()).replace(day=1)

    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)

    return {
        "selected_month": month_start.strftime("%Y-%m"),
        "month_label": month_start.strftime("%B %Y"),
        "start_date": month_start.isoformat(),
        "end_date": month_end.isoformat(),
        "interval": "day",
    }


def build_finance_dashboard_context(selected_month: str | None = None) -> dict:
    date_range = get_finance_date_range(selected_month)
    start_date = date_range["start_date"]
    end_date = date_range["end_date"]

    time_series_data = get_time_series_data(start_date, end_date, date_range["interval"])
    return {
        **date_range,
        "little_shop_spend": get_little_shop_spend(start_date, end_date),
        "kit_transfer_value": get_kit_transfer_value(start_date, end_date),
        "kit_supplier_spend": get_kit_supplier_spend(start_date, end_date),
        "net_kit_spend": get_net_kit_spend(start_date, end_date),
        "little_shop_breakdown": get_breakdown_per_item(start_date, end_date, "Little Shop"),
        "kit_supplier_breakdown": get_breakdown_per_item(start_date, end_date, "Keele Suppliers"),
        "kit_transfer_breakdown": get_breakdown_per_item(start_date, end_date, "Keele Transfers"),
        "time_series_data": time_series_data,
        **_build_chart_geometry(time_series_data),
    }
