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
)

# --- Helper: pretty print stock for one item in both locations ---
def print_item_stock(item: str) -> None:
    k = stock_on_hand("Keele", item)
    l = stock_on_hand("Little Shop", item)
    print(f"{item}")
    print(f"  Keele:       {k}")
    print(f"  Little Shop: {l}")


def cmd_init(_args: argparse.Namespace) -> None:
    init_db()
    seed_locations()
    print("Database initialised and locations seeded.")


def cmd_add_item(args: argparse.Namespace) -> None:
    init_db()
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


def cmd_stock(args: argparse.Namespace) -> None:
    init_db()
    print_item_stock(args.item)


def cmd_count_start(args: argparse.Namespace) -> None:
    init_db()
    count_id = create_count(args.location, args.week_ending)
    print(f"Created count: {count_id} ({args.location}, week ending {args.week_ending})")


def cmd_count_add(args: argparse.Namespace) -> None:
    init_db()

    # Option 1: user provided a count id (old way)
    if args.count_id is not None:
        count_id = args.count_id

    # Option 2: user provided location + week ending (new way)
    else:
        if not args.location or not args.week_ending:
            raise SystemExit("count-add needs either --count-id OR (--location AND --week-ending)")
        count_id = get_or_create_count(args.location, args.week_ending)

    add_count_line(count_id, args.item, args.counted)
    print(f"Added count line to count {count_id}: {args.item} = {args.counted}")



def cmd_usage(args: argparse.Namespace) -> None:
    init_db()
    used = usage_between_counts(args.location, args.item, args.open_count_id, args.close_count_id)
    print(f"Usage for {args.item} at {args.location} between counts {args.open_count_id} -> {args.close_count_id}: {used}")

def cmd_count_list(args: argparse.Namespace) -> None:
    init_db()
    rows = list_counts(location=args.location, limit=args.limit)

    if not rows:
        print("No stock counts found yet.")
        return

    print("ID | Location | Week ending | Created")
    print("---|----------|------------|--------")
    for r in rows:
        print(f"{r['id']} | {r['location']} | {r['week_ending']} | {r['created_at']}")



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock", description="Coffee shop stock tracker (rough CLI)")
    sub = p.add_subparsers(required=True)

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
    sp = sub.add_parser("stock", help="Show stock on hand for an item in both locations")
    sp.add_argument("--item", required=True)
    sp.set_defaults(func=cmd_stock)

    # dashboard
    sp = sub.add_parser("dashboard", help="Show all items and current stock per shop")
    sp.set_defaults(func=cmd_dashboard)


    # count-start
    sp = sub.add_parser("count-start", help="Create a stock count for a location")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--week-ending", required=True, help="YYYY-MM-DD")
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
    sp.add_argument("--week-ending", required=False, help="Used when --count-id is omitted (YYYY-MM-DD)")
    sp.add_argument("--item", required=True)
    sp.add_argument("--counted", required=True, type=float)
    sp.set_defaults(func=cmd_count_add)


    # usage
    sp = sub.add_parser("usage", help="Calculate usage between two counts")
    sp.add_argument("--location", required=True, choices=["Keele", "Little Shop"])
    sp.add_argument("--item", required=True)
    sp.add_argument("--open-count-id", required=True, type=int)
    sp.add_argument("--close-count-id", required=True, type=int)
    sp.set_defaults(func=cmd_usage)

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

def cmd_stock(args: argparse.Namespace) -> None:
    init_db()
    print_item_stock(args.item)


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


if __name__ == "__main__":
    main()