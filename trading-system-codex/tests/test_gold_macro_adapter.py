from app.services.gold_macro_adapter import _gold_macro_snapshot


def _make_macro(indicators: list[dict]) -> dict:
    return {
        "layer_map": {
            "rates_policy": {"indicators": indicators},
            "cross_asset_confirmation": {"indicators": indicators},
            "inflation": {"indicators": indicators},
        },
        "layers": [
            {"layer_key": "rates_policy", "indicators": indicators},
            {"layer_key": "cross_asset_confirmation", "indicators": indicators},
            {"layer_key": "inflation", "indicators": indicators},
        ],
    }


def test_gold_macro_snapshot_missing_returns_missing():
    snapshot = _gold_macro_snapshot({})
    assert snapshot["real_yield_10y"]["bias"] == "missing"
    assert snapshot["dxy"]["bias"] == "missing"
    assert snapshot["cpi_yoy"]["bias"] == "missing"
    assert snapshot["vix"]["bias"] == "missing"


def test_gold_macro_snapshot_real_yield_high_is_bearish():
    # real_yield_5y=2.5 (在 2.0-2.8 之间 → bearish)
    macro = _make_macro([{"indicator_key": "real_yield_5y", "value_num": 2.5, "unit": "%",
                          "display_label": "5Y Real Yield", "source_provider": "fred",
                          "status": "ok"}])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["real_yield_10y"]["bias"] == "bearish"
    assert "实际利率偏高" in snapshot["real_yield_10y"]["bias_reason"]


def test_gold_macro_snapshot_dxy_strong_bearish():
    macro = _make_macro([{"indicator_key": "dxy", "value_num": 110.0, "unit": "index",
                          "display_label": "DXY", "source_provider": "fred", "status": "ok"}])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["dxy"]["bias"] == "strong_bearish"


def test_gold_macro_snapshot_cpi_2d_table_bullish():
    # CPI=2.7 + RealYield=1.0 + DXY=100 → bullish
    macro = _make_macro([
        {"indicator_key": "cpi_yoy", "value_num": 2.7, "unit": "%", "display_label": "CPI",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 1.0, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 100.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["cpi_yoy"]["bias"] == "bullish"
    assert "抗通胀需求" in snapshot["cpi_yoy"]["bias_reason"]


def test_gold_macro_snapshot_cpi_high_with_tight_yields_bearish():
    # CPI=3.2 + RealYield=2.1 + DXY=106 → bearish
    macro = _make_macro([
        {"indicator_key": "cpi_yoy", "value_num": 3.2, "unit": "%", "display_label": "CPI",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 2.1, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 106.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["cpi_yoy"]["bias"] == "bearish"


def test_gold_macro_snapshot_liquidity_shock_detection():
    # VIX=30 + DXY=106 + RealYield=2.1 → liquidity_shock
    macro = _make_macro([
        {"indicator_key": "vix", "value_num": 30.0, "unit": "index", "display_label": "VIX",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 106.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 2.1, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["_diagnostics"]["liquidity_shock_detected"] is True
    assert snapshot["vix"]["bias"] == "bearish"  # 流动性冲击下 VIX 急升 ≠ 避险
    assert snapshot["dxy"]["bias"] == "bearish"
    assert "流动性冲击" in snapshot["vix"]["bias_reason"]