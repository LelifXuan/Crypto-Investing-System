from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOTION = (ROOT / "app/static/ui/semanticMotion.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
BTC = (ROOT / "app/static/pages/btc_derivatives.js").read_text(encoding="utf-8")


def test_unchanged_values_do_not_animate_and_abort_cleans_up() -> None:
    assert "normalized(previous) === normalized(next)" in MOTION
    assert 'signal?.addEventListener("abort"' in MOTION
    assert "window.clearTimeout(timer)" in MOTION
    assert "previousWorkbenchValues" in BTC


def test_reduced_motion_keeps_stable_final_state() -> None:
    assert "prefers-reduced-motion: reduce" in MOTION
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert ".is-semantic-value-change" in CSS
