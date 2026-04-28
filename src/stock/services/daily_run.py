from collections.abc import Callable

from ..db import (
    export_pick_list_to_sheet,
    export_supplier_order_to_sheet,
    generate_keele_pick_list,
    generate_request_from_par,
    generate_supplier_order,
    import_count_from_sheet,
    reconcile_count,
)

Writer = Callable[[str], None]


def run_daily_for_location(location: str, date: str, writer: Writer = print) -> None:
    writer("\n==============================")
    writer(f"RUNNING DAY FOR: {location}")
    writer("==============================")

    writer("\nImporting count...")
    count_id = import_count_from_sheet(location, date)
    writer(f"   -> Count ID: {count_id}")

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
        export_pick_list_to_sheet(pick_rows)

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
        export_supplier_order_to_sheet(order_rows)


def run_day(date: str, writer: Writer = print) -> None:
    run_daily_for_location("Little Shop", date, writer=writer)
    run_daily_for_location("Keele", date, writer=writer)
    writer("\nFULL DAY COMPLETE\n")
