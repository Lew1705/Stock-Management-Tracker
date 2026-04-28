from ..db import record_run_history, recent_run_history


def list_recent_runs(limit: int = 10):
    return recent_run_history(limit=limit)


def save_run_history(run_type: str, run_date: str, status: str, output: str) -> int:
    return record_run_history(run_type, run_date, status, output)
