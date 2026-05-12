from stock.db import add_transaction, current_stock
from stock.services.analytics import build_analytics_dashboard_context, build_item_analytics_context, detect_anomalies
from stock.services.items import save_item_record


def test_analytics_dashboard_uses_demo_history_when_no_transactions(isolated_db):
    save_item_record(
        item_id=None,
        name="Oat Milk",
        category="Milk",
        base_unit="each",
        supplier="Booker",
        ref="BK-1",
        cost_per_unit="1.40",
        par_keele="12",
        par_little_shop="6",
    )

    context = build_analytics_dashboard_context({"period": "7", "category": "milk"})

    assert context["has_real_history"] is False
    assert context["kpis"]["total_items"] == 1
    assert context["daily_chart"]["points"]
    assert context["top_items"]


def test_detect_anomalies_flags_fast_depletion(isolated_db):
    save_item_record(
        item_id=None,
        name="Espresso Beans",
        category="Food",
        base_unit="g",
        supplier="Roastery",
        ref="ESP",
        cost_per_unit="8.00",
        par_keele="10",
        par_little_shop="0",
    )
    add_transaction("Keele", "Espresso Beans", 3, "RECEIVE", "Opening stock")

    context = build_analytics_dashboard_context({"period": "30", "category": "food"})
    alerts = detect_anomalies(
        [
            {
                "date": f"2026-04-{day:02d}",
                "item_id": 1,
                "usage_qty": 1.5,
                "waste_qty": 0,
            }
            for day in range(1, 15)
        ],
        [{"id": 1, "name": "Espresso Beans", "base_unit": "kg"}],
        {1: current_stock("Keele", "Espresso Beans")},
    )

    assert context["has_real_history"] is True
    assert any(alert["severity"] == "critical" for alert in alerts)


def test_item_analytics_returns_forecast_metrics(isolated_db):
    save_item_record(
        item_id=None,
        name="Vanilla Syrup",
        category="Syrups",
        base_unit="each",
        supplier="Monin",
        ref="VN",
        cost_per_unit="6.50",
        par_keele="4",
        par_little_shop="2",
    )

    context = build_item_analytics_context(1, {"period": "30"})

    assert context["item"]["name"] == "Vanilla Syrup"
    assert context["overview"]["average_daily_usage"] > 0
    assert context["stock_chart"]["points"]
    assert context["insights"]
