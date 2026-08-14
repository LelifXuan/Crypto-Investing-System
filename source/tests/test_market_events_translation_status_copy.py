"""Translation UI only exposes an active state, not redundant completion badges."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "static" / "pages" / "market_events.js").read_text(encoding="utf-8")


def test_completed_translation_has_no_per_event_badge() -> None:
    mapping = SOURCE[SOURCE.index("function translationStatusLabel"):SOURCE.index("function translationChipMarkup")]
    assert 'translated: ""' in mapping
    assert "中文翻译完成" not in mapping


def test_pending_translation_uses_one_short_label() -> None:
    assert 'pending: "翻译中"' in SOURCE
    assert 'queued: "翻译中"' in SOURCE
    assert 'renderStatus("翻译中", "loading")' in SOURCE
    assert "中文翻译完成：" not in SOURCE
