from flask import Blueprint, jsonify, request

from .services.auth import get_current_user, login_required, role_required
from .services.counts import build_count_data, save_count_data
from .services.dashboard import get_dashboard_summary
from .services.items import list_items
from .services.planning import (
    add_custom_shopping_list_item,
    edit_custom_shopping_list_item,
    get_request_list_data,
    get_shopping_list_data,
    remove_custom_shopping_list_item,
)
from .services.sections import list_section_settings, save_section_visibility, visible_categories_for_user

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
    rows = [dict(row) for row in list_items(visible_categories=visible_categories_for_user(get_current_user()))]
    return jsonify({"items": rows, "count": len(rows)})


@api.get("/counts")
@login_required
def counts_snapshot():
    location = request.args.get("location", "Keele")
    count_date = request.args.get("date")
    return jsonify(build_count_data(location, count_date, visible_categories=visible_categories_for_user(get_current_user())))


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

        count_id = save_count_data(
            location,
            count_date,
            normalized_counts,
            visible_categories=visible_categories_for_user(get_current_user()),
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({"status": "ok", "count_id": count_id})


@api.get("/request-lists")
@login_required
def request_list_snapshot():
    count_date = request.args.get("date")
    return jsonify(get_request_list_data(count_date, visible_categories=visible_categories_for_user(get_current_user())))


@api.get("/shopping-lists")
@login_required
def shopping_list_snapshot():
    count_date = request.args.get("date")
    return jsonify(get_shopping_list_data(count_date, visible_categories=visible_categories_for_user(get_current_user())))


@api.post("/shopping-lists/custom-items")
@role_required("manager", "admin")
def shopping_list_custom_item_create():
    payload = request.get_json(silent=True) or {}
    try:
        custom_item_id = add_custom_shopping_list_item(
            str(payload.get("count_date", "")),
            str(payload.get("item_name", "")),
            str(payload.get("quantity", "")),
            int(get_current_user().id) if get_current_user().id else None,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok", "id": custom_item_id}), 201


@api.put("/shopping-lists/custom-items/<int:custom_item_id>")
@role_required("manager", "admin")
def shopping_list_custom_item_update(custom_item_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        edit_custom_shopping_list_item(
            custom_item_id,
            str(payload.get("item_name", "")),
            str(payload.get("quantity", "")),
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok"})


@api.delete("/shopping-lists/custom-items/<int:custom_item_id>")
@role_required("manager", "admin")
def shopping_list_custom_item_delete(custom_item_id: int):
    try:
        remove_custom_shopping_list_item(custom_item_id)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok"})


@api.get("/admin/sections")
@role_required("admin")
def section_settings_snapshot():
    return jsonify({"sections": list_section_settings()})


@api.patch("/admin/sections/<int:section_id>")
@role_required("admin")
def section_settings_update(section_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        save_section_visibility(section_id, bool(payload.get("visible_to_staff")))
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok"})
