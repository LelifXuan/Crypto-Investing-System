"""Static guards for primary-control contrast and monitoring column parity."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_primary_buttons_define_light_text_and_descendants_inherit_it() -> None:
    assert "color: var(--white)" in EDITORIAL
    assert '#page-root :where(button, .btn, .primary-button, .btn-primary) > :where(span, svg)' in EDITORIAL
    for excluded in ("dropdown-item", "page-guide-fab"):
        assert f":not(.{excluded})" in EDITORIAL


def test_monitoring_summary_hosts_stretch_their_cards() -> None:
    assert "align-items: stretch" in EDITORIAL
    assert '#monitoring-macro-panel,' in EDITORIAL
    assert '#monitoring-terminal-summary { display: flex;' in EDITORIAL
    assert '#monitoring-macro-panel > .monitoring-panel' in EDITORIAL
    assert '#monitoring-terminal-summary > .terminal-summary-card' in EDITORIAL
