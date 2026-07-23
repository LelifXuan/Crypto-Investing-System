"""Tests for CFTC COT provider."""
from datetime import datetime, timezone

import pytest

from app.services.macro.providers.cftc import (
    CotSnapshot,
    _compute_percentile,
    _parse_cot_csv,
)


# Sample CFTC disaggregated COT report with gold line
_SAMPLE_COT_CSV = """\
"WHEAT-SRW - CHICAGO BOARD OF TRADE",260714,2026-06-30,001602,CBT ,00,001 ,  500000,   80000,  120000,   75000,   15000,   30000,   70000,  100000,   90000,   30000,   20000,   80000,  480000,  490000,   20000,   10000,  470000,   80000,  110000,   72000,   15000,   29000,   65000,  105000,   85000,   32000,   21000,   75000,  460000,  465000,   23000,   15000,   20000,    2000,    9000,    5000,     500,     200,   10000,    3000,     800,     600,    2500,    2000,   22000,   19000,    1000,    3500,   35000,    2000,   30000,    -800,    1500,    7000,    3000,  -20000,   11000,    2000,   -2500,    8000,   33000,   35000,    2000,     100,  100.0,   15.0,   22.0,   14.0,    3.0,    6.0,   14.0,   20.0,   18.0,    6.0,    4.0,   15.0,   92.0,   93.0,    7.0,    7.0,  100.0,   16.0,   22.0,   15.0,    3.5,    6.0,   13.5,   22.5,   19.5,    7.0,    4.5,   15.5,   92.5,   93.5,    7.5,    6.5,  100.0,   10.0,   45.0,   25.0,    2.5,    1.0,   50.0,   15.0,    4.0,    3.0,   12.5,   10.0,   95.0,   83.0,    5.0,   17.0,    400,     80,     95,     20,     10,     18,     70,     55,     70,     70,     50,     65,    320,    295,    395,     78,     90,     22,     10,     18,     65,     55,     70,     75,     45,     65,    315,    290,    130,     15,     60,     12,      4,.,      9,     14,      5,      4,     22,     12,     55,    105,    12.0,    11.5,    20.5,    21.5,     6.5,     8.5,    11.0,    13.0,    13.0,    12.0,    21.5,    22.5,     6.5,     9.5,    11.5,    14.5,    46.5,    22.5,    60.0,    35.0,    46.5,    21.0,    57.0,    31.0,"(CONTRACTS OF 5,000 BUSHELS)","001602","CBT ","001 ","A10","Combined"
"GOLD - COMMODITY EXCHANGE INC.",260714,2026-07-14,088691,CMX ,01,088 ,  522185,   19603,   36897,   25617,  213125,   75263,  136610,   17463,   32780,   80284,   23502,  101842,  472000,  500871,   50185,   21313,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,       0,   15702,    1178,    -438,     -27,   -6189,   19892,    1820,   -2474,     447,   -9304,    2224,    2790,   16795,   16253,   -1093,    -551,  100.0,    3.8,    7.1,    4.9,   40.8,   14.4,   26.2,    3.3,    6.3,   15.4,    4.5,   19.5,   90.4,   95.9,    9.6,    4.1,  100.0,    3.8,    7.1,    4.9,   40.8,   14.4,   26.2,    3.3,    6.3,   15.4,    4.5,   19.5,   90.4,   95.9,    9.6,    4.1,  100.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    0.0,    289,     23,     18,     11,     28,     33,     74,     24,     63,     93,     33,     67,    268,    200,    289,     23,     18,     11,     28,     33,     74,     24,     63,     93,     33,     67,    268,    200,      0,      0,      0,      0,      0,      0,      0,      0,      0,      0,      0,      0,      0,      0,    19.2,    29.5,    30.1,    45.4,    14.5,    25.2,    20.1,    35.8,    19.2,    29.5,    30.1,    45.4,    14.5,    25.2,    20.1,    35.8,     0.0,     0.0,     0.0,     0.0,     0.0,     0.0,     0.0,     0.0,"(CONTRACTS OF 100 TROY OUNCES)","088691","CMX ","088 ","N20","Combined"
"""


class TestParseCotCsv:
    def test_finds_gold_contract(self):
        snap = _parse_cot_csv(_SAMPLE_COT_CSV)
        assert snap is not None
        assert snap.oi_total == 522185
        assert snap.managed_money_long == 213125
        assert snap.managed_money_short == 75263
        assert snap.report_date == datetime(2026, 7, 14, tzinfo=timezone.utc)

    def test_managed_money_net(self):
        snap = _parse_cot_csv(_SAMPLE_COT_CSV)
        assert snap.managed_money_net == 213125 - 75263  # 137862

    def test_net_pct_of_oi(self):
        snap = _parse_cot_csv(_SAMPLE_COT_CSV)
        expected = (213125 - 75263) / 522185
        assert snap.net_pct_of_oi == pytest.approx(expected, abs=0.001)

    def test_returns_none_for_missing_gold(self):
        csv_text = '"CORN - CHICAGO BOARD OF TRADE",260714,2026-07-14,002602,CBT,00,002,1000000,100000,200000'
        assert _parse_cot_csv(csv_text) is None

    def test_returns_none_for_empty_csv(self):
        assert _parse_cot_csv("") is None


class TestPercentile:
    def test_percentile_empty_history(self):
        assert _compute_percentile([], 0.5) is None

    def test_percentile_max(self):
        history = [0.1, 0.2, 0.3, 0.4]
        assert _compute_percentile(history, 0.5) == 1.0  # 100th percentile

    def test_percentile_min(self):
        history = [0.2, 0.3, 0.4, 0.5]
        assert _compute_percentile(history, 0.1) == 0.0  # 0th percentile

    def test_percentile_mid(self):
        history = [0.1, 0.3, 0.5, 0.7]
        assert _compute_percentile(history, 0.4) == 0.5  # 50th percentile (2 below, 2 above)


class TestCotSnapshot:
    def test_zero_oi_returns_zero(self):
        snap = CotSnapshot(
            report_date=datetime(2026, 7, 14, tzinfo=timezone.utc),
            oi_total=0,
            managed_money_long=1000,
            managed_money_short=500,
        )
        assert snap.net_pct_of_oi == 0.0


class TestProviderRegistration:
    def test_cftc_provider_is_registered(self):
        from app.services.macro.provider_registry import MacroProviderRegistry
        registry = MacroProviderRegistry()
        provider = registry.resolve(source_provider="cftc", source_kind="raw_series")
        assert provider is not None
        assert provider.provider_key == "cftc"

    def test_cftc_provider_supports_correct_source(self):
        from app.services.macro.providers.cftc import CftcCotProvider
        p = CftcCotProvider()
        assert p.supports("cftc", "raw_series") is True
        assert p.supports("fred", "raw_series") is False
