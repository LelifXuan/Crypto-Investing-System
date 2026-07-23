from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.macro.providers.tradingeconomics_web import (
    TradingEconomicsWebProvider,
    parse_us_bond_table,
)

US_BOND_TABLE_HTML = """
<table>
  <thead>
    <tr><th></th><th>收益率</th><th>天</th><th>Month</th><th>年</th><th>日</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>US 10Y</td><td>4.58</td><td>0.007%</td><td>0.162%</td>
      <td>0.095%</td><td>2026-06-09</td>
    </tr>
    <tr>
      <td>US 5Y TIPS</td><td>1.83</td><td>0.030%</td><td>0.422%</td>
      <td>0.085%</td><td>2026-06-08</td>
    </tr>
    <tr>
      <td>US 30Y TIPS</td><td>2.80</td><td>0.057%</td><td>0.095%</td>
      <td>0.116%</td><td>2026-06-08</td>
    </tr>
  </tbody>
</table>
"""


def test_parse_us_bond_table_extracts_5y_tips() -> None:
    row = parse_us_bond_table(US_BOND_TABLE_HTML, "US 5Y TIPS")

    assert row.label == "US 5Y TIPS"
    assert row.yield_value == Decimal("1.83")
    assert row.day_change_pct == Decimal("0.030")
    assert row.month_change_pct == Decimal("0.422")
    assert row.year_change_pct == Decimal("0.085")
    assert row.date.date().isoformat() == "2026-06-08"


def test_parse_us_bond_table_rejects_missing_target_row() -> None:
    with pytest.raises(ValueError, match="US 5Y TIPS"):
        parse_us_bond_table(US_BOND_TABLE_HTML.replace("US 5Y TIPS", "US 2Y TIPS"), "US 5Y TIPS")


@pytest.mark.asyncio
async def test_provider_returns_macro_fetch_result_for_5y_tips(monkeypatch) -> None:
    provider = TradingEconomicsWebProvider()

    async def fake_fetch_html():
        return US_BOND_TABLE_HTML

    monkeypatch.setattr(provider, "_fetch_us_bond_html", fake_fetch_html)

    result = await provider.fetch_latest("US 5Y TIPS")

    assert result.value == Decimal("1.83")
    assert result.observation_ts.date().isoformat() == "2026-06-08"
    assert result.source_ref == "tradingeconomics_web:US 5Y TIPS"
    assert result.metadata["day_change_pct"] == "0.030"
