"""Guards the opportunity workspace height and ETF toolbar hierarchy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
ETF = (ROOT / "app" / "static" / "pages" / "ashare_etf.js").read_text(encoding="utf-8")


def test_strategy_scan_workspace_fills_viewport_and_uses_taller_cells() -> None:
    assert 'body[data-page="ai-strategy"] .strategy-scan-page {' in EDITORIAL
    assert "min-height: calc(100vh - var(--topbar-height)" in EDITORIAL
    assert 'body[data-page="ai-strategy"] .strategy-scan-grid {' in EDITORIAL
    assert "flex: 1 1 auto" in EDITORIAL
    assert 'body[data-page="ai-strategy"] .scan-cell-btn {' in EDITORIAL
    assert "min-height: 52px" in EDITORIAL


def test_etf_title_and_frequency_note_are_separated() -> None:
    assert '"HALO & 现金流 ETF"' in ETF
    assert "完整策略 · HALO 六只周定投+季末调仓 + 现金流ETF 周定投(6:1)" not in ETF
    frequency_block = ETF[ETF.index('<span>定投频率</span>'):ETF.index('<label class="etf-equity-offset">')]
    assert "etf-equity-freq-hint" not in frequency_block
    assert "etf-equity-strategy-note" in ETF


def test_etf_toolbar_is_centred_and_legacy_green_hovers_are_overridden() -> None:
    assert 'body[data-page="ashare-etf"] .etf-equity-controls {' in EDITORIAL
    assert "align-items: center" in EDITORIAL
    assert ".etf-equity-mode-btn:hover:not(.is-active)" in STYLES
    assert ".etf-equity-from .etf-equity-freq-btn:hover" in STYLES
    assert "background: var(--accent-soft)" in STYLES
    assert "background: var(--accent-ghost)" in STYLES
    assert "rgba(110, 155, 148" not in STYLES
