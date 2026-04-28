import io
import os
import threading
import traceback
from contextlib import redirect_stdout
from urllib.parse import urlparse

from flask import Flask, g, redirect, render_template, request, send_file, session, url_for

from .api import api
from .db import init_db, seed_locations
from .presentation import (
    active_page_for_path,
    build_count_page_context,
    build_items_page_context,
    build_request_list_page_context,
    build_shopping_list_page_context,
)
from .services.admin import (
    create_user_record,
    list_user_accounts,
    reset_user_password,
    update_user_active_record,
    update_user_role_record,
)
from .services.audit import build_finance_dashboard_context, get_request_list_value
from .services.auth import (
    AnonymousUser,
    VALID_USER_ROLES,
    authenticate_user,
    get_current_user,
    load_authenticated_user,
    login_required,
    login_user,
    logout_user,
    role_required,
)
from .services.counts import build_count_data, get_count_status_overview, get_daily_sync_readiness, save_count_data
from .services.daily_run import run_day as run_daily_workflow
from .services.dashboard import get_dashboard_summary, today_iso
from .services.history import save_run_history
from .services.invoices import (
    build_invoice_hub_data,
    get_invoice_detail,
    get_invoice_file_path,
    review_invoice,
    save_supplier_invoice_upload,
)
from .services.items import get_base_units, get_item, list_items, save_item_record
from .services.operations import build_delivery_form_data, confirm_little_shop_transfer
from .services.orders import (
    create_order_from_current_plan,
    get_order_detail,
    list_orders,
    mark_order_cancelled,
    mark_order_ordered,
    mark_order_received,
)
from .services.planning import get_request_list_data, get_shopping_list_data
from .services.reporting import build_operations_history_context
from .services.transfers import (
    cancel_transfer,
    confirm_transfer_by_request,
    get_transfer_request_detail,
    list_recent_transfer_requests,
)


app = Flask(
    __name__,
    template_folder=str(os.path.join(os.path.dirname(__file__), "..", "..", "templates")),
)
app.config["SECRET_KEY"] = os.environ.get("STOCK_SECRET_KEY", "dev-secret-change-me")
app.register_blueprint(api)
_run_lock = threading.Lock()


@app.before_request
def load_request_user():
    g.current_user = load_authenticated_user(session.get("user_id")) or AnonymousUser()


@app.context_processor
def inject_nav_state():
    current_user = get_current_user()
    return {
        "active_page": active_page_for_path(request.path),
        "current_user": current_user,
        "is_manager": current_user.is_authenticated and getattr(current_user, "role", "") in {"manager", "admin"},
        "is_admin": current_user.is_authenticated and getattr(current_user, "role", "") == "admin",
    }


def _bootstrap() -> None:
    init_db()
    seed_locations()


def _dashboard_context() -> dict:
    status_date = request.args.get("date", today_iso()).strip() or today_iso()
    context = get_dashboard_summary()
    context["sync_readiness"] = get_daily_sync_readiness(status_date)
    context["count_status"] = get_count_status_overview(status_date)
    return context


def _safe_redirect_target(target: str | None) -> str:
    if not target:
        return url_for("index")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return url_for("index")
    return target


@app.get("/login")
def login():
    if get_current_user().is_authenticated:
        return redirect(url_for("index"))
    return render_template(
        "login.html",
        next_url=_safe_redirect_target(request.args.get("next")),
        error_message=request.args.get("error", "").strip(),
    )


@app.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = _safe_redirect_target(request.form.get("next"))

    try:
        user = authenticate_user(username, password)
    except ValueError as exc:
        return render_template("login.html", next_url=next_url, error_message=str(exc)), 400

    if user is None:
        return render_template(
            "login.html",
            next_url=next_url,
            error_message="Username or password was incorrect.",
        ), 401

    login_user(user)
    return redirect(next_url)


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("dashboard.html", **_dashboard_context())


@app.get("/items")
@role_required("manager", "admin")
def items():
    search = request.args.get("q", "").strip().lower()
    rows = list_items()
    if search:
        rows = [
            row for row in rows
            if search in str(row["name"]).lower()
            or search in str(row["category"]).lower()
            or search in str(row["suppliers"]).lower()
        ]
    return render_template("items.html", search_query=request.args.get("q", "").strip(), **build_items_page_context(rows))


@app.get("/counts")
@login_required
def counts():
    return redirect(url_for("keele_count", date=request.args.get("date", "").strip() or None))


def _render_count_screen(location: str, *, count_date: str | None = None, success_message: str = "", error_message: str = "", form_values: dict[int, str] | None = None, status_code: int = 200):
    count_data = build_count_data(location, count_date)
    hydrated_rows = []
    value_lookup = form_values or {}
    for row in count_data["rows"]:
        hydrated = dict(row)
        if row["id"] in value_lookup:
            hydrated["counted_qty"] = value_lookup[row["id"]]
        hydrated_rows.append(hydrated)
    return (
        render_template(
            "count_form.html",
            **build_count_page_context(
                location=count_data["location"],
                count_date=count_data["count_date"],
                count_rows=hydrated_rows,
                count_id=count_data["count_id"],
                is_reconciled=count_data["is_reconciled"],
                success_message=success_message,
                error_message=error_message,
            ),
        ),
        status_code,
    )


@app.get("/counts/keele")
@login_required
def keele_count():
    success_message = "Count saved successfully." if request.args.get("saved") == "1" else ""
    return _render_count_screen("Keele", count_date=request.args.get("date"), success_message=success_message)[0]


@app.get("/counts/little-shop")
@login_required
def little_shop_count():
    success_message = ""
    if request.args.get("saved") == "1":
        success_message = "Count saved successfully."
    return _render_count_screen("Little Shop", count_date=request.args.get("date"), success_message=success_message)[0]


@app.post("/counts")
@login_required
def save_count():
    location = request.form.get("location", "Keele").strip() or "Keele"
    count_date = request.form.get("count_date", today_iso()).strip() or today_iso()

    count_values: dict[int, str] = {}
    for key, value in request.form.items():
        if not key.startswith("qty_"):
            continue
        try:
            item_id = int(key.removeprefix("qty_"))
        except ValueError:
            continue
        count_values[item_id] = value

    route_name = "keele_count" if location == "Keele" else "little_shop_count"
    try:
        save_count_data(location, count_date, count_values)
        return redirect(url_for(route_name, date=count_date, saved="1"))
    except ValueError as exc:
        return _render_count_screen(
            location,
            count_date=count_date,
            error_message=str(exc),
            form_values=count_values,
            status_code=400,
        )


@app.get("/shopping-lists")
@role_required("manager", "admin")
def shopping_lists():
    shopping_data = get_shopping_list_data(request.args.get("date"))
    return render_template(
        "shopping_list.html",
        **build_shopping_list_page_context(
            shopping_data["location"],
            shopping_data["count_date"],
            shopping_data["rows"],
        ),
    )


@app.get("/request-lists")
@login_required
def request_lists():
    request_data = get_request_list_data(request.args.get("date"))
    request_id = request.args.get("request_id", type=int)
    moved_qty = request.args.get("moved_qty", type=float)
    moved_lines = request.args.get("moved_lines", type=int)
    error_message = request.args.get("error", "").strip()
    success_message = ""
    if moved_qty is not None and moved_lines is not None:
        success_message = (
            f"Confirmed transfer to Little Shop. Moved {moved_qty:.2f} units across {moved_lines} item"
            f"{'' if moved_lines == 1 else 's'}."
        )
    request_value = None
    if request_id is not None:
        try:
            request_value = get_request_list_value(request_id)
        except ValueError as exc:
            return render_template(
                "run_day_result.html",
                title="Request not found",
                status="error",
                message=str(exc),
                output="",
                run_date=request_data["count_date"],
            ), 404
    return render_template(
        "request_list.html",
        **build_request_list_page_context(
            request_data["location"],
            request_data["count_date"],
            request_data["rows"],
            request_data["source_location"],
            total_request_value=request_data["total_request_value"],
            request_id=request_id,
            request_value=request_value,
            success_message=success_message,
            error_message=error_message,
        ),
    )


@app.post("/request-lists/confirm")
@login_required
def confirm_request_list():
    count_date = request.form.get("count_date", today_iso()).strip() or today_iso()
    note = request.form.get("note", "").strip()
    try:
        result = confirm_little_shop_transfer(count_date, note)
        return redirect(
            url_for(
                "request_lists",
                date=count_date,
                request_id=result["request_id"],
                moved_qty=f"{result['moved_qty']:.2f}",
                moved_lines=result["moved_lines"],
            )
        )
    except ValueError as exc:
        return redirect(url_for("request_lists", date=count_date, error=str(exc)))


@app.get("/transfers")
@role_required("manager", "admin")
def transfers():
    return render_template("transfers.html", transfer_rows=list_recent_transfer_requests())


@app.get("/transfers/<int:request_id>")
@role_required("manager", "admin")
def transfer_detail(request_id: int):
    try:
        detail = get_transfer_request_detail(request_id)
    except ValueError as exc:
        return render_template(
            "run_day_result.html",
            title="Transfer request not found",
            status="error",
            message=str(exc),
            output="",
            run_date=today_iso(),
        ), 404
    return render_template("transfer_detail.html", **detail)


@app.post("/transfers/<int:request_id>/confirm")
@role_required("manager", "admin")
def transfer_confirm(request_id: int):
    note = request.form.get("note", "").strip()
    try:
        result = confirm_transfer_by_request(request_id, note)
        return redirect(url_for("transfer_detail", request_id=request_id, moved="1", moved_qty=f"{result['moved_qty']:.2f}"))
    except ValueError as exc:
        return redirect(url_for("transfer_detail", request_id=request_id, error=str(exc)))


@app.post("/transfers/<int:request_id>/cancel")
@role_required("manager", "admin")
def transfer_cancel(request_id: int):
    try:
        cancel_transfer(request_id)
        return redirect(url_for("transfer_detail", request_id=request_id, cancelled="1"))
    except ValueError as exc:
        return redirect(url_for("transfer_detail", request_id=request_id, error=str(exc)))


@app.get("/finance")
@role_required("manager", "admin")
def finance():
    finance_context = build_finance_dashboard_context(request.args.get("month"))
    return render_template("finance.html", **finance_context)


@app.get("/deliveries/new")
@role_required("manager", "admin")
def new_delivery():
    delivery_data = build_invoice_hub_data()
    return render_template(
        "delivery_form.html",
        ordered_orders=delivery_data["ordered_orders"],
        draft_orders=delivery_data["draft_orders"],
        recent_invoices=delivery_data["recent_invoices"],
        ordered_count=delivery_data["ordered_count"],
        draft_count=delivery_data["draft_count"],
        invoice_count=delivery_data["invoice_count"],
        delivery_date=today_iso(),
        location="Keele",
        info_message=request.args.get("info", "").strip(),
        error_message=request.args.get("error", "").strip(),
    )


@app.post("/deliveries")
@role_required("manager", "admin")
def create_delivery():
    try:
        invoice_id = save_supplier_invoice_upload(
            request.form.get("order_id", ""),
            request.form.get("invoice_reference", ""),
            request.form.get("supplier_name", ""),
            request.form.get("note", ""),
            request.files.get("invoice_file"),
        )
        return redirect(url_for("invoice_detail", invoice_id=invoice_id, uploaded="1"))
    except ValueError as exc:
        return redirect(url_for("new_delivery", error=str(exc)))


@app.get("/invoices/<int:invoice_id>")
@role_required("manager", "admin")
def invoice_detail(invoice_id: int):
    try:
        context = get_invoice_detail(invoice_id)
    except ValueError as exc:
        return render_template(
            "run_day_result.html",
            title="Invoice not found",
            status="error",
            message=str(exc),
            output="",
            run_date=today_iso(),
        ), 404
    return render_template("invoice_detail.html", **context)


@app.post("/invoices/<int:invoice_id>/review")
@role_required("manager", "admin")
def invoice_review(invoice_id: int):
    try:
        review_invoice(
            invoice_id,
            invoice_reference=request.form.get("invoice_reference", ""),
            note=request.form.get("note", ""),
        )
        return redirect(url_for("invoice_detail", invoice_id=invoice_id, reviewed="1"))
    except ValueError as exc:
        return redirect(url_for("invoice_detail", invoice_id=invoice_id, error=str(exc)))


@app.get("/invoices/<int:invoice_id>/file")
@role_required("manager", "admin")
def invoice_file(invoice_id: int):
    try:
        context = get_invoice_detail(invoice_id)
        file_path = get_invoice_file_path(str(context["invoice"]["stored_filename"]))
    except ValueError as exc:
        return render_template(
            "run_day_result.html",
            title="Invoice file not found",
            status="error",
            message=str(exc),
            output="",
            run_date=today_iso(),
        ), 404
    return send_file(file_path, download_name=str(context["invoice"]["original_filename"]))


def _item_form_values(form_data: dict | None = None) -> dict:
    source = form_data or {}
    return {
        "name": source.get("name", ""),
        "category": source.get("category", ""),
        "base_unit": source.get("base_unit", ""),
        "cost_per_unit": source.get("cost_per_unit", ""),
        "supplier": source.get("supplier", ""),
        "ref": source.get("ref", ""),
        "par_keele": source.get("par_keele", ""),
        "par_little_shop": source.get("par_little_shop", ""),
    }


@app.get("/items/new")
@role_required("manager", "admin")
def new_item():
    return render_template(
        "item_form.html",
        form_title="Add item",
        form_intro="Start with a simple item record. We can extend this page later with par levels and extra actions.",
        submit_label="Create item",
        form_action=url_for("create_item"),
        item_values=_item_form_values(),
        error_message="",
        base_units=get_base_units(),
        item_id=None,
    )


@app.post("/items")
@role_required("manager", "admin")
def create_item():
    form_values = _item_form_values(request.form)
    try:
        save_item_record(
            item_id=None,
            name=form_values["name"],
            category=form_values["category"],
            base_unit=form_values["base_unit"],
            supplier=form_values["supplier"],
            ref=form_values["ref"],
            cost_per_unit=form_values["cost_per_unit"],
            par_keele=form_values["par_keele"],
            par_little_shop=form_values["par_little_shop"],
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
                base_units=get_base_units(),
                item_id=None,
            ),
            400,
        )


@app.get("/items/<int:item_id>/edit")
@role_required("manager", "admin")
def edit_item(item_id: int):
    try:
        item_values = get_item(item_id)
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
        base_units=get_base_units(),
        item_id=item_id,
    )


@app.post("/items/<int:item_id>")
@role_required("manager", "admin")
def update_item(item_id: int):
    form_values = _item_form_values(request.form)
    try:
        save_item_record(
            item_id=item_id,
            name=form_values["name"],
            category=form_values["category"],
            base_unit=form_values["base_unit"],
            supplier=form_values["supplier"],
            ref=form_values["ref"],
            cost_per_unit=form_values["cost_per_unit"],
            par_keele=form_values["par_keele"],
            par_little_shop=form_values["par_little_shop"],
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
                base_units=get_base_units(),
                item_id=item_id,
            ),
            400,
        )


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200


@app.get("/supplier-orders")
@role_required("manager", "admin")
def supplier_orders():
    status = request.args.get("status", "").strip() or None
    return render_template(
        "supplier_orders.html",
        order_rows=list_orders(status=status),
        selected_status=status or "",
        today=today_iso(),
    )


@app.post("/supplier-orders")
@role_required("manager", "admin")
def supplier_orders_create():
    order_date = request.form.get("order_date", today_iso()).strip() or today_iso()
    note = request.form.get("note", "").strip()
    try:
        order_id = create_order_from_current_plan(order_date, note)
        return redirect(url_for("supplier_order_detail", order_id=order_id, created="1"))
    except ValueError as exc:
        return redirect(url_for("supplier_orders", error=str(exc)))


@app.get("/supplier-orders/<int:order_id>")
@role_required("manager", "admin")
def supplier_order_detail(order_id: int):
    try:
        detail = get_order_detail(order_id)
    except ValueError as exc:
        return render_template(
            "run_day_result.html",
            title="Supplier order not found",
            status="error",
            message=str(exc),
            output="",
            run_date=today_iso(),
        ), 404
    return render_template("supplier_order_detail.html", **detail)


@app.post("/supplier-orders/<int:order_id>/ordered")
@role_required("manager", "admin")
def supplier_order_mark_ordered(order_id: int):
    try:
        mark_order_ordered(order_id)
        return redirect(url_for("supplier_order_detail", order_id=order_id, ordered="1"))
    except ValueError as exc:
        return redirect(url_for("supplier_order_detail", order_id=order_id, error=str(exc)))


@app.post("/supplier-orders/<int:order_id>/received")
@role_required("manager", "admin")
def supplier_order_mark_received(order_id: int):
    note = request.form.get("note", "").strip()
    try:
        result = mark_order_received(order_id, note)
        return redirect(url_for("supplier_order_detail", order_id=order_id, received="1", received_qty=f"{result['received_qty']:.2f}"))
    except ValueError as exc:
        return redirect(url_for("supplier_order_detail", order_id=order_id, error=str(exc)))


@app.post("/supplier-orders/<int:order_id>/cancel")
@role_required("manager", "admin")
def supplier_order_mark_cancelled(order_id: int):
    try:
        mark_order_cancelled(order_id)
        return redirect(url_for("supplier_order_detail", order_id=order_id, cancelled="1"))
    except ValueError as exc:
        return redirect(url_for("supplier_order_detail", order_id=order_id, error=str(exc)))


@app.get("/history")
@role_required("manager", "admin")
def operations_history():
    return render_template("history.html", **build_operations_history_context())


@app.get("/admin/users")
@role_required("admin")
def admin_users():
    return render_template(
        "admin_users.html",
        user_rows=list_user_accounts(),
        valid_roles=VALID_USER_ROLES,
        success_message=request.args.get("success", "").strip(),
        error_message=request.args.get("error", "").strip(),
    )


@app.post("/admin/users")
@role_required("admin")
def admin_users_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "staff").strip()
    try:
        create_user_record(username, password, role)
        return redirect(url_for("admin_users", success="User created."))
    except ValueError as exc:
        return redirect(url_for("admin_users", error=str(exc)))


@app.post("/admin/users/<int:user_id>/role")
@role_required("admin")
def admin_users_role(user_id: int):
    role = request.form.get("role", "staff").strip()
    try:
        update_user_role_record(user_id, role)
        return redirect(url_for("admin_users", success="Role updated."))
    except ValueError as exc:
        return redirect(url_for("admin_users", error=str(exc)))


@app.post("/admin/users/<int:user_id>/active")
@role_required("admin")
def admin_users_active(user_id: int):
    is_active = request.form.get("is_active", "1") == "1"
    try:
        update_user_active_record(user_id, is_active)
        return redirect(url_for("admin_users", success="Account updated."))
    except ValueError as exc:
        return redirect(url_for("admin_users", error=str(exc)))


@app.post("/admin/users/<int:user_id>/password")
@role_required("admin")
def admin_users_password(user_id: int):
    password = request.form.get("password", "")
    try:
        reset_user_password(user_id, password)
        return redirect(url_for("admin_users", success="Password reset."))
    except ValueError as exc:
        return redirect(url_for("admin_users", error=str(exc)))


@app.post("/run-day")
@login_required
def run_day():
    run_date = request.form.get("run_date", today_iso()).strip() or today_iso()

    sync_readiness = get_daily_sync_readiness(run_date)
    if not sync_readiness["is_ready"]:
        missing_locations = ", ".join(sync_readiness["missing_locations"])
        return (
            render_template(
                "run_day_result.html",
                title="Counts incomplete",
                status="warning",
                message=(
                    f"Daily sync for {run_date} is blocked until saved stock counts exist for: "
                    f"{missing_locations}."
                ),
                output="Open the Counts page, save each location for that date, then run the sync again.",
                run_date=run_date,
            ),
            400,
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
            run_daily_workflow(run_date)
        raw_output = output.getvalue() or "Run completed."
        save_run_history("run-day", run_date, "SUCCESS", raw_output)
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
        save_run_history("run-day", run_date, "FAILED", raw_output)
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


@app.errorhandler(401)
def unauthorized_page(_exc):
    return redirect(url_for("login", next=request.path))


@app.errorhandler(403)
def forbidden_page(_exc):
    return (
        render_template(
            "run_day_result.html",
            title="Access denied",
            status="error",
            message="Your account does not have permission to open that page.",
            output="",
            run_date=today_iso(),
        ),
        403,
    )


def main() -> None:
    _bootstrap()
    port = int(os.environ.get("PORT", "8080"))
    from waitress import serve

    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
