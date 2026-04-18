import argparse
import io
import os
import threading
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, redirect, render_template, request, url_for

from .cli import cmd_run_day
from .db import (
    VALID_BASE_UNITS,
    get_count_entry_rows,
    get_item_for_edit,
    get_items_with_suppliers,
    generate_request_list,
    generate_shopping_list,
    generate_supplier_shopping_list,
    init_db,
    recent_run_history,
    record_run_history,
    save_web_count,
    save_item,
    seed_locations,
)


app = Flask(
    __name__,
    template_folder=str(os.path.join(os.path.dirname(__file__), "..", "..", "templates")),
)
_run_lock = threading.Lock()


@app.context_processor
def inject_nav_state():
    path = request.path
    if path.startswith("/items"):
        active_page = "items"
    elif path.startswith("/counts"):
        active_page = "counts"
    elif path.startswith("/shopping-lists"):
        active_page = "shopping_lists"
    elif path.startswith("/request-lists"):
        active_page = "request_lists"
    else:
        active_page = "dashboard"
    return {"active_page": active_page}


def _today() -> str:
    timezone_name = os.environ.get("STOCK_TIMEZONE", "Europe/London")
    try:
        return datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    except ZoneInfoNotFoundError:
        return datetime.now().date().isoformat()


def _bootstrap() -> None:
    init_db()
    seed_locations()


def _dashboard_context() -> dict:
    history = recent_run_history(limit=8)
    items = get_items_with_suppliers()
    categories = sorted({str(row["category"]) for row in items if row["category"]})
    return {
        "today": _today(),
        "timezone_name": os.environ.get("STOCK_TIMEZONE", "Europe/London"),
        "history": history,
        "item_count": len(items),
        "category_count": len(categories),
        "run_count": len(history),
    }


def _count_locations() -> list[str]:
    return ["Keele", "Little Shop"]


def _build_count_template_context(
    *,
    location: str,
    count_date: str,
    count_rows: list[dict],
    count_id: int | None,
    is_reconciled: bool,
    error_message: str = "",
    success_message: str = "",
) -> dict:
    grouped_rows: dict[str, list[dict]] = {}
    for row in count_rows:
        grouped_rows.setdefault(row["category"], []).append(row)

    total_items = len(count_rows)
    entered_items = sum(1 for row in count_rows if str(row["counted_qty"]).strip() != "")

    return {
        "location": location,
        "count_date": count_date,
        "count_id": count_id,
        "is_reconciled": is_reconciled,
        "grouped_rows": grouped_rows,
        "locations": _count_locations(),
        "error_message": error_message,
        "success_message": success_message,
        "total_items": total_items,
        "entered_items": entered_items,
    }


def _build_shopping_list_context(location: str, count_date: str, rows: list[dict]) -> dict:
    grouped_rows: dict[str, list[dict]] = {}
    for row in rows:
        grouped_rows.setdefault(row["category"], []).append(row)

    total_items = len(rows)
    total_order_qty = sum(float(row["order_qty"]) for row in rows)

    return {
        "location": location,
        "count_date": count_date,
        "grouped_rows": grouped_rows,
        "total_items": total_items,
        "total_order_qty": total_order_qty,
    }


def _build_request_list_context(location: str, count_date: str, rows: list[dict], source_location: str) -> dict:
    grouped_rows: dict[str, list[dict]] = {}
    for row in rows:
        grouped_rows.setdefault(row["category"], []).append(row)

    total_items = len(rows)
    total_request_qty = sum(float(row["request_qty"]) for row in rows)
    total_fulfill_qty = sum(float(row["fulfill_qty"]) for row in rows)

    return {
        "location": location,
        "count_date": count_date,
        "source_location": source_location,
        "grouped_rows": grouped_rows,
        "total_items": total_items,
        "total_request_qty": total_request_qty,
        "total_fulfill_qty": total_fulfill_qty,
    }


@app.get("/")
def index():
    return render_template("dashboard.html", **_dashboard_context())


@app.get("/items")
def items():
    rows = get_items_with_suppliers()
    grouped_items: dict[str, list] = {}
    for row in rows:
        grouped_items.setdefault(str(row["category"]), []).append(row)

    return render_template(
        "items.html",
        grouped_items=grouped_items,
        item_count=len(rows),
        category_count=len(grouped_items),
    )


@app.get("/counts")
def counts():
    location = request.args.get("location", "Keele").strip() or "Keele"
    if location not in _count_locations():
        location = "Keele"

    count_date = request.args.get("date", _today()).strip() or _today()
    success_message = ""
    if request.args.get("saved") == "1":
        success_message = "Count saved successfully."

    count_data = get_count_entry_rows(location, count_date)
    return render_template(
        "count_form.html",
        **_build_count_template_context(
            location=location,
            count_date=count_date,
            count_rows=count_data["rows"],
            count_id=count_data["count_id"],
            is_reconciled=count_data["is_reconciled"],
            success_message=success_message,
        ),
    )


@app.post("/counts")
def save_count():
    location = request.form.get("location", "Keele").strip() or "Keele"
    count_date = request.form.get("count_date", _today()).strip() or _today()

    count_values: dict[int, str] = {}
    for key, value in request.form.items():
        if not key.startswith("qty_"):
            continue
        try:
            item_id = int(key.removeprefix("qty_"))
        except ValueError:
            continue
        count_values[item_id] = value

    try:
        save_web_count(location, count_date, count_values)
        return redirect(url_for("counts", location=location, date=count_date, saved="1"))
    except ValueError as exc:
        count_data = get_count_entry_rows(location, count_date)
        value_lookup = {row["id"]: row["counted_qty"] for row in count_data["rows"]}
        value_lookup.update(count_values)

        hydrated_rows = []
        for row in count_data["rows"]:
            hydrated = dict(row)
            hydrated["counted_qty"] = value_lookup.get(row["id"], row["counted_qty"])
            hydrated_rows.append(hydrated)

        return (
            render_template(
                "count_form.html",
                **_build_count_template_context(
                    location=location,
                    count_date=count_date,
                    count_rows=hydrated_rows,
                    count_id=count_data["count_id"],
                    is_reconciled=count_data["is_reconciled"],
                    error_message=str(exc),
                ),
            ),
            400,
        )


@app.get("/shopping-lists")
def shopping_lists():
    count_date = request.args.get("date", _today()).strip() or _today()
    location = "Keele"
    rows = generate_supplier_shopping_list(
        count_date,
        source_location_name="Keele",
        request_location_name="Little Shop",
    )
    return render_template(
        "shopping_list.html",
        **_build_shopping_list_context(location, count_date, rows),
    )


@app.get("/request-lists")
def request_lists():
    location = "Little Shop"
    count_date = request.args.get("date", _today()).strip() or _today()
    source_location = "Keele"
    rows = generate_request_list(location, count_date, source_location)
    return render_template(
        "request_list.html",
        **_build_request_list_context(location, count_date, rows, source_location),
    )


def _item_form_values(form_data: dict | None = None) -> dict:
    source = form_data or {}
    return {
        "name": source.get("name", ""),
        "category": source.get("category", ""),
        "base_unit": source.get("base_unit", ""),
        "supplier": source.get("supplier", ""),
        "ref": source.get("ref", ""),
    }


@app.get("/items/new")
def new_item():
    return render_template(
        "item_form.html",
        form_title="Add item",
        form_intro="Start with a simple item record. We can extend this page later with par levels and extra actions.",
        submit_label="Create item",
        form_action=url_for("create_item"),
        item_values=_item_form_values(),
        error_message="",
        base_units=VALID_BASE_UNITS,
        item_id=None,
    )


@app.post("/items")
def create_item():
    form_values = _item_form_values(request.form)
    try:
        save_item(
            None,
            form_values["name"],
            form_values["category"],
            form_values["base_unit"],
            form_values["supplier"],
            form_values["ref"],
        )
        return redirect(url_for("items"))
    except ValueError as exc:
        return (
            render_template(
                "item_form.html",
                form_title="Add item",
                form_intro="Start with a simple item record. We can extend this page later with par levels and extra actions.",
                submit_label="Create item",
                form_action=url_for("create_item"),
                item_values=form_values,
                error_message=str(exc),
                base_units=VALID_BASE_UNITS,
                item_id=None,
            ),
            400,
        )


@app.get("/items/<int:item_id>/edit")
def edit_item(item_id: int):
    try:
        item_values = get_item_for_edit(item_id)
    except ValueError as exc:
        return render_template(
            "run_day_result.html",
            title="Item not found",
            status="error",
            message=str(exc),
            output="",
            run_date="",
        ), 404

    return render_template(
        "item_form.html",
        form_title="Edit item",
        form_intro="This page lets you update the item details already stored in the database.",
        submit_label="Save changes",
        form_action=url_for("update_item", item_id=item_id),
        item_values=item_values,
        error_message="",
        base_units=VALID_BASE_UNITS,
        item_id=item_id,
    )


@app.post("/items/<int:item_id>")
def update_item(item_id: int):
    form_values = _item_form_values(request.form)
    try:
        save_item(
            item_id,
            form_values["name"],
            form_values["category"],
            form_values["base_unit"],
            form_values["supplier"],
            form_values["ref"],
        )
        return redirect(url_for("items"))
    except ValueError as exc:
        return (
            render_template(
                "item_form.html",
                form_title="Edit item",
                form_intro="This page lets you update the item details already stored in the database.",
                submit_label="Save changes",
                form_action=url_for("update_item", item_id=item_id),
                item_values=form_values,
                error_message=str(exc),
                base_units=VALID_BASE_UNITS,
                item_id=item_id,
            ),
            400,
        )


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200


@app.post("/run-day")
def run_day():
    expected_token = os.environ.get("STOCK_WEB_TOKEN", "").strip()
    submitted_token = request.form.get("token", "").strip()
    run_date = request.form.get("run_date", _today()).strip() or _today()

    if not expected_token:
        return (
            render_template(
                "run_day_result.html",
                title="Missing access code",
                status="error",
                message="Set STOCK_WEB_TOKEN in Railway before using the daily run screen.",
                output="",
                run_date=run_date,
            ),
            500,
        )

    if submitted_token != expected_token:
        return (
            render_template(
                "run_day_result.html",
                title="Access denied",
                status="error",
                message="The access code was incorrect.",
                output="",
                run_date=run_date,
            ),
            403,
        )

    if not _run_lock.acquire(blocking=False):
        return (
            render_template(
                "run_day_result.html",
                title="Already running",
                status="warning",
                message="A daily sync is already in progress. Please wait a minute and try again.",
                output="",
                run_date=run_date,
            ),
            409,
        )

    output = io.StringIO()
    try:
        _bootstrap()
        with redirect_stdout(output):
            cmd_run_day(argparse.Namespace(date=run_date))
        raw_output = output.getvalue() or "Run completed."
        record_run_history("run-day", run_date, "SUCCESS", raw_output)
        return render_template(
            "run_day_result.html",
            title="Run complete",
            status="success",
            message="The daily workflow finished successfully.",
            output=raw_output,
            run_date=run_date,
        )
    except Exception:
        raw_output = output.getvalue() + "\n" + traceback.format_exc()
        record_run_history("run-day", run_date, "FAILED", raw_output)
        return (
            render_template(
                "run_day_result.html",
                title="Run failed",
                status="error",
                message="Something went wrong while running the workflow.",
                output=raw_output,
                run_date=run_date,
            ),
            500,
        )
    finally:
        _run_lock.release()


def main() -> None:
    _bootstrap()
    port = int(os.environ.get("PORT", "8080"))
    from waitress import serve

    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
