"""Guard against reintroducing the shared context rail.

The rail rendered 研究对象 / 周期 / 市场状态 / 数据 / 信源 as a full-width strip
above the workbench. Those values were already carried by the hero, the
statusbar and the per-chart captions, so the strip spent a row of vertical
space repeating them. It was removed page by page (monitoring, macro,
market-events, btc-derivatives) and finally from the technical-indicators page,
at which point ``ui/contextRail.js`` had no consumers left and was deleted.

The rail must not come back: a page mounting it would import a module that no
longer exists.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "app" / "static" / "pages"
EDITORIAL_CSS = ROOT / "app" / "static" / "editorial.css"


def _page_sources() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in PAGES.rglob("*.js")
    }


def test_context_rail_module_is_gone() -> None:
    assert not (ROOT / "app" / "static" / "ui" / "contextRail.js").exists(), (
        "ui/contextRail.js was deleted with the rail; do not restore it without "
        "a page that consumes it"
    )


def test_no_page_mounts_the_context_rail() -> None:
    offenders = [
        name for name, source in _page_sources().items() if "mountContextRail" in source
    ]
    assert offenders == [], f"these pages still mount the removed rail: {offenders}"


def test_no_rail_markup_or_state_hooks_remain() -> None:
    sources = "\n".join(_page_sources().values())
    assert "analysis-context-rail" not in sources, (
        "the indicators page must not recreate the rail host element"
    )
    assert "workbench-context-item" not in sources


def test_rail_css_is_removed() -> None:
    css = EDITORIAL_CSS.read_text(encoding="utf-8")
    assert ".workbench-context-rail" not in css
    assert ".workbench-context-item" not in css
    assert "--context-rail-min-height" not in css, (
        "the rail's sizing token has no consumer once the rail is gone"
    )
