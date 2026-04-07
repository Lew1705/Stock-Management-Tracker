import csv
from pathlib import Path

import argparse

from .db import (
    init_db,
    seed_locations,
    insert_item,
    receive_into_keele,
    transfer_keele_to_little,
    waste,
    stock_on_hand,
    create_count,
    add_count_line,
    usage_between_counts,
    current_stock,
    get_items,
    list_counts,
    get_or_create_count,
    usage_since_last_count,
    combined_order_sheet,
    set_par_level,
    reconcile_count,
    create_transfer_request,
    add_transfer_request_line,
    list_transfer_requests,
    fulfill_transfer_request,
    create_request_from_par,
    count_line_count,
    get_request_lines,
    get_item_by_id,
    add_count_line_by_item_id,
    get_conn,
    import_items_and_par_levels,
    list_items,
    generate_request_from_par,
    export_request_to_csv,
    generate_keele_pick_list,
    export_pick_list_to_csv,
    generate_supplier_order,
    export_supplier_order_to_csv,
    import_count_from_sheet,
    export_pick_list_to_sheet,
    export_supplier_order_to_sheet,
    export_count_to_sheet
)


def run_daily_for_location(location: str, date: str):
    print(f"\n==============================")
    print(f"🚀 RUNNING DAY FOR: {location}")
    print(f"==============================")

    # Import count
    print("\n📥 Importing count...")
    count_id = import_count_from_sheet(location, date)
    print(f"   → Count ID: {count_id}")

    # Reconcile
    print("\n⚖️ Reconciling...")
    report = reconcile_count(count_id)
    total_variance = sum(abs(r["diff"]) for r in report)
    print(f"   → Total variance: {round(total_variance, 2)}")

    # LITTLE SHOP LOGIC
    if location == "Little Shop":

        print("\n📦 REQUEST:")
        request_rows = generate_request_from_par(location)

        if not request_rows:
            print(" - No items needed")
        else:
            for r in request_rows:
                print(f" - {r['name']}: {round(r['request_qty'],2)}")

        print("\n🚚 PICK FROM KEELE:")
        pick_rows = generate_keele_pick_list(location)

        if not pick_rows:
            print(" - Nothing to pick")
        else:
            for r in pick_rows:
                print(f" - {r['name']}: {round(r['pick_qty'],2)}")

        print("\n📤 Exporting pick list...")
        export_pick_list_to_sheet(pick_rows)

    # KEELE LOGIC
    if location == "Keele":

        print("\n🛒 SUPPLIER ORDER:")
        order_rows = generate_supplier_order()

        has_orders = any(r["supplier_order_qty"] > 0 for r in order_rows)

        if not has_orders:
            print(" - No supplier order needed")
        else:
            for r in order_rows:
                if r["supplier_order_qty"] > 0:
                    print(f" - {r['name']}: {round(r['supplier_order_qty'],2)}")

        print("\n📤 Exporting supplier order...")
        export_supplier_order_to_sheet(order_rows)


# --- Helper: pretty print stock for one item in both locations ---
def print_item_stock(item: str) -> None:
    k = stock_on_hand("Keele", item)
    l = stock_on_hand("Little Shop", item)
    print(f"{item}")
    print(f"  Keele:       {k}")
    print(f"  Little Shop: {l}")


def cmd_run_day(args):
    init_db()

    date = args.date

    # Run Little Shop FIRST
    run_daily_for_location("Little Shop", date)

    # Then Keele
    run_daily_for_location("Keele", date)

    print("\n✅ FULL DAY COMPLETE\n")


def cmd_init(_args: argparse.Namespace) -> None:
    init_db()
    seed_locations()
    print("Database initialised and locations seeded.")


def cmd_add_item(args: argparse.Namespace) -> None:
    insert_item(args.name, args.category, args.base_unit)
    print(f"Item added (or already exists): {args.name}")


def cmd_receive(args: argparse.Namespace) -> None:
    init_db()
    receive_into_keele(args.item, args.qty, args.note or "")
    print("Recorded delivery into Keele.")
    print_item_stock(args.item)


def cmd_transfer(args: argparse.Namespace) -> None:
    init_db()
    transfer_keele_to_little(args.item, args.qty, args.note or "")
    print("Recorded transfer Keele -> Little Shop.")
    print_item_stock(args.item)


def cmd_waste(args: argparse.Namespace) -> None:
    init_db()
    waste(args.location, args.item, args.qty, args.note or "")
    print("Recorded waste.")
    print_item_stock(args.item)


def cmd_stock(args):
    qty = current_stock(args.location, args.item)
    print(f"{args.item} @ {args.location}: {round(qty,2)}")


def cmd_count_start(args: argparse.Namespace) -> None:
    init_db()
    count_id = create_count(args.location, args.date)
    print(f"Created count: {count_id} ({args.location}, count date {args.date})")


def cmd_count_add(args: argparse.Namespace) -> None:
    init_db()

    # Option 1: user provided a count id (old way)
    if args.count_id is not None:
        count_id = args.count_id

    # Option 2: user provided location + week ending (new way)
    else:
        if not args.location or not args.date:
            raise SystemExit("count-add needs either --count-id OR (--location AND --date)")
        count_id = get_or_create_count(args.location, args.date)

    add_count_line(count_id, args.item, args.counted)
    print(f"Added count line to count {count_id}: {args.item} = {args.counted}")



def cmd_usage(args: argparse.Namespace) -> None:
    init_db()
    used = usage_between_counts(args.location, args.item, args.open_count_id, args.close_count_id)
    print(f"Usage for {args.item} at {args.location} between counts {args.open_count_id} -> {args.close_count_id}: {used}")

def cmd_export_count_sheet(args):
    export_count_to_sheet(args.location)

def cmd_import_count_sheet(args):
    count_id = import_count_from_sheet(args.location, args.date)
    print(f"Imported count {count_id}")


def cmd_import_count_sheet(args):
    from .db import import_count_from_sheet
    import_count_from_sheet(args.location, args.date)

def cmd_order_sheet(args: argparse.Namespace) -> None:
    init_db()
    rows = combined_order_sheet()

    print("Combined Order Sheet (Keele + Little Shop)")
    print("Item | Keele Short | Little Short | Total | Unit")
    print("-----|--------------|--------------|-------|-----")

    for r in rows:
        if (not args.show_zero) and (r["total_shortfall"] == 0):
            continue

        print(
            f"{r['item']} | "
            f"{r['keele_shortfall']} | "
            f"{r['little_shortfall']} | "
            f"{r['total_shortfall']} | "
            f"{r['unit']}"
        )



def cmd_count_list(args: argparse.Namespace) -> None:
    init_db()
    rows = list_counts(location=args.location, limit=args.limit)

    if not rows:
        print("No stock counts found yet.")
        return

    print("ID | Location | Count Date | Created")
    print("---|----------|------------|--------")
    for r in rows:
        print(f"{r['id']} | {r['location']} | {r['count_date']} | {r['created_at']}")

def cmd_usage_since(args: argparse.Namespace) -> None:
    init_db()

    data = usage_since_last_count(args.location, item=args.item)

    # Single item output
    if args.item:
        print(
            f"Usage for {data['item']} at {args.location} "
            f"between counts {data['open_count_id']} -> {data['close_count_id']}: {data['used']}"
        )
        return

    # All items output
    print(
        f"Usage at {args.location} between counts "
        f"{data['open_count_id']} -> {data['close_count_id']}"
    )
    print("Item | Used | Unit")
    print("-----|------|-----")

    for r in data["rows"]:
        if (not args.show_zero) and (r["used"] == 0):
            continue
        print(f"{r['item']} | {r['used']} | {r['base_unit']}")

def cmd_req_rebuild_par(args: argparse.Namespace) -> None:
    init_db()
    req_id = create_request_from_par(
        to_location=args.location,
        request_date=args.date,
        note="Auto request from PAR (rebuilt)"
    )
    print(f"Rebuilt transfer request {req_id} (Keele -> {args.location}) for {args.date}")

def cmd_set_par(args: argparse.Namespace) -> None:
    init_db()
    set_par_level(args.location, args.item, args.qty)
    print(f"Set par level: {args.location} / {args.item} = {args.qty}")

def cmd_count_reconcile(args: argparse.Namespace) -> None:
    init_db()
    report = reconcile_count(args.count_id, note=args.note or "")

    print(f"Reconciled count {args.count_id}")
    print("Item | Expected | Counted | Diff | Unit")
    print("-----|----------|---------|------|-----")

    any_diff = False
    for r in report:
        if abs(r["diff"]) > 1e-9:
            any_diff = True
        print(f"{r['item']} | {r['expected']} | {r['counted']} | {r['diff']} | {r['unit']}")

    if not any_diff:
        print("No variances found. No adjustments were created.")
def cmd_req_create(args: argparse.Namespace) -> None:
    init_db()
    req_id = create_transfer_request("Keele", "Little Shop", args.date, args.note or "")
    print(f"Created transfer request {req_id} (Keele -> Little Shop) for {args.date}")

def cmd_req_add(args: argparse.Namespace) -> None:
    init_db()
    add_transfer_request_line(args.request_id, args.item, args.qty)
    print(f"Request {args.request_id}: set {args.item} requested qty to {args.qty}")

def cmd_req_list(args: argparse.Namespace) -> None:
    init_db()
    rows = list_transfer_requests(status=args.status, limit=args.limit)
    if not rows:
        print("No requests found.")
        return
    print("ID | From | To | Date | Status | Created | Note")
    print("---|------|----|------|--------|--------|-----")
    for r in rows:
        print(f"{r['id']} | {r['from_location']} | {r['to_location']} | {r['request_date']} | {r['status']} | {r['created_at']} | {r['note']}")

def cmd_req_fulfill(args: argparse.Namespace) -> None:
    init_db()
    fulfill_transfer_request(args.request_id, note=args.note or "")
    print(f"Fulfilled outstanding items for request {args.request_id}")

def cmd_req_show(args: argparse.Namespace) -> None:
    init_db()
    lines = get_request_lines(args.request_id)

    if not lines:
        print("No lines found for this request.")
        return

    print(f"Request {args.request_id} lines")
    print("Item | Requested | Fulfilled | Outstanding | Unit")
    print("-----|----------|-----------|------------|-----")

    for ln in lines:
        print(
            f"{ln['item']} | {ln['requested']} | {ln['fulfilled']} | {ln['outstanding']} | {ln['unit']}"
        )


def cmd_close_day(args: argparse.Namespace) -> None:
    init_db()

    # Ensure today's count exists
    count_id = get_or_create_count(args.location, args.date)
    print(f"Close-day: using count {count_id} for {args.location} on {args.date}")

    # Require at least 1 count line
    n_lines = count_line_count(count_id)
    if n_lines == 0:
        print("This count has 0 lines. Enter count lines first, then run close-day again.")
        print(f"Tip: python -m stock.cli count-add --count-id {count_id} --item \"<ITEM>\" --counted <QTY>")
        return

    # Reconcile (locks count). If already reconciled, stop.
    if args.reconcile:
        try:
            report = reconcile_count(count_id, note=args.note or f"Close-day {args.date}")
        except ValueError as e:
            print(str(e))
            return

        diffs = [r for r in report if abs(r["diff"]) > 1e-9]
        print(f"Reconciled and locked count {count_id}. Variances: {len(diffs)}")

        if diffs:
            print("Item | Expected | Counted | Diff | Unit")
            print("-----|----------|---------|------|-----")
            for r in diffs:
                print(f"{r['item']} | {r['expected']} | {r['counted']} | {r['diff']} | {r['unit']}")
        else:
            print("No variances found.")

    # Little Shop: auto-create transfer request from PAR shortfalls
    if args.location == "Little Shop" and args.make_request:
        req_id = create_request_from_par("Little Shop", args.date, note=args.request_note or "Auto request from PAR")
        print(f"\nCreated transfer request {req_id} (Keele -> Little Shop)")

        lines = get_request_lines(req_id)
        if not lines:
            print("Request has 0 lines (no shortfalls).")
        else:
            print("Item | Requested | Unit")
            print("-----|-----------|-----")
            for ln in lines:
                print(f"{ln['item']} | {ln['requested']} | {ln['unit']}")

        print(f"\nNext at Keele: python -m stock.cli req-fulfill --request-id {req_id}")

    # Keele: show supplier ordering sheet (includes outstanding Little Shop requests)
    if args.location == "Keele" and args.show_keele_order:
        rows = keele_supplier_order_sheet(include_outstanding_requests=True)
        print("\nKeele Supplier Order Sheet (includes outstanding Little Shop requests)")
        print("Item | Keele Short | Outstanding to Little | Suggested Order | Unit")
        print("-----|------------|------------------------|----------------|-----")
        for r in rows:
            if (not args.show_zero) and r["suggested_order"] <= 1e-9:
                continue
            print(
                f"{r['item']} | {r['keele_short']} | {r['outstanding_to_little']} | "
                f"{r['suggested_order']} | {r['unit']}"
            )

def cmd_count_show(args: argparse.Namespace) -> None:
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT sc.id, l.name AS location, sc.count_date, sc.created_at
            FROM stock_counts sc
            JOIN locations l ON l.id = sc.location_id
            WHERE sc.id = ?;
            """,
            (args.id,),
        ).fetchone()

        if row is None:
            raise SystemExit(f"No stock count found with id {args.id}")

        print(f"Count {row['id']} | {row['location']} | {row['count_date']} | {row['created_at']}")
        print("Item ID | Item | Qty (base)")
        print("--------|------|----------")

        lines = conn.execute(
            """
            SELECT i.id AS item_id, i.name, scl.counted_qty_base
            FROM stock_count_lines scl
            JOIN items i ON i.id = scl.item_id
            WHERE scl.count_id = ?
            ORDER BY i.name;
            """,
            (args.id,),
        ).fetchall()

        if not lines:
            print("(no lines)")
            return

        for ln in lines:
            print(f"{ln['item_id']} | {ln['name']} | {ln['counted_qty_base']}")

def cmd_keele_order(args: argparse.Namespace) -> None:
    init_db()
    rows = keele_supplier_order_sheet(include_outstanding_requests=(not args.ignore_requests))

    title = (
        "Keele Supplier Order Sheet (includes outstanding Little Shop requests)"
        if not args.ignore_requests
        else "Keele Supplier Order Sheet (ignoring Little Shop requests)"
    )
    print(title)
    print("Item | Keele On Hand | Keele PAR | Keele Short | Outstanding to Little | Suggested Order | Unit")
    print("-----|--------------|----------|------------|------------------------|----------------|-----")

    # Build filtered list once so print + export match
    export_rows = []
    for r in rows:
        if (not args.show_zero) and r["suggested_order"] <= 1e-9:
            continue
        export_rows.append(r)
        print(
            f"{r['item']} | {r['keele_on_hand']} | {r['keele_par']} | {r['keele_short']} | "
            f"{r['outstanding_to_little']} | {r['suggested_order']} | {r['unit']}"
        )

    # Optional CSV export
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "item",
                "keele_on_hand",
                "keele_par",
                "keele_short",
                "outstanding_to_little",
                "suggested_order",
                "unit",
            ])
            for r in export_rows:
                w.writerow([
                    r["item"],
                    r["keele_on_hand"],
                    r["keele_par"],
                    r["keele_short"],
                    r["outstanding_to_little"],
                    r["suggested_order"],
                    r["unit"],
                ])

        print(f"Wrote CSV: {out_path}")


def cmd_export_count_template(args: argparse.Namespace) -> None:
    init_db()

    out_path = Path(args.out)

    # Ensure output folder exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        items = conn.execute(
            """
            SELECT id, name, base_unit
            FROM items
            ORDER BY name;
            """
        ).fetchall()

    if not items:
        raise SystemExit("No items found. Add items first (add-item).")

    # Write template CSV
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["item_id", "item_name", "unit", "qty"])
        for it in items:
            writer.writerow([it["id"], it["name"], it["base_unit"], ""])

    print(f"Exported count template for {args.location} to {out_path}")
    print("Tip: In Google Sheets, lock item_id/item_name/unit, and only edit qty.")


def cmd_ingest_counts(args: argparse.Namespace) -> None:
    init_db()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    processed_dir = Path(args.processed) if args.processed else (folder.parent / "processed")
    rejected_dir = Path(args.rejected) if args.rejected else (folder.parent / "rejected")
    processed_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(folder.glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    imported = 0
    skipped = 0
    failed = 0

    for fp in csv_files:
        name = fp.stem  # filename without extension

        # Expect: count_<location>_<YYYY-MM-DD>
        # location can include spaces because we split from the right.
        if not name.startswith("count_"):
            print(f"Skipping (not a count file): {fp.name}")
            skipped += 1
            continue

        try:
            # split from right into 3 parts: "count", "<location>", "<date>"
            prefix, location, date_part = name.rsplit("_", 2)
        except ValueError:
            print(f"Rejected (bad filename format): {fp.name}")
            fp.rename(rejected_dir / fp.name)
            failed += 1
            continue

        if date_part != args.date:
            print(f"Rejected (date mismatch, expected {args.date}): {fp.name}")
            fp.rename(rejected_dir / fp.name)
            failed += 1
            continue

        location = location.strip()

        try:
            fake_args = argparse.Namespace(
                csv_file=str(fp),
                location=location,
                date=args.date,
            )
            cmd_import_count(fake_args)
            imported += 1

            fp.rename(processed_dir / fp.name)
        except SystemExit as e:
            print(f"FAILED import {fp.name}: {e}")
            fp.rename(rejected_dir / fp.name)
            failed += 1
        except Exception as e:
            print(f"FAILED import {fp.name}: {e}")
            fp.rename(rejected_dir / fp.name)
            failed += 1

    print(f"Imported: {imported} | Skipped: {skipped} | Rejected: {failed}")
    print(f"Processed folder: {processed_dir}")
    print(f"Rejected folder: {rejected_dir}")

import csv
from pathlib import Path

def cmd_import_count(args: argparse.Namespace) -> None:
    init_db()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    # 1) Read + validate CSV first (no DB writes yet)
    rows: list[tuple[int, float]] = []  # (item_id, qty)
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"item_id", "qty", "unit"}
        if not reader.fieldnames or not required.issubset({h.strip() for h in reader.fieldnames}):
            raise SystemExit("CSV must have columns: item_id,qty,unit")

        for line_no, row in enumerate(reader, start=2):
            item_id_raw = (row.get("item_id") or "").strip()
            qty_raw = (row.get("qty") or "").strip()
            unit_raw = (row.get("unit") or "").strip()

            if not item_id_raw or not qty_raw or not unit_raw:
                raise SystemExit(f"Line {line_no}: missing item_id/qty/unit")

            try:
                item_id = int(item_id_raw)
            except ValueError:
                raise SystemExit(f"Line {line_no}: item_id must be int (got {item_id_raw})")

            try:
                qty = float(qty_raw)
            except ValueError:
                raise SystemExit(f"Line {line_no}: qty must be numeric (got {qty_raw})")

            if qty < 0:
                raise SystemExit(f"Line {line_no}: qty must be >= 0 (got {qty})")

            item = get_item_by_id(item_id)
            if unit_raw != item["base_unit"]:
                raise SystemExit(
                    f"Line {line_no}: unit mismatch for item_id {item_id} ({item['name']}). "
                    f"CSV unit '{unit_raw}' must match base_unit '{item['base_unit']}'."
                )

            rows.append((item_id, qty))

    # 2) Atomic DB update: create/fetch count, wipe lines, insert fresh
    with get_conn() as conn:
        conn.execute("BEGIN;")
        try:
            count_id = get_or_create_count(args.location, args.date)

            # CSV should fully replace the count for that day
            conn.execute("DELETE FROM stock_count_lines WHERE count_id = ?;", (count_id,))

            inserted = 0
            for item_id, qty in rows:
                conn.execute(
                    """
                    INSERT INTO stock_count_lines (count_id, item_id, counted_qty_base)
                    VALUES (?, ?, ?);
                    """,
                    (count_id, item_id, qty),
                )
                inserted += 1

            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise



def cmd_import_items(args):
    import_items_and_par_levels(args.csv_path)


def cmd_list_items(args):
    list_items()


def cmd_generate_request(args):
    rows = generate_request_from_par(args.location)

    if not rows:
        print(f"No shortfalls found for {args.location}.")
        return

    print(f"Request for {args.location}")
    print("-" * 80)
    print(f"{'ID':>3} | {'Item':<25} | {'On Hand':>10} | {'Par':>10} | {'Request':>10} | Unit")
    print("-" * 80)

    for row in rows:
        print(
            f"{row['item_id']:>3} | "
            f"{row['name']:<25} | "
            f"{row['stock_on_hand']:>10.2f} | "
            f"{row['par_qty']:>10.2f} | "
            f"{row['request_qty']:>10.2f} | "
            f"{row['base_unit']}"
        )

    if args.csv_path:
        export_request_to_csv(rows, args.csv_path)
        print(f"\nRequest exported to {args.csv_path}")

def cmd_keele_pick_list(args):
    rows = generate_keele_pick_list(
        request_location_name=args.location,
        source_location_name="Keele"
    )

    if not rows:
        print(f"No pick list needed for {args.location}.")
        return

    print(f"Pick list for {args.location} from Keele")
    print("-" * 100)
    print(f"{'ID':>3} | {'Item':<25} | {'Request':>10} | {'Keele':>10} | {'Pick':>10} | {'Short':>10} | Unit")
    print("-" * 100)

    for row in rows:
        print(
            f"{row['item_id']:>3} | "
            f"{row['name']:<25} | "
            f"{row['request_qty']:>10.2f} | "
            f"{row['keele_stock']:>10.2f} | "
            f"{row['pick_qty']:>10.2f} | "
            f"{row['short_qty']:>10.2f} | "
            f"{row['base_unit']}"
        )

    if args.csv_path:
        export_pick_list_to_csv(rows, args.csv_path)
        print(f"\nPick list exported to {args.csv_path}")

def cmd_keele_supplier_order(args):
    rows = generate_supplier_order()

    print("\nKEELE SUPPLIER ORDER\n")

    header = (
        f"{'Item':<25}"
        f"{'Unit':<6}"
        f"{'Keele PAR':>10}"
        f"{'Keele Stock':>12}"
        f"{'Pick Qty':>10}"
        f"{'Projected':>12}"
        f"{'Order Qty':>10}"
        f"{'Supplier':>15}"
    )

    print(header)
    print("-" * len(header))

    for r in rows:
        print(
            f"{r['name']:<25}"
            f"{r['base_unit']:<6}"
            f"{r['keele_par_qty']:>10.1f}"
            f"{r['keele_stock']:>12.1f}"
            f"{r['pick_qty']:>10.1f}"
            f"{r['projected_keele_stock']:>12.1f}"
            f"{r['supplier_order_qty']:>10.1f}"
            f"{r['supplier']:>15}"
        )

def cmd_daily_planning(args):
    location = args.location
    date = args.date

    print("\n📥 Importing count from Google Sheet...")
    count_id = import_count_from_sheet(location, date)
    print(f"   → Count ID: {count_id}")

    print("\n⚖️  Reconciling count...")
    report = reconcile_count(count_id)

    total_variance = sum(abs(r["diff"]) for r in report)
    print(f"   → Total variance: {round(total_variance, 2)}")


    print("\n📦 REQUEST (Little Shop needs):")
    request_rows = generate_request_from_par(location)

    for r in request_rows:
        print(f" - {r['name']}: {round(r['request_qty'],2)} {r['base_unit']}")

    print("\n🚚 PICK FROM KEELE:")

    pick_rows = generate_keele_pick_list(location)

    for r in pick_rows:
        print(f" - {r['name']}: pick {round(r['pick_qty'],2)}")

    from collections import defaultdict

    print("\n🛒 SUPPLIER ORDER (Grouped):")

    order_rows = generate_supplier_order()

    grouped = defaultdict(list)

    for r in order_rows:
        supplier = r.get("supplier", "Unknown")
        grouped[supplier].append(r)

    for supplier, items in grouped.items():
        print(f"\nSupplier: {supplier}")
        for r in items:
            print(f" - {r['name']}: {round(r['supplier_order_qty'],2)}")

    print("\n📤 Exporting Pick List to Google Sheets...")
    export_pick_list_to_sheet(pick_rows)

    print("📤 Exporting Supplier Orders to Google Sheets...")
    export_supplier_order_to_sheet(order_rows)

    print("\n✅ DAILY PLANNING COMPLETE\n")



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock", description="Coffee shop stock tracker (rough CLI)")
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("daily-planning", help="Run full daily workflow")
    sp.add_argument("--location", required=True)
    sp.add_argument("--date", required=True)
    sp.set_defaults(func=cmd_daily_planning)

    # init
    sp = sub.add_parser("init", help="Initialise database and seed locations")
    sp.set_defaults(func=cmd_init)

    # add-item
    sp = sub.add_parser("add-item", help="Add an item")
    sp.add_argument("--name", required=True)
    sp.add_argument("--category", required=True)
    sp.add_argument("--base-unit", required=True, choices=["each", "g", "ml"])
    sp.set_defaults(func=cmd_add_item)

    # receive
    sp = sub.add_parser("receive", help="Record a delivery into Keele")
    sp.add_argument("--item", required=True)
    sp.add_argument("--qty", required=True, type=float)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_receive)

    # transfer
    sp = sub.add_parser("transfer", help="Transfer stock Keele -> Little Shop")
    sp.add_argument("--item", required=True)
    sp.add_argument("--qty", required=True, type=float)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_transfer)

    # waste
    sp = sub.add_parser("waste", help="Record waste at a location")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--item", required=True)
    sp.add_argument("--qty", required=True, type=float)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_waste)

    # stock
    sp = sub.add_parser("stock", help="Check stock for an item at a location")
    sp.add_argument("--location", required=True)
    sp.add_argument("--item", required=True)
    sp.set_defaults(func=cmd_stock)

    # dashboard
    sp = sub.add_parser("dashboard", help="Show all items and current stock per shop")
    sp.set_defaults(func=cmd_dashboard)



    # count-start
    sp = sub.add_parser("count-start", help="Create a stock count for a location")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.set_defaults(func=cmd_count_start)

    # count-list
    sp = sub.add_parser("count-list", help="List recent stock counts")
    sp.add_argument("--location", required=False, choices=["Keele", "Little Shop"])
    sp.add_argument("--limit", required=False, type=int, default=25)
    sp.set_defaults(func=cmd_count_list)


   # count-add
    sp = sub.add_parser("count-add", help="Add an item line to a count")
    sp.add_argument("--count-id", required=False, type=int, help="Use an existing count id (old workflow)")
    sp.add_argument("--location", required=False, choices=["Keele", "Little Shop"], help="Used when --count-id is omitted")
    sp.add_argument("--date", required=False, help="YYYY-MM-DD (daily stock take date)")
    sp.add_argument("--item", required=True)
    sp.add_argument("--counted", required=True, type=float)
    sp.set_defaults(func=cmd_count_add)

    # usage-since
    sp = sub.add_parser("usage-since", help="Usage since the last stock count (auto picks last 2 counts)")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--item", required=False, help="Optional: calculate usage for one item only")
    sp.add_argument("--show-zero", action="store_true", help="Include items with zero usage")
    sp.set_defaults(func=cmd_usage_since)

    # count-show
    sp = sub.add_parser("count-show", help="Show lines for a stock count")
    sp.add_argument("--id", required=True, type=int, help="Count ID")
    sp.set_defaults(func=cmd_count_show)

    # usage
    sp = sub.add_parser("usage", help="Calculate usage between two counts")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--item", required=True)
    sp.add_argument("--open-count-id", required=True, type=int)
    sp.add_argument("--close-count-id", required=True, type=int)
    sp.set_defaults(func=cmd_usage)

    # set-par
    sp = sub.add_parser("set-par", help="Set recommended stock (par level) for an item at a location")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--item", required=True)
    sp.add_argument("--qty", required=True, type=float)
    sp.set_defaults(func=cmd_set_par)

    # order-sheet
    sp = sub.add_parser("order-sheet", help="Show combined order shortfalls for both shops")
    sp.add_argument("--show-zero", action="store_true", help="Include items with no shortfall")
    sp.set_defaults(func=cmd_order_sheet)


    # count-reconcile
    sp = sub.add_parser("count-reconcile", help="Reconcile a count: create ADJUSTMENT transactions for any variances")
    sp.add_argument("--count-id", required=True, type=int)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_count_reconcile)

        # req-create
    sp = sub.add_parser("req-create", help="Create a transfer request (Keele -> Little Shop)")
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_req_create)

    # req-add
    sp = sub.add_parser("req-add", help="Add/replace an item line on a transfer request")
    sp.add_argument("--request-id", required=True, type=int)
    sp.add_argument("--item", required=True)
    sp.add_argument("--qty", required=True, type=float)
    sp.set_defaults(func=cmd_req_add)

    # req-list
    sp = sub.add_parser("req-list", help="List transfer requests")
    sp.add_argument("--status", default="OPEN", help="OPEN, PARTIAL, FULFILLED, CANCELLED (or blank for all)")
    sp.add_argument("--limit", type=int, default=25)
    sp.set_defaults(func=cmd_req_list)

    # req-fulfill
    sp = sub.add_parser("req-fulfill", help="Fulfill a transfer request (creates TRANSFER_OUT/IN transactions)")
    sp.add_argument("--request-id", required=True, type=int)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_req_fulfill)


    # keele-order
    sp = sub.add_parser("keele-order", help="Keele supplier order sheet, optionally including outstanding Little Shop requests")
    sp.add_argument("--show-zero", action="store_true", help="Include items with zero suggested order")
    sp.add_argument("--ignore-requests", action="store_true", help="Ignore outstanding Little Shop requests")
    sp.add_argument("--out", required=False, help="Write the order sheet to a CSV file")

    sp.set_defaults(func=cmd_keele_order)

    sp = sub.add_parser("close-day", help="Daily close: require count lines, reconcile+lock, and optionally create request / show order sheet")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.add_argument("--reconcile", action="store_true", help="Reconcile and lock the count")
    sp.add_argument("--note", default="")
    sp.add_argument("--make-request", action="store_true", help="(Little Shop) Create transfer request from PAR shortfalls")
    sp.add_argument("--request-note", default="")
    sp.add_argument("--show-keele-order", action="store_true", help="(Keele) Print supplier order sheet incl. outstanding requests")
    sp.add_argument("--show-zero", action="store_true", help="Include zero lines in Keele order output")
    sp.add_argument("--out", required=False, help="Write the order sheet to a CSV file")
    sp.set_defaults(func=cmd_close_day)

    # req-show
    sp = sub.add_parser("req-show", help="Show lines for a transfer request")
    sp.add_argument("--request-id", required=True, type=int)
    sp.set_defaults(func=cmd_req_show)

    # import-count
    sp = sub.add_parser("import-count", help="Import a daily count CSV")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.add_argument("csv_file", help="Path to CSV (item_id,qty,unit)")
    sp.set_defaults(func=cmd_import_count)

    # export-count-template
    sp = sub.add_parser("export-count-template", help="Export a CSV count template for a location")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--out", required=True, help="Output CSV path")
    sp.set_defaults(func=cmd_export_count_template)

    sp = sub.add_parser("export-sheets", help="Export all Google Sheets (Keele + Little Shop)")
    sp.set_defaults(func=cmd_export_sheets)

    sp = sub.add_parser("req-rebuild-par", help="Rebuild (update) today's transfer request from PAR shortfalls")
    sp.add_argument("--location", required=True, choices=["Little Shop"])
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.set_defaults(func=cmd_req_rebuild_par)
    
    sp = sub.add_parser("list-items", help="List all inventory items")
    sp.set_defaults(func=cmd_list_items)

    sp = sub.add_parser("run-day", help="Run full workflow for both shops")
    sp.add_argument("--date", required=True)
    sp.set_defaults(func=cmd_run_day)

    sp = sub.add_parser("ingest-counts", help="Import all daily count CSVs from a folder")   
    sp.add_argument("--folder", required=True, help="Folder containing count_*.csv")
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.add_argument("--processed", required=False, help="Processed folder (default: sibling 'processed')")
    sp.add_argument("--rejected", required=False, help="Rejected folder (default: sibling 'rejected')")
    sp.set_defaults(func=cmd_ingest_counts)

    sp = sub.add_parser("generate-request", help="Generate restock request from par levels")
    sp.add_argument("--location", required=True, help="Location name")
    sp.add_argument("--csv-path", required=False, help="Optional CSV export path")
    sp.set_defaults(func=cmd_generate_request)

    sp = sub.add_parser("pick-list", help="Generate Keele pick list for a location")
    sp.add_argument("--location", required=True, help="Requesting location name")
    sp.add_argument("--csv-path", required=False, help="Optional CSV export path")
    sp.set_defaults(func=cmd_keele_pick_list)

    sp = sub.add_parser("keele-supplier-order", help="Generate supplier order for Keele")
    sp.add_argument("--csv-path", required=False, help="Optional CSV export path") 
    sp.set_defaults(func=cmd_keele_supplier_order)

    parser_import_items = sub.add_parser(
    "import-items",
    help="Import items and par levels from CSV"
)


    sp = sub.add_parser("export-count-sheet", help="Export count template to Google Sheet")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.set_defaults(func=cmd_export_count_sheet)


# Import count from Google Sheet
    sp = sub.add_parser(
        "import-count-sheet",
        help="Import count from Google Sheet"
    )
    sp.add_argument("--location", required=True, help="Location name")
    sp.add_argument("--date", required=True, help="Count date (YYYY-MM-DD)")
    sp.set_defaults(func=cmd_import_count_sheet)

    parser_import_items.add_argument("csv_path")

    parser_import_items.set_defaults(func=cmd_import_items)

    return p




def print_item_stock(item: str) -> None:
    k = current_stock("Keele", item)
    l = current_stock("Little Shop", item)
    print(f"{item}")
    print(f"  Keele:       {k}")
    print(f"  Little Shop: {l}")




def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


def cmd_dashboard(_args: argparse.Namespace) -> None:
    init_db()
    items = get_items()
    if not items:
        print("No items found. Add items first with add-item.")
        return

    print("Item | Keele | Little Shop")
    print("-----|-------|------------")
    for row in items:
        name = str(row["name"])
        k = current_stock("Keele", name)
        l = current_stock("Little Shop", name)
        print(f"{name} | {k} | {l}")


def cmd_export_sheets(args):
    init_db()

    locations = ["Keele", "Little Shop"]

    for loc in locations:
        print(f"\n📤 Exporting count sheet for {loc}...")
        export_count_to_sheet(loc)

    print("\n✅ All sheets exported\n")

if __name__ == "__main__":
    main()