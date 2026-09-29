from datetime import UTC, datetime, timedelta

from app.services.market_reference_price import select_reference_price
from app.services.strategy_signal.snapshot_builder import _build_structure_score

NOW = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)


def test_signed_structure_score_is_not_a_percentage() -> None:
    assert _build_structure_score({"overall_score": 0.19}) == (59.5, 40.5)
    assert _build_structure_score({"overall_score": -0.6}) == (20.0, 80.0)
    assert _build_structure_score({"overall_score": 0}) == (50.0, 50.0)
    assert _build_structure_score({"bias_score": 0}) == (0.0, 100.0)
    assert _build_structure_score({"overall_score": 64}) == (64, 36)


def test_old_mark_cannot_override_new_daily_candle() -> None:
    picked = select_reference_price(
        {"mark_price": "85843.2", "ts_event": (NOW - timedelta(days=5)).isoformat()},
        [{"close": "83389.8", "ts_open": NOW.replace(hour=0).isoformat()}],
        "1d",
        now=NOW,
    )
    assert picked["price"] == "83389.8"
    assert picked["price_as_of"] == NOW.replace(hour=0).isoformat()


def test_recent_mark_wins_and_all_stale_prices_are_rejected() -> None:
    mark = {"mark_price": "82621.99", "ts_event": (NOW - timedelta(minutes=5)).isoformat()}
    candle = {"close": "83389.8", "ts_open": NOW.replace(hour=0).isoformat()}
    assert select_reference_price(mark, [candle], "1d", now=NOW)["price"] == "82621.99"
    old = select_reference_price(mark, [candle], "1d", now=NOW + timedelta(days=5))
    assert old["price"] is None
