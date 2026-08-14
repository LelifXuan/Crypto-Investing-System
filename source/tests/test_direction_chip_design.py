"""Static guards for the shared editorial long/short chip language."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_direction_chip_tokens_are_defined_in_the_final_theme_layer() -> None:
    for token in (
        "--bullish-chip-ink",
        "--bullish-chip-surface",
        "--bullish-chip-surface-soft",
        "--bullish-chip-border",
        "--bearish-chip-ink",
        "--bearish-chip-surface",
        "--bearish-chip-surface-soft",
        "--bearish-chip-border",
        "--neutral-chip-ink",
        "--neutral-chip-surface",
        "--neutral-chip-border",
    ):
        assert token in EDITORIAL


def test_all_direction_chip_apis_use_the_shared_tokens() -> None:
    combined = EDITORIAL + STYLES
    for selector in (
        ".impact-bullish",
        ".impact-bearish",
        ".impact-neutral",
        ".chip-bullish",
        ".chip-bullish-soft",
        ".chip-bearish",
        ".chip-bearish-soft",
        ".chip-neutral",
        '.btc-tone-chip[data-tone="bullish"]',
        '.btc-tone-chip[data-tone="bearish"]',
        '.btc-confidence-chip[data-tone="bullish"]',
        '.btc-confidence-chip[data-tone="bearish"]',
    ):
        assert selector in combined

    assert "var(--bullish-chip-ink" in combined
    assert "var(--bearish-chip-ink" in combined
    assert "var(--neutral-chip-ink" in combined


def test_direction_chips_do_not_reuse_brand_purple() -> None:
    start = EDITORIAL.index("/* Direction chips stay semantic")
    end = EDITORIAL.index(".chip-warning", start)
    direction_block = EDITORIAL[start:end]
    assert "var(--accent" not in direction_block
    assert "#66548e" not in direction_block.lower()
    assert "#4d3b73" not in direction_block.lower()
