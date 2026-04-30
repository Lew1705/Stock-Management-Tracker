from collections.abc import Callable

from ..db import (
    export_pick_list_to_sheet,
    export_supplier_order_to_sheet,
    generate_keele_pick_list,
    generate_request_from_par,
    generate_supplier_order,
    get_saved_count_summary,
    reconcile_count,
)

Writer = Callable[[str], None]


def _saved_count_id(location: str, date: str) -> tuple[int, bool]:
    summary = get_saved_count_summary(location, date)
    count_id = summary["count_id"]
    if count_id is None or int(summary["line_count"]) <= 0:
        raise ValueError(f"No saved web count exists for {location} on {date}.")
    return int(count_id), bool(summary["is_reconciled"])


def _try_google_export(label: str, exporter: Callable, rows, writer: Writer) -> None:
    try:
        exporter(rows)
    except FileNotFoundError as exc:
        writer(f"   -> Skipped Google Sheets export: {exc}")
    else:
        writer(f"   -> {label} exported")


def run_daily_for_location(location: str, date: str, writer: Writer = print) -> None:
    writer("\n==============================")
    writer(f"RUNNING DAY FOR: {location}")
    writer("==============================")

    writer("\nUsing saved web count...")
    count_id, is_reconciled = _saved_count_id(location, date)
    writer(f"   -> Count ID: {count_id}")

    if is_reconciled:
        writer("\nReconciling...")
        writer("   -> Count was already reconciled")
    else:
        writer("\nReconciling...")
        report = reconcile_count(count_id)
        total_variance = sum(abs(row["diff"]) for row in report)
        writer(f"   -> Total variance: {round(total_variance, 2)}")

    if location == "Little Shop":
        writer("\nREQUEST:")
        request_rows = generate_request_from_par(location)
        if not request_rows:
            writer(" - No items needed")
        else:
            for row in request_rows:
                writer(f" - {row['name']}: {round(row['request_qty'], 2)}")

        writer("\nPICK FROM KEELE:")
        pick_rows = generate_keele_pick_list(location)
        if not pick_rows:
            writer(" - Nothing to pick")
        else:
            for row in pick_rows:
                writer(f" - {row['name']}: {round(row['pick_qty'], 2)}")

        writer("\nExporting pick list...")
        _try_google_export("Pick list", export_pick_list_to_sheet, pick_rows, writer)

    if location == "Keele":
        writer("\nSUPPLIER ORDER:")
        order_rows = generate_supplier_order()
        order_candidates = [row for row in order_rows if row["supplier_order_qty"] > 0]
        if not order_candidates:
            writer(" - No supplier order needed")
        else:
            for row in order_candidates:
                writer(f" - {row['name']}: {round(row['supplier_order_qty'], 2)}")

        writer("\nExporting supplier order...")
        _try_google_export("Supplier order", export_supplier_order_to_sheet, order_rows, writer)


def run_day(date: str, writer: Writer = print) -> None:
    run_daily_for_location("Little Shop", date, writer=writer)
    run_daily_for_location("Keele", date, writer=writer)
    writer("\nFULL DAY COMPLETE\n")
