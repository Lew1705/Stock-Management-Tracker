from .history import list_recent_runs
from .orders import list_orders
from .transfers import list_recent_transfer_requests


def build_operations_history_context() -> dict:
    transfer_rows = list_recent_transfer_requests()[:10]
    order_rows = list_orders()[:10]
    run_rows = [dict(row) for row in list_recent_runs(limit=10)]
    return {
        "transfer_rows": transfer_rows,
        "order_rows": order_rows,
        "run_rows": run_rows,
    }
