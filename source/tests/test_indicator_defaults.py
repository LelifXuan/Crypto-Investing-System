from decimal import Decimal

from app.services.indicators import SUPPORTED_INDICATOR_TIMEFRAMES, IndicatorService


def test_supported_indicator_timeframes() -> None:
    assert SUPPORTED_INDICATOR_TIMEFRAMES == ("1h", "4h", "1d", "1w", "30d")


def test_default_indicator_parameters() -> None:
    params = IndicatorService.default_parameters()
    assert "sma_window" not in params
    assert params["ema_window"] == 14
    assert params["macd_slow"] == 26
    assert params["bbands_stddev"] == Decimal("2")
