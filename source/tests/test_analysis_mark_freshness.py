"""Static guards for quote freshness semantics (ui-audit 2026-09-04 P1#4).

Audit finding: the realtime card labeled a 2-day-old cached mark as
"实时标记价 / Live / 5 分钟自动刷新" with a bullish chip. Freshness is a
data-availability state (§3.2) and must never read as a market direction
(§7.10) — info/warning tones only.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")


def test_mark_chip_is_dynamic_and_starts_neutral() -> None:
    assert 'id="analysis-mark-freshness"' in ANALYSIS
    assert "chip chip-neutral" in ANALYSIS


def test_stale_mark_shows_true_age_in_warning_tone() -> None:
    assert "MARK_STALE_AFTER_MS" in ANALYSIS
    assert "applyMarkFreshness" in ANALYSIS
    assert "缓存 · " in ANALYSIS
    assert 'chip chip-warning' in ANALYSIS
    # the age label formats days/hours, not a fake "Live"
    assert '"实时"' in ANALYSIS
    assert 'statusChip("Live"' not in ANALYSIS
    assert '"chip-bullish"' not in ANALYSIS[ANALYSIS.index("applyMarkFreshness"):ANALYSIS.index("applyMarkFreshness") + 1500]


def test_freshness_applies_on_first_render_and_enhancement() -> None:
    assert "applyMarkFreshness(markPayload);" in ANALYSIS  # loadAll initial render
    assert "applyMarkFreshness(markPayload, { preferLive });" in ANALYSIS  # 5-min refresh path
