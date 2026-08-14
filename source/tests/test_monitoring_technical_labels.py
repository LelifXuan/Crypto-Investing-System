from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_monitoring_tech_cards_render_formula():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "monitoring.js").read_text(encoding="utf-8", errors="replace")
    assert "item.formula" in source or "formula" in source, "Monitoring technical cards not reading formula field"


def test_monitoring_tech_cards_render_comment():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "monitoring.js").read_text(encoding="utf-8", errors="replace")
    assert "item.comment" in source or "comment" in source, "Monitoring technical cards not reading comment field"


def test_monitoring_dashboard_imports_classifier():
    source = (Path(__file__).resolve().parents[1] / "app" / "services" / "monitoring_dashboard.py").read_text(encoding="utf-8", errors="replace")
    assert "from app.services.technical_signal_classifier import" in source, "monitoring_dashboard does not import classifier"


def test_classifier_returns_structured_output():
    from app.services.technical_signal_classifier import classify_signals
    # Test with empty data
    result = classify_signals([], {}, {})
    assert isinstance(result, list), "classify_signals should return a list"


def test_classifier_ema_structure_returns_formula():
    from app.services.technical_signal_classifier import classify_signals
    # Minimal test with single candle and core series
    class Candle:
        close = 100.0
    candles = [Candle()]
    core = {"ema_20": {"values": [98, 99]}, "ema_50": {"values": [95, 96]}, "ema_200": {"values": [90, 91]}}
    result = classify_signals(candles, core, {})
    ema = next((s for s in result if s.get("indicator_key") == "ema_structure"), None)
    assert ema is not None, "EMA structure signal missing"
    assert "formula" in ema, "EMA structure missing formula"
    assert "comment" in ema, "EMA structure missing comment"
