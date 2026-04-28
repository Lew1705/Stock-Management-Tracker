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
