from flask import Blueprint, jsonify, request

from .services.auth import login_required
from .services.counts import build_count_data, save_count_data
from .services.dashboard import get_dashboard_summary
from .services.items import list_items
from .services.planning import get_request_list_data, get_shopping_list_data

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/dashboard")
@login_required
def dashboard_summary():
    data = get_dashboard_summary()
    serializable = dict(data)
    serializable["history"] = [dict(row) for row in data["history"]]
    return jsonify(serializable)


@api.get("/items")
@login_required
def items_catalog():
    rows = [dict(row) for row in list_items()]
    return jsonify({"items": rows, "count": len(rows)})


@api.get("/counts")
@login_required
def counts_snapshot():
    location = request.args.get("location", "Keele")
    count_date = request.args.get("date")
    return jsonify(build_count_data(location, count_date))


@api.post("/counts")
@login_required
def save_counts_snapshot():
    payload = request.get_json(silent=True) or {}
    location = str(payload.get("location", "Keele"))
    count_date = str(payload.get("count_date", ""))
    counts = payload.get("counts", {})

    try:
        normalized_counts: dict[int, str] = {}
        for item_id, value in counts.items():
            normalized_counts[int(item_id)] = "" if value is None else str(value)

        count_id = save_count_data(location, count_date, normalized_counts)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({"status": "ok", "count_id": count_id})


@api.get("/request-lists")
@login_required
def request_list_snapshot():
    count_date = request.args.get("date")
    return jsonify(get_request_list_data(count_date))


@api.get("/shopping-lists")
@login_required
def shopping_list_snapshot():
    count_date = request.args.get("date")
    return jsonify(get_shopping_list_data(count_date))
