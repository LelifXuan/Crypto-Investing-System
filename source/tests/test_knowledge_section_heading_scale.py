import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL_CSS = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_knowledge_collapse_heading_uses_compact_type_scale() -> None:
    selector = (
        'body[data-page="knowledge-base"] #page-root '
        ".knowledge-section-heading h2"
    )
    desktop, compact = re.findall(
        rf"{re.escape(selector)}\s*\{{([^}}]*)\}}",
        EDITORIAL_CSS,
    )

    assert "font-size: 18px" in desktop
    assert "font-size: 16px" in compact
    assert "text-wrap: balance" in desktop
