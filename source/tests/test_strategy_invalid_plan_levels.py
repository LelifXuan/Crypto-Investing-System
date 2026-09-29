from app.services.strategy_unified.opportunity_scanner import (
    OpportunityScanner,
    _extract_scan_item,
    _valid_stop_geometry,
)


def test_stop_must_be_outside_entry_zone_on_loss_side():
    assert not _valid_stop_geometry("SHORT", [118.78], 118.78)
    assert not _valid_stop_geometry("SHORT", [97.34, 97.73], 97.5)
    assert _valid_stop_geometry("SHORT", [97.34, 97.73], 100.54)
    assert not _valid_stop_geometry("LONG", [97.34, 97.73], 97.5)
    assert _valid_stop_geometry("LONG", [97.34, 97.73], 95.0)


def test_zero_risk_trade_plan_cannot_appear_as_ranked_opportunity():
    payload = {
        "status": "ready",
        "timeframe_stack": [
            {
                "timeframe": "4h",
                "direction": "SHORT",
                "freshness": "fresh",
                "confidence": 100,
                "current_price": 118.78,
                "key_support": 110,
                "invalidation": 121,
                "long_score": 10,
                "short_score": 90,
            }
        ],
        "trade_decision": {
            "side": "SHORT",
            "position_cap": "standard",
            "trade_timeframe": "4h",
            "permission": "allow",
        },
        "trade_plans": [
            {
                "plan_type": "TACTICAL_SHORT",
                "direction": "SHORT",
                "entry_zone": [118.78],
                "stop_loss": 118.78,
            }
        ],
    }
    item = _extract_scan_item(payload, "okb-usdt-perp", "OKB", "4h")
    assert "invalid_execution_levels" in item.qualification_reasons
    assert not item.qualified
    assert item.entry_zone == []
    assert item.stop_loss is None
    result = OpportunityScanner._result([item], ["okb-usdt-perp"], ("4h",), source="cache")
    assert result.ranked == []
