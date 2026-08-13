from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_matrix_status_text_is_legible():
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    start = css.index(".scan-cell-btn small")
    rule = css[start:css.index("}", start)]

    assert "font-size: 0.9rem" in rule
    assert "font-weight: 600" in rule
    assert "line-height: 1.4" in rule
