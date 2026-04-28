from stock.services.counts import get_daily_sync_readiness, save_count_data
from stock.services.items import save_item_record


def test_daily_sync_readiness_reports_missing_locations(isolated_db):
    readiness = get_daily_sync_readiness("2026-04-24")

    assert readiness["is_ready"] is False
    assert readiness["missing_locations"] == ["Keele", "Little Shop"]


def test_daily_sync_readiness_marks_both_locations_ready(isolated_db):
    save_item_record(
        item_id=None,
        name="Oatly",
        category="Milk",
        base_unit="each",
        supplier="Booker",
        ref="BK-1",
    )

    save_count_data("Keele", "2026-04-24", {1: "5"})
    save_count_data("Little Shop", "2026-04-24", {1: "2"})

    readiness = get_daily_sync_readiness("2026-04-24")

    assert readiness["is_ready"] is True
    assert readiness["missing_locations"] == []
    assert [row["line_count"] for row in readiness["locations"]] == [1, 1]
