"""Static guards for the ETF equity pending state (ui-audit 2026-09-04 P1#5).

Audit finding: with 6 ETFs missing history the summary still showed a row
of fabricated zeros (策略权益 0 / 累计投入 0 / DCA 相对 0%) next to a blank
chart — missing data must never be presented as a zero-valued simulation
result (§1.2 / §7.10).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ETF = (ROOT / "app/static/pages/ashare_etf.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")


def test_missing_history_renders_pending_state_not_zeros() -> None:
    idx = ETF.index("function _renderEquitySummaryCards")
    block = ETF[idx:idx + 2000]
    assert "historyMissing" in block
    assert "etf-equity-awaiting" in block
    assert "等待历史数据" in block
    assert "不会以 0 作为模拟结果" in block


def test_pending_triggers_on_full_symbol_loss_or_missing_source() -> None:
    idx = ETF.index("function _renderEquitySummaryCards")
    block = ETF[idx:idx + 1200]
    assert 'meta?.source_status === "missing"' in block
    assert "missingSymbols >= totalSymbols" in block


def test_genuine_zero_positions_are_not_swallowed() -> None:
    # months_simulated > 0 with zero values is a real zero-holdings result,
    # not missing data — the guard must keep it as numbers.
    idx = ETF.index("function _renderEquitySummaryCards")
    block = ETF[idx:idx + 1200]
    assert "(summary?.months_simulated ?? 0) === 0" in block


def test_pending_card_has_dashed_placeholder_styling() -> None:
    assert ".etf-equity-awaiting" in STYLES
    idx = STYLES.index(".etf-equity-awaiting {")
    block = STYLES[idx:STYLES.index("}", idx)]
    assert "dashed" in block
