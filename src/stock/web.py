import argparse
import io
import os
import threading
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from flask import Flask, Response, request

from .cli import cmd_run_day
from .db import init_db, recent_run_history, record_run_history, seed_locations


app = Flask(__name__)
_run_lock = threading.Lock()


def _today() -> str:
    timezone_name = os.environ.get("STOCK_TIMEZONE", "Europe/London")
    return datetime.now(ZoneInfo(timezone_name)).date().isoformat()


def _bootstrap() -> None:
    init_db()
    seed_locations()


def _page(body: str, status_code: int = 200) -> Response:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Tracker Runner</title>
  <style>
    :root {{
      --bg: #f5efe4;
      --card: #fffaf2;
      --ink: #1d1a17;
      --accent: #1f6f5f;
      --accent-2: #d97b2d;
      --line: #d8cdbd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, #f2d5ad 0, transparent 30%),
        linear-gradient(180deg, #f6f0e8 0%, var(--bg) 100%);
      color: var(--ink);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(760px, 100%);
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 28px;
      box-shadow: 0 20px 60px rgba(54, 39, 23, 0.12);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3rem);
      line-height: 1;
    }}
    p {{
      margin: 0 0 16px;
      font-size: 1rem;
    }}
    form {{
      display: grid;
      gap: 12px;
      margin: 20px 0 0;
    }}
    label {{
      font-weight: 700;
    }}
    input, button {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid var(--line);
      font: inherit;
    }}
    button {{
      background: linear-gradient(135deg, var(--accent), #2b9d86);
      color: white;
      border: 0;
      font-weight: 700;
      cursor: pointer;
    }}
    button:hover {{
      filter: brightness(1.03);
    }}
    .meta {{
      color: #5b5045;
      font-size: 0.95rem;
    }}
    .warn {{
      padding: 12px 14px;
      background: #fff1e5;
      border: 1px solid #f0c39a;
      border-radius: 12px;
      color: #7a4316;
      margin-top: 16px;
    }}
    pre {{
      margin: 18px 0 0;
      padding: 16px;
      background: #201a15;
      color: #f3eee8;
      border-radius: 14px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .history {{
      margin-top: 28px;
      border-top: 1px solid var(--line);
      padding-top: 20px;
    }}
    .history-list {{
      display: grid;
      gap: 12px;
    }}
    .history-item {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.55);
    }}
    .status {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .status-success {{
      background: #dff3e8;
      color: #176646;
    }}
    .status-failed {{
      background: #fde7e3;
      color: #9a2d21;
    }}
    .history-meta {{
      margin: 0 0 8px;
      color: #5b5045;
      font-size: 0.95rem;
    }}
  </style>
</head>
<body>
  <main class="card">
    {body}
  </main>
</body>
</html>"""
    return Response(html, status=status_code, mimetype="text/html")


@app.get("/")
def index() -> Response:
    today = escape(_today())
    history = recent_run_history(limit=8)
    history_html = "".join(
        f"""
        <article class="history-item">
          <div class="status {'status-success' if row['status'] == 'SUCCESS' else 'status-failed'}">{escape(row['status'])}</div>
          <p class="history-meta">
            {escape(row['run_type'])} for {escape(row['run_date'])}
            <br>
            Finished: {escape(row['finished_at'] or row['started_at'])}
          </p>
          <pre>{escape((row['output'] or '').strip() or 'No output recorded.')}</pre>
        </article>
        """
        for row in history
    ) or "<p class='meta'>No runs recorded yet.</p>"
    return _page(
        f"""
        <h1>Stock Tracker Runner</h1>
        <p>Run the daily stock workflow whenever staff need it.</p>
        <p class="meta">Today in {escape(os.environ.get("STOCK_TIMEZONE", "Europe/London"))}: {today}</p>
        <form method="post" action="/run-day">
          <div>
            <label for="run-date">Run date</label>
            <input id="run-date" name="run_date" type="date" value="{today}" required>
          </div>
          <div>
            <label for="token">Access code</label>
            <input id="token" name="token" type="password" required>
          </div>
          <button type="submit">Run Daily Sync</button>
        </form>
        <section class="history">
          <h1 style="font-size:2rem; margin-bottom:12px;">Recent Runs</h1>
          <div class="history-list">
            {history_html}
          </div>
        </section>
        """
    )


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200


@app.post("/run-day")
def run_day() -> Response:
    expected_token = os.environ.get("STOCK_WEB_TOKEN", "").strip()
    submitted_token = request.form.get("token", "").strip()
    run_date = request.form.get("run_date", _today()).strip() or _today()

    if not expected_token:
        return _page("<h1>Missing access code</h1><div class='warn'>Set STOCK_WEB_TOKEN in Railway.</div>", 500)

    if submitted_token != expected_token:
        return _page(
            """
            <h1>Access denied</h1>
            <div class="warn">The access code was incorrect.</div>
            <p><a href="/">Go back</a></p>
            """,
            403,
        )

    if not _run_lock.acquire(blocking=False):
        return _page(
            """
            <h1>Already running</h1>
            <div class="warn">A daily sync is already in progress. Please wait a minute and try again.</div>
            <p><a href="/">Go back</a></p>
            """,
            409,
        )

    output = io.StringIO()
    try:
        _bootstrap()
        with redirect_stdout(output):
            cmd_run_day(argparse.Namespace(date=run_date))
        raw_output = output.getvalue() or "Run completed."
        record_run_history("run-day", run_date, "SUCCESS", raw_output)
        rendered = escape(raw_output)
        return _page(
            f"""
            <h1>Run complete</h1>
            <p class="meta">Processed date: {escape(run_date)}</p>
            <p><a href="/">Run again</a></p>
            <pre>{rendered}</pre>
            """
        )
    except Exception:
        raw_output = output.getvalue() + "\n" + traceback.format_exc()
        record_run_history("run-day", run_date, "FAILED", raw_output)
        rendered = escape(raw_output)
        return _page(
            f"""
            <h1>Run failed</h1>
            <div class="warn">Something went wrong while running the workflow.</div>
            <p><a href="/">Go back</a></p>
            <pre>{rendered}</pre>
            """,
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
