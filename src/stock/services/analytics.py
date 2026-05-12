from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, pstdev
from typing import Mapping

from ..db import current_stock, get_conn, get_item_supplier_summary
from .dashboard import today_iso


CATEGORY_FILTERS = ["milk", "bakery", "food", "syrups", "packaging", "other"]
PERIOD_OPTIONS = {
    "7": 7,
    "30": 30,
    "90": 90,
}
USAGE_TYPES = {"TRANSFER_OUT", "WASTE", "ADJUSTMENT"}
REPLENISHMENT_TYPES = {"RECEIVE", "TRANSFER_IN"}
DEFAULT_THRESHOLDS = {
    "spike_pct": 30.0,
    "drop_pct": -30.0,
    "critical_days_remaining": 3.0,
    "warning_days_remaining": 7.0,
    "waste_pct": 12.0,
    "volatility_ratio": 0.65,
}


def _parse_date(value: str | None, fallback: date) -> date:
    text = (value or "").strip()
    if not text:
        return fallback
    try:
        return date.fromisoformat(text)
    except ValueError:
        return fallback


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _category_bucket(category: str) -> str:
    text = (category or "").strip().lower()
    if any(token in text for token in ["milk", "dairy", "oat"]):
        return "milk"
    if any(token in text for token in ["bakery", "bread", "pastry", "cake", "croissant"]):
        return "bakery"
    if any(token in text for token in ["bean", "coffee", "espresso", "food", "sandwich", "salad", "cake", "pastry"]):
        return "food"
    if "syrup" in text:
        return "syrups"
    if any(token in text for token in ["pack", "cup", "lid", "bag", "napkin"]):
        return "packaging"
    return "other"


def _fmt_qty(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value - round(value)) < 0.05:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def _pct_change(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 100.0 if current > 0 else 0.0
    return ((current - baseline) / baseline) * 100


def _moving_average(values: list[float], window: int = 7) -> list[float]:
    output = []
    for idx in range(len(values)):
        chunk = values[max(0, idx - window + 1): idx + 1]
        output.append(mean(chunk) if chunk else 0.0)
    return output


def _stable_noise(item_id: int, day: date, spread: float = 0.22) -> float:
    digest = hashlib.sha256(f"{item_id}:{day.isoformat()}".encode("utf-8")).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    return 1 + ((raw - 0.5) * 2 * spread)


def _load_items() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.name,
                i.category,
                i.base_unit,
                i.cost_per_unit,
                COALESCE(SUM(p.par_qty_base), 0) AS total_par
            FROM items i
            LEFT JOIN par_levels p ON p.item_id = i.id
            GROUP BY i.id, i.name, i.category, i.base_unit, i.cost_per_unit
            ORDER BY LOWER(i.category), LOWER(i.name);
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _load_transactions(start: date, end: date, item_id: int | None = None) -> list[dict]:
    params: list[object] = [start.isoformat(), (end + timedelta(days=1)).isoformat()]
    item_where = ""
    if item_id is not None:
        item_where = "AND st.item_id = ?"
        params.append(int(item_id))

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                st.id,
                date(st.ts) AS tx_date,
                st.ts,
                st.item_id,
                st.location_id,
                st.qty_base,
                st.cost_per_unit_at_time,
                st.type,
                st.note,
                i.name,
                i.category,
                i.base_unit,
                i.cost_per_unit,
                l.name AS location
            FROM stock_transactions st
            JOIN items i ON i.id = st.item_id
            JOIN locations l ON l.id = st.location_id
            WHERE date(st.ts) >= ?
              AND date(st.ts) < ?
              {item_where}
            ORDER BY datetime(st.ts), st.id;
            """,
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def _has_real_history() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM stock_transactions;").fetchone()
    return int(row["n"] or 0) > 0


def _demo_daily_usage(items: list[dict], days: list[date]) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        item_id = int(item["id"])
        category = _category_bucket(str(item["category"]))
        base = {
            "milk": 9.0,
            "bakery": 7.5,
            "food": 5.5,
            "syrups": 2.4,
            "packaging": 14.0,
            "other": 3.0,
        }[category]
        if "oat" in str(item["name"]).lower():
            base *= 1.35
        if "espresso" in str(item["name"]).lower():
            base *= 1.4

        for idx, day in enumerate(days):
            weekday_multiplier = 1.22 if day.weekday() in {4, 5} else 0.92 if day.weekday() == 0 else 1.0
            trend = 1 + (idx / max(len(days) - 1, 1)) * (0.1 + (item_id % 4) * 0.035)
            qty = max(base * weekday_multiplier * trend * _stable_noise(item_id, day), 0.05)
            waste = qty * (0.03 + ((item_id + idx) % 5) * 0.006)
            rows.append(
                {
                    "date": day.isoformat(),
                    "item_id": item_id,
                    "name": item["name"],
                    "category": item["category"],
                    "category_bucket": category,
                    "base_unit": item["base_unit"],
                    "usage_qty": qty,
                    "waste_qty": waste,
                    "replenished_qty": qty * 1.4 if day.weekday() == 1 else 0.0,
                    "value": qty * float(item["cost_per_unit"] or 0),
                    "is_demo": True,
                }
            )
    return rows


def _daily_usage_from_transactions(items: list[dict], start: date, end: date, item_id: int | None = None) -> list[dict]:
    tx_rows = _load_transactions(start, end, item_id=item_id)
    grouped: dict[tuple[str, int], dict] = {}

    for tx in tx_rows:
        qty = float(tx["qty_base"] or 0)
        tx_type = str(tx["type"])
        usage_qty = abs(qty) if tx_type in USAGE_TYPES and qty < 0 else 0.0
        waste_qty = abs(qty) if tx_type == "WASTE" and qty < 0 else 0.0
        replenished_qty = abs(qty) if tx_type in REPLENISHMENT_TYPES and qty > 0 else 0.0
        if usage_qty <= 0 and waste_qty <= 0 and replenished_qty <= 0:
            continue
        key = (str(tx["tx_date"]), int(tx["item_id"]))
        target = grouped.setdefault(
            key,
            {
                "date": str(tx["tx_date"]),
                "item_id": int(tx["item_id"]),
                "name": tx["name"],
                "category": tx["category"],
                "category_bucket": _category_bucket(str(tx["category"])),
                "base_unit": tx["base_unit"],
                "usage_qty": 0.0,
                "waste_qty": 0.0,
                "replenished_qty": 0.0,
                "value": 0.0,
                "is_demo": False,
            },
        )
        target["usage_qty"] += usage_qty
        target["waste_qty"] += waste_qty
        target["replenished_qty"] += replenished_qty
        target["value"] += usage_qty * float(tx["cost_per_unit_at_time"] or tx["cost_per_unit"] or 0)

    if grouped:
        return list(grouped.values())

    selected_items = [item for item in items if item_id is None or int(item["id"]) == int(item_id)]
    return _demo_daily_usage(selected_items, _date_range(start, end))


def _filter_usage(rows: list[dict], category: str) -> list[dict]:
    if not category:
        return rows
    return [row for row in rows if row["category_bucket"] == category]


def _series_by_day(rows: list[dict], days: list[date], field: str = "usage_qty") -> list[dict]:
    totals = defaultdict(float)
    for row in rows:
        totals[str(row["date"])] += float(row[field] or 0)
    return [
        {
            "label": day.strftime("%d %b"),
            "date": day.isoformat(),
            "value": round(totals[day.isoformat()], 2),
        }
        for day in days
    ]


def _series_by_week(rows: list[dict]) -> list[dict]:
    totals = defaultdict(float)
    for row in rows:
        day = date.fromisoformat(str(row["date"]))
        week_start = day - timedelta(days=day.weekday())
        totals[week_start.isoformat()] += float(row["usage_qty"] or 0)
    return [
        {"label": datetime.fromisoformat(key).strftime("%d %b"), "date": key, "value": round(value, 2)}
        for key, value in sorted(totals.items())
    ]


def _top_items(rows: list[dict], limit: int = 8) -> list[dict]:
    grouped: dict[int, dict] = {}
    for row in rows:
        item = grouped.setdefault(
            int(row["item_id"]),
            {
                "item_id": int(row["item_id"]),
                "name": row["name"],
                "category": row["category"],
                "base_unit": row["base_unit"],
                "usage_qty": 0.0,
                "value": 0.0,
            },
        )
        item["usage_qty"] += float(row["usage_qty"] or 0)
        item["value"] += float(row["value"] or 0)
    return sorted(grouped.values(), key=lambda item: item["usage_qty"], reverse=True)[:limit]


def _fastest_increasing(rows: list[dict], days: list[date], limit: int = 6) -> list[dict]:
    if len(days) < 4:
        return []
    midpoint = days[0] + (days[-1] - days[0]) / 2
    grouped = defaultdict(lambda: {"early": 0.0, "late": 0.0, "name": "", "item_id": 0})
    for row in rows:
        bucket = grouped[int(row["item_id"])]
        bucket["name"] = row["name"]
        bucket["item_id"] = int(row["item_id"])
        if date.fromisoformat(str(row["date"])) <= midpoint:
            bucket["early"] += float(row["usage_qty"] or 0)
        else:
            bucket["late"] += float(row["usage_qty"] or 0)
    scored = []
    for bucket in grouped.values():
        change = _pct_change(bucket["late"], bucket["early"])
        scored.append({**bucket, "change_pct": round(change, 1), "value": max(change, 0)})
    return sorted(scored, key=lambda item: item["change_pct"], reverse=True)[:limit]


def _category_breakdown(rows: list[dict]) -> list[dict]:
    totals = defaultdict(float)
    labels = {
        "milk": "Milk",
        "bakery": "Bakery",
        "food": "Food",
        "syrups": "Syrups",
        "packaging": "Packaging",
        "other": "Other",
    }
    for row in rows:
        totals[row["category_bucket"]] += float(row["usage_qty"] or 0)
    total = sum(totals.values())
    return [
        {
            "key": key,
            "label": labels[key],
            "value": round(totals[key], 2),
            "percent": round((totals[key] / total * 100) if total else 0, 1),
        }
        for key in CATEGORY_FILTERS
        if totals[key] > 0
    ]


def _current_stock_by_item(items: list[dict]) -> dict[int, float]:
    stocks: dict[int, float] = {}
    for item in items:
        total = 0.0
        for location in ("Keele", "Little Shop"):
            try:
                total += current_stock(location, str(item["name"]))
            except ValueError:
                continue
        stocks[int(item["id"])] = total
    return stocks


def _low_stock_items(items: list[dict], stocks: dict[int, float]) -> list[dict]:
    low = []
    for item in items:
        par = float(item["total_par"] or 0)
        if par > 0 and stocks.get(int(item["id"]), 0.0) < par:
            low.append({**item, "current_stock": stocks.get(int(item["id"]), 0.0), "par": par})
    return low


def _line_chart(series: list[dict], *, width: int = 720, height: int = 230, fill: bool = False) -> dict:
    pad_x = 42
    pad_y = 24
    values = [float(point["value"] or 0) for point in series]
    max_value = max(values) if values else 0
    scale_max = max(max_value, 1.0)
    usable_w = width - (pad_x * 2)
    usable_h = height - (pad_y * 2)
    points = []
    for idx, point in enumerate(series):
        x = pad_x + (usable_w * idx / max(len(series) - 1, 1))
        y = pad_y + usable_h - ((float(point["value"] or 0) / scale_max) * usable_h)
        points.append({**point, "x": round(x, 2), "y": round(y, 2), "tooltip": f"{point['label']}: {_fmt_qty(float(point['value']))}"})
    path = ""
    if points:
        path = " ".join([("M" if idx == 0 else "L") + f" {point['x']} {point['y']}" for idx, point in enumerate(points)])
    area_path = ""
    if fill and points:
        baseline = height - pad_y
        area_path = f"M {points[0]['x']} {baseline} " + path.replace("M", "L", 1) + f" L {points[-1]['x']} {baseline} Z"
    guides = []
    for ratio in (0, 0.5, 1):
        y = pad_y + usable_h - (ratio * usable_h)
        guides.append({"y": round(y, 2), "label": _fmt_qty(scale_max * ratio)})
    return {"width": width, "height": height, "points": points, "path": path, "area_path": area_path, "guides": guides}


def _bar_chart(rows: list[dict], *, label_key: str = "name", value_key: str = "usage_qty", width: int = 720, height: int = 260) -> dict:
    max_value = max([float(row.get(value_key, 0) or 0) for row in rows], default=1)
    max_value = max(max_value, 1)
    bars = []
    left = 44
    top = 22
    gap = 10
    usable_w = width - 74
    bar_h = max(18, (height - top - 24 - (gap * max(len(rows) - 1, 0))) / max(len(rows), 1))
    for idx, row in enumerate(rows):
        value = float(row.get(value_key, 0) or 0)
        bars.append(
            {
                **row,
                "x": left,
                "y": round(top + idx * (bar_h + gap), 2),
                "width": round((value / max_value) * usable_w, 2),
                "height": round(bar_h, 2),
                "label": str(row.get(label_key, "")),
                "value_label": _fmt_qty(value),
            }
        )
    return {"width": width, "height": height, "bars": bars}


def _donut_chart(rows: list[dict], *, radius: int = 64) -> dict:
    total = sum(float(row["value"] or 0) for row in rows)
    circumference = 2 * math.pi * radius
    offset = 0.0
    colors = ["#1f6f5f", "#d8822a", "#62748a", "#8a5f3d", "#7a8f3b", "#a25528"]
    segments = []
    for idx, row in enumerate(rows):
        value = float(row["value"] or 0)
        fraction = (value / total) if total else 0
        dash = fraction * circumference
        segments.append({**row, "color": colors[idx % len(colors)], "dash": round(dash, 2), "gap": round(circumference - dash, 2), "offset": round(-offset, 2)})
        offset += dash
    return {"radius": radius, "circumference": round(circumference, 2), "segments": segments, "total": round(total, 2)}


def detect_anomalies(
    usage_rows: list[dict],
    items: list[dict],
    stocks: dict[int, float],
    *,
    thresholds: Mapping[str, float] | None = None,
) -> list[dict]:
    config = {**DEFAULT_THRESHOLDS, **dict(thresholds or {})}
    by_item_day = defaultdict(lambda: defaultdict(float))
    item_meta = {int(item["id"]): item for item in items}

    for row in usage_rows:
        by_item_day[int(row["item_id"])][str(row["date"])] += float(row["usage_qty"] or 0)

    alerts = []
    for item_id, daily in by_item_day.items():
        ordered = [daily[key] for key in sorted(daily)]
        if not ordered:
            continue
        recent = ordered[-7:]
        baseline = ordered[-37:-7] or ordered[:-7] or ordered
        recent_avg = mean(recent) if recent else 0.0
        baseline_avg = mean(baseline) if baseline else 0.0
        change = _pct_change(recent_avg, baseline_avg)
        item = item_meta.get(item_id, {"name": "Unknown item", "base_unit": "units"})

        if change >= config["spike_pct"]:
            alerts.append(
                {
                    "id": f"spike-{item_id}",
                    "severity": "warning",
                    "title": f"{item['name']} usage is {change:.0f}% higher than normal",
                    "body": "The last 7 days are running above the longer baseline, so check par levels or upcoming orders.",
                    "item_id": item_id,
                }
            )
        elif change <= config["drop_pct"]:
            alerts.append(
                {
                    "id": f"drop-{item_id}",
                    "severity": "info",
                    "title": f"Unexpected drop in {item['name']} usage",
                    "body": f"Recent usage is {abs(change):.0f}% below the baseline. This can indicate a menu change or missed stock movement.",
                    "item_id": item_id,
                }
            )

        stock = stocks.get(item_id, 0.0)
        if recent_avg > 0 and stock > 0:
            days_remaining = stock / recent_avg
            if days_remaining <= config["critical_days_remaining"]:
                severity = "critical"
            elif days_remaining <= config["warning_days_remaining"]:
                severity = "warning"
            else:
                severity = ""
            if severity:
                alerts.append(
                    {
                        "id": f"depletion-{item_id}",
                        "severity": severity,
                        "title": f"{item['name']} may run out in {days_remaining:.1f} days",
                        "body": "Current stock divided by recent daily usage is inside the reorder window.",
                        "item_id": item_id,
                    }
                )

        if len(recent) >= 3 and recent[-1] > recent[-2] > recent[-3] and recent[-3] > 0:
            alerts.append(
                {
                    "id": f"trend-{item_id}",
                    "severity": "info",
                    "title": f"{item['name']} has increased for 3 consecutive days",
                    "body": "Demand is trending upward in the current week.",
                    "item_id": item_id,
                }
            )

    waste_by_item = defaultdict(float)
    usage_by_item = defaultdict(float)
    for row in usage_rows:
        waste_by_item[int(row["item_id"])] += float(row["waste_qty"] or 0)
        usage_by_item[int(row["item_id"])] += float(row["usage_qty"] or 0)
    for item_id, waste_qty in waste_by_item.items():
        usage_qty = usage_by_item[item_id]
        if usage_qty > 0 and (waste_qty / usage_qty * 100) >= config["waste_pct"]:
            item = item_meta.get(item_id, {"name": "Unknown item"})
            alerts.append(
                {
                    "id": f"waste-{item_id}",
                    "severity": "warning",
                    "title": f"{item['name']} waste is unusually high",
                    "body": f"Waste is {waste_qty / usage_qty * 100:.0f}% of recorded usage in this range.",
                    "item_id": item_id,
                }
            )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(alerts, key=lambda alert: severity_rank.get(alert["severity"], 9))[:8]


def _recent_activity(usage_rows: list[dict], tx_rows: list[dict]) -> list[dict]:
    activity = []
    for tx in sorted(tx_rows, key=lambda row: str(row["ts"]), reverse=True)[:8]:
        qty = abs(float(tx["qty_base"] or 0))
        verb = {
            "RECEIVE": "Stock addition",
            "TRANSFER_IN": "Stock addition",
            "TRANSFER_OUT": "Stock deduction",
            "WASTE": "Waste recorded",
            "ADJUSTMENT": "Stock correction",
        }.get(str(tx["type"]), "Stock movement")
        activity.append(
            {
                "kind": verb,
                "title": f"{verb}: {tx['name']}",
                "body": f"{_fmt_qty(qty)} {tx['base_unit']} at {tx['location']}",
                "date": str(tx["tx_date"]),
            }
        )
    if activity:
        return activity

    for row in sorted(usage_rows, key=lambda item: (str(item["date"]), float(item["usage_qty"] or 0)), reverse=True)[:8]:
        activity.append(
            {
                "kind": "Demo usage",
                "title": f"Stock deduction: {row['name']}",
                "body": f"{_fmt_qty(float(row['usage_qty']))} {row['base_unit']} modelled usage",
                "date": str(row["date"]),
            }
        )
    return activity


def _resolve_filters(args: Mapping[str, str]) -> dict:
    today = _parse_date(today_iso(), datetime.now().date())
    period = (args.get("period") or "30").strip()
    if period == "custom":
        end = _parse_date(args.get("end"), today)
        start = _parse_date(args.get("start"), end - timedelta(days=29))
    else:
        days = PERIOD_OPTIONS.get(period, 30)
        end = today
        start = end - timedelta(days=days - 1)
    category = (args.get("category") or "").strip().lower()
    if category not in CATEGORY_FILTERS:
        category = ""
    return {"period": period, "start": start, "end": end, "category": category}


def build_analytics_dashboard_context(args: Mapping[str, str]) -> dict:
    filters = _resolve_filters(args)
    items = _load_items()
    days = _date_range(filters["start"], filters["end"])
    usage_rows = _daily_usage_from_transactions(items, filters["start"], filters["end"])
    filtered_rows = _filter_usage(usage_rows, filters["category"])
    stocks = _current_stock_by_item(items)
    low_stock = _low_stock_items(items, stocks)
    top = _top_items(filtered_rows, limit=8)
    daily_series = _series_by_day(filtered_rows, days)
    weekly_series = _series_by_week(filtered_rows)
    increasing = _fastest_increasing(filtered_rows, days)
    categories = _category_breakdown(filtered_rows)
    alerts = detect_anomalies(usage_rows, items, stocks)
    total_usage = sum(float(row["usage_qty"] or 0) for row in filtered_rows)
    prior_start = filters["start"] - timedelta(days=len(days))
    prior_end = filters["start"] - timedelta(days=1)
    prior_rows = _filter_usage(_daily_usage_from_transactions(items, prior_start, prior_end), filters["category"])
    prior_usage = sum(float(row["usage_qty"] or 0) for row in prior_rows)
    week_rows = [row for row in usage_rows if date.fromisoformat(str(row["date"])) >= filters["end"] - timedelta(days=6)]
    most_used_week = _top_items(_filter_usage(week_rows, filters["category"]), limit=1)
    estimated_value = sum(stocks.get(int(item["id"]), 0.0) * float(item["cost_per_unit"] or 0) for item in items)
    tx_rows = _load_transactions(filters["start"], filters["end"])

    return {
        "filters": {**filters, "start": filters["start"].isoformat(), "end": filters["end"].isoformat()},
        "period_options": PERIOD_OPTIONS,
        "category_filters": CATEGORY_FILTERS,
        "has_real_history": _has_real_history(),
        "kpis": {
            "total_items": len(items),
            "low_stock_items": len(low_stock),
            "most_used_week": most_used_week[0]["name"] if most_used_week else "No usage yet",
            "average_daily_usage": total_usage / max(len(days), 1),
            "weekly_usage_change_pct": _pct_change(total_usage, prior_usage),
            "estimated_stock_value": estimated_value,
        },
        "alerts": alerts,
        "daily_chart": _line_chart(daily_series, fill=True),
        "weekly_chart": _line_chart(weekly_series, width=720, height=220),
        "top_items_chart": _bar_chart(top),
        "increasing_chart": _bar_chart(increasing, value_key="value", height=230),
        "category_chart": _donut_chart(categories),
        "category_breakdown": categories,
        "top_items": top,
        "recent_activity": _recent_activity(filtered_rows, tx_rows),
        "low_stock": low_stock[:6],
    }


def _item_or_404(item_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, category, base_unit, cost_per_unit
            FROM items
            WHERE id = ?;
            """,
            (int(item_id),),
        ).fetchone()
    if row is None:
        raise ValueError(f"Item {item_id} was not found.")
    return dict(row)


def _item_daily_rows(item: dict, start: date, end: date) -> list[dict]:
    days = _date_range(start, end)
    raw = _daily_usage_from_transactions([item], start, end, item_id=int(item["id"]))
    grouped = defaultdict(lambda: {"usage_qty": 0.0, "waste_qty": 0.0, "replenished_qty": 0.0})
    for row in raw:
        grouped[str(row["date"])]["usage_qty"] += float(row["usage_qty"] or 0)
        grouped[str(row["date"])]["waste_qty"] += float(row["waste_qty"] or 0)
        grouped[str(row["date"])]["replenished_qty"] += float(row["replenished_qty"] or 0)
    stock = 0.0
    output = []
    for day in days:
        key = day.isoformat()
        stock += grouped[key]["replenished_qty"] - grouped[key]["usage_qty"]
        output.append(
            {
                "date": key,
                "label": day.strftime("%d %b"),
                "usage_qty": round(grouped[key]["usage_qty"], 2),
                "waste_qty": round(grouped[key]["waste_qty"], 2),
                "replenished_qty": round(grouped[key]["replenished_qty"], 2),
                "stock_level": round(max(stock, 0.0), 2),
            }
        )
    current_total = 0.0
    for location in ("Keele", "Little Shop"):
        try:
            current_total += current_stock(location, str(item["name"]))
        except ValueError:
            continue
    if output:
        diff = current_total - output[-1]["stock_level"]
        for row in output:
            row["stock_level"] = round(max(row["stock_level"] + diff, 0.0), 2)
    return output


def _heatmap(rows: list[dict]) -> list[dict]:
    totals = defaultdict(float)
    counts = defaultdict(int)
    for row in rows:
        day = date.fromisoformat(str(row["date"]))
        key = day.weekday()
        totals[key] += float(row["usage_qty"] or 0)
        counts[key] += 1
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    max_value = max([totals[idx] / max(counts[idx], 1) for idx in range(7)], default=1)
    return [
        {
            "day": names[idx],
            "value": round(totals[idx] / max(counts[idx], 1), 2),
            "intensity": round((totals[idx] / max(counts[idx], 1)) / max(max_value, 1), 2),
        }
        for idx in range(7)
    ]


def build_item_analytics_context(item_id: int, args: Mapping[str, str]) -> dict:
    filters = _resolve_filters(args)
    item = _item_or_404(item_id)
    rows = _item_daily_rows(item, filters["start"], filters["end"])
    usage_values = [float(row["usage_qty"] or 0) for row in rows]
    moving = _moving_average(usage_values)
    stock_series = [{"label": row["label"], "date": row["date"], "value": row["stock_level"]} for row in rows]
    usage_series = [{"label": row["label"], "date": row["date"], "value": row["usage_qty"]} for row in rows]
    average_daily = mean(usage_values) if usage_values else 0.0
    recent_daily = mean(usage_values[-7:]) if usage_values[-7:] else average_daily
    total_usage = sum(usage_values)
    total_waste = sum(float(row["waste_qty"] or 0) for row in rows)
    waste_pct = (total_waste / total_usage * 100) if total_usage else 0.0
    current_total = rows[-1]["stock_level"] if rows else 0.0
    days_remaining = (current_total / recent_daily) if recent_daily > 0 else None
    reorder_date = None
    if days_remaining is not None:
        reorder_date = (filters["end"] + timedelta(days=max(math.floor(days_remaining) - 2, 0))).isoformat()
    first_week = sum(usage_values[:7])
    last_week = sum(usage_values[-7:])
    usage_change = _pct_change(last_week, first_week)
    trend_direction = "Increasing" if usage_change > 10 else "Decreasing" if usage_change < -10 else "Stable"
    volatility = (pstdev(usage_values) / average_daily) if average_daily > 0 and len(usage_values) > 1 else 0.0
    insights = []
    if usage_change > 20:
        insights.append("Usage has steadily increased over the selected period.")
    if days_remaining is not None and days_remaining <= 7:
        insights.append(f"Current depletion rate suggests reorder within {max(math.ceil(days_remaining), 1)} days.")
    if volatility >= DEFAULT_THRESHOLDS["volatility_ratio"]:
        insights.append("This product shows highly volatile demand.")
    if waste_pct >= DEFAULT_THRESHOLDS["waste_pct"]:
        insights.append("Waste is above the normal operating threshold.")
    if not insights:
        insights.append("Usage is currently stable against the selected history window.")

    comparison_weekly = _series_by_week([
        {
            "date": row["date"],
            "usage_qty": row["usage_qty"],
        }
        for row in rows
    ])
    monthly_totals = defaultdict(float)
    for row in rows:
        month_key = str(row["date"])[:7]
        monthly_totals[month_key] += float(row["usage_qty"] or 0)
    replenishment_events = [row for row in rows if float(row["replenished_qty"] or 0) > 0][-8:]
    waste_events = [row for row in rows if float(row["waste_qty"] or 0) > 0][-8:]
    peak_days = sorted(rows, key=lambda row: float(row["usage_qty"] or 0), reverse=True)[:5]
    moving_series = [
        {"label": row["label"], "date": row["date"], "value": round(moving[idx], 2)}
        for idx, row in enumerate(rows)
    ]

    return {
        "item": item,
        "supplier": get_item_supplier_summary(int(item["id"])),
        "filters": {**filters, "start": filters["start"].isoformat(), "end": filters["end"].isoformat()},
        "period_options": PERIOD_OPTIONS,
        "category_filters": CATEGORY_FILTERS,
        "overview": {
            "current_stock": current_total,
            "average_daily_usage": average_daily,
            "supplier": get_item_supplier_summary(int(item["id"])),
            "estimated_depletion_date": (filters["end"] + timedelta(days=math.ceil(days_remaining))).isoformat() if days_remaining is not None else "Unknown",
            "reorder_recommendation": "Reorder now" if days_remaining is not None and days_remaining <= 5 else "Monitor",
            "waste_pct": waste_pct,
            "trend_direction": trend_direction,
            "days_remaining": days_remaining,
            "reorder_date": reorder_date or "Unknown",
        },
        "insights": insights,
        "stock_chart": _line_chart(stock_series, fill=True),
        "usage_chart": _line_chart(usage_series, height=200),
        "moving_chart": _line_chart(moving_series, height=200),
        "weekly_chart": _bar_chart(comparison_weekly, label_key="label", value_key="value", height=230),
        "monthly_rows": [{"month": key, "usage_qty": round(value, 2)} for key, value in sorted(monthly_totals.items())],
        "peak_days": peak_days,
        "heatmap": _heatmap(rows),
        "reorder_history": replenishment_events,
        "waste_history": waste_events,
        "raw_rows": rows,
    }
