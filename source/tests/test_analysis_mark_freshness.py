"""Static guards for quote freshness semantics (ui-audit 2026-09-04 P1#4).

Audit finding: the realtime card labeled a 2-day-old cached mark as
"实时标记价 / Live / 5 分钟自动刷新" with a bullish chip. Freshness is a
data-availability state (§3.2) and must never read as a market direction
(§7.10) — info/warning tones only.

2026-09-22 price-lag follow-up: a bundle's `mark` can itself be hours/days
old; rendering it on first paint tells the user the wrong price for the
200–800ms it takes the live fetch to return. We refuse to render a bundle-
derived mark older than BUNDLE_MARK_STALE_AFTER_MS, and we align
MARK_STALE_AFTER_MS with the backend's LIVE_MARK_MAX_AGE_SECONDS (15s) so
the chip and the service agree on what "fresh" means.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")


def test_mark_chip_is_dynamic_and_starts_neutral() -> None:
    assert 'id="analysis-mark-freshness"' in ANALYSIS
    assert "chip chip-neutral" in ANALYSIS


def test_stale_mark_shows_true_age_in_warning_tone() -> None:
    assert "MARK_STALE_AFTER_MS" in ANALYSIS
    assert "applyMarkFreshness" in ANALYSIS
    assert "报价过期" in ANALYSIS
    assert 'chip chip-warning' in ANALYSIS
    # the age label formats days/hours, not a fake "Live"
    assert '"实时"' in ANALYSIS
    assert 'statusChip("Live"' not in ANALYSIS
    start = ANALYSIS.index("applyMarkFreshness")
    helper_block = ANALYSIS[start:start + 1500]
    assert '"chip-bullish"' not in helper_block


def test_freshness_applies_on_first_render_and_enhancement() -> None:
    assert "displayLatestMark(markPayload, { fromBundle: true });" in ANALYSIS
    assert "displayLatestMark(markPayload, { preferLive });" in ANALYSIS  # live quote path


def test_mark_stale_threshold_aligned_with_backend() -> None:
    # Backstop against anyone reverting the front-end freshness budget back
    # to 60s — that mismatch was the original bug that let 6-day-old quotes
    # render with a "实时" chip.
    assert "MARK_STALE_AFTER_MS = 15 * 1000" in ANALYSIS
    assert "MARK_STALE_AFTER_MS = 60 * 1000" not in ANALYSIS


def test_bundle_mark_has_stale_cutoff_constant() -> None:
    assert "BUNDLE_MARK_STALE_AFTER_MS" in ANALYSIS
    # 30s is a deliberate buffer above the 15s fast path: a snapshot older
    # than 30s clearly predates the page load and should never be shown
    # even for one frame while the live fetch is in flight.
    assert "BUNDLE_MARK_STALE_AFTER_MS = 30 * 1000" in ANALYSIS


def test_display_latest_mark_refuses_overaged_bundle_payload() -> None:
    # The function must inspect options.fromBundle and refuse to write
    # latestDisplayedMark when the bundle payload exceeds the cutoff. The
    # placeholder "等待最新报价" copy is the user-visible signal.
    start = ANALYSIS.index("function displayLatestMark(")
    block = ANALYSIS[start:start + 1500]
    assert "fromBundle" in block
    assert "BUNDLE_MARK_STALE_AFTER_MS" in block
    assert "等待最新报价" in block


def test_display_latest_mark_keeps_strict_newer_than_previous_guard() -> None:
    # Pre-existing invariant: never let an older payload overwrite a newer
    # display. The new bundle-too-stale branch must not have weakened this.
    start = ANALYSIS.index("function displayLatestMark(")
    block = ANALYSIS[start:start + 1500]
    assert "timestamp >= Date.parse(latestDisplayedMark.ts_event)" in block
