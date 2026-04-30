from stock.services import daily_run


def test_run_day_processes_locations_in_order(monkeypatch):
    seen = []

    def fake_run_daily_for_location(location, date, writer=print):
        seen.append((location, date))

    monkeypatch.setattr(daily_run, "run_daily_for_location", fake_run_daily_for_location)

    messages = []
    daily_run.run_day("2026-04-24", writer=messages.append)

    assert seen == [
        ("Little Shop", "2026-04-24"),
        ("Keele", "2026-04-24"),
    ]
    assert messages[-1] == "\nFULL DAY COMPLETE\n"


def test_daily_run_uses_saved_web_count_and_skips_missing_google_exports(monkeypatch):
    reconciled = []

    monkeypatch.setattr(
        daily_run,
        "get_saved_count_summary",
        lambda location, date: {"count_id": 42, "is_reconciled": False, "line_count": 3},
    )
    monkeypatch.setattr(daily_run, "reconcile_count", lambda count_id: reconciled.append(count_id) or [])
    monkeypatch.setattr(daily_run, "generate_request_from_par", lambda location: [])
    monkeypatch.setattr(daily_run, "generate_keele_pick_list", lambda location: [])
    monkeypatch.setattr(
        daily_run,
        "export_pick_list_to_sheet",
        lambda rows: (_ for _ in ()).throw(FileNotFoundError("missing credentials")),
    )

    messages = []
    daily_run.run_daily_for_location("Little Shop", "2026-04-30", writer=messages.append)

    assert reconciled == [42]
    assert any("Using saved web count" in message for message in messages)
    assert any("Skipped Google Sheets export" in message for message in messages)
