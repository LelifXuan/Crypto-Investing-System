from pathlib import Path


PAGE = Path("app/static/pages/analysis.js")


def test_boll_chart_uses_editorial_theme_roles() -> None:
    source = PAGE.read_text(encoding="utf-8")
    boll = source[source.index('["analysis-boll"') : source.index('["analysis-rsi"')]

    assert 'themeColor("--bullish", "#34745f")' not in boll
    assert 'themeColor("--bearish", "#a34f5f")' not in boll
    assert 'themeColor("--info", "#3e6f9f")' in boll
    assert 'themeColor("--accent", "#66548e")' in boll
    assert 'themeColor("--accent-strong", "#4d3b73")' in boll
    assert 'backgroundColor: "rgba(102, 84, 142, 0.07)"' in boll
    assert "fill: 2" in boll
    assert '"#a896c8"' not in boll
    assert '"#5a6a7c"' not in boll
