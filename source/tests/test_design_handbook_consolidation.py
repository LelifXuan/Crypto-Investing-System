"""Static smoke checks for §13.2 #8 design handbook consolidation.

Asserts that:
1. `source/docs/design-guidelines.md` is marked deprecated (header banner).
2. Same-path legacy file exists with the full 316-line snapshot.
3. V3.1 §0 priority #3 references the legacy path (not the live one).
4. V3.1 §13.2 #8 carries the V3.2 closure marker.
5. V3.1 §14.5 lists the V3.2 remaining debts (H1→H2 + UI_UX_AUDIT path).
6. V3.1 does not carry obsolete brand colors / viewport baselines that
   were conflicts with the legacy file.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
SOURCE_DOC = ROOT / "docs" / "design-guidelines.md"
LEGACY_DOC = ROOT / "source" / "docs" / "design-guidelines.md"
LEGACY_BACKUP = ROOT / "source" / "docs" / "design-guidelines-legacy.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_doc_marked_deprecated() -> None:
    """Header banner declares the file deprecated as of V3.2."""
    source = _read(LEGACY_DOC)
    head = source[:1200]
    assert "已废弃" in head, (
        "source/docs/design-guidelines.md should carry a deprecation banner"
    )
    assert "V3.2" in head, (
        "deprecation banner should reference V3.2 (2026-08-27)"
    )


def test_legacy_backup_snapshot_exists() -> None:
    assert LEGACY_BACKUP.exists(), (
        "source/docs/design-guidelines-legacy.md must exist as the V3.2 archive"
    )
    snapshot = _read(LEGACY_BACKUP)
    # Full 316-line snapshot preserved (allow minor drift).
    line_count = len(snapshot.splitlines())
    assert line_count >= 280, (
        f"legacy backup should preserve ≥280 lines, got {line_count}"
    )


def test_v31_priority_references_legacy_path() -> None:
    """V3.1 §0 priority #3 must point at the archived legacy file, not the
    deprecated live one."""
    source = _read(SOURCE_DOC)
    # Find the priority list item referring to legacy handbook.
    assert "design-guidelines-legacy.md" in source, (
        "V3.1 §0 should reference source/docs/design-guidelines-legacy.md"
    )
    # The live (non-legacy) path should NOT appear in §0 priorities.
    head = source[:1500]
    block = re.search(r"约束优先级：(.*?)(?:^---|\Z)", head, re.DOTALL)
    assert block is not None
    priorities = block.group(1)
    assert "source/docs/design-guidelines-legacy.md" in priorities
    # The bare live path should not appear in priorities (legacy renamed).
    # We tolerate it elsewhere in V3.1 if cited in migration notes.
    live_in_priorities = re.search(
        r"^\d\.\s+`source/docs/design-guidelines\.md`(?!-legacy)", priorities, re.MULTILINE
    )
    assert live_in_priorities is None, (
        "the live path must not appear in §0 priority list"
    )


def test_v31_section_13_2_8_marked_closed() -> None:
    source = _read(SOURCE_DOC)
    # §13.2 #8 closure marker should be present within the debt list.
    block_match = re.search(
        r"8\.\s+\*\*文档分叉\*\*.*?(?=\n\d\.\s+\*\*[^\*]+\*\*|\n已治理)",
        source,
        re.DOTALL,
    )
    assert block_match is not None, (
        "V3.1 §13.2 #8 (文档分叉) entry not found"
    )
    block = block_match.group(0)
    assert "已收敛" in block, (
        "V3.1 §13.2 #8 should carry 已收敛 closure marker"
    )
    assert "V3.2" in block, (
        "V3.1 §13.2 #8 closure should reference V3.2"
    )


def test_v31_has_section_14_5_remaining_debts() -> None:
    source = _read(SOURCE_DOC)
    assert "## 14.5" in source, (
        "V3.1 should include §14.5 V3.2 remaining debts"
    )
    section_14_5 = re.search(
        r"## 14\.5.*?(?=\n##\s|\Z)", source, re.DOTALL
    )
    assert section_14_5 is not None
    body = section_14_5.group(0)
    assert "H1→H2" in body or "H1" in body and "H2" in body
    assert "UI_UX_AUDIT" in body or "UI/UX_AUDIT" in body, (
        "§14.5 must list UI_UX_AUDIT path-split debt"
    )


def test_v31_no_obsolete_brand_color() -> None:
    """V3.1 must not regress to the legacy `--ink #1d2b3a` or `#14b8a6`
    brand that conflicted with `#66548e` editorial accent."""
    source = _read(SOURCE_DOC)
    bad_patterns = [
        "--ink #1d2b3a",
        "#14b8a6",  # legacy teal accent
    ]
    leaked: list[str] = []
    for p in bad_patterns:
        if p in source:
            leaked.append(p)
    assert not leaked, (
        f"V3.1 must not regress to legacy brand colors: {leaked}"
    )


def test_v31_no_obsolete_viewport_baseline() -> None:
    """V3.1 §11.1 viewport list must not promote 2560×1600 as a base — it's
    only allowed as a high-screen cross-check per §11.1."""
    source = _read(SOURCE_DOC)
    # Find §11.1 viewport list block.
    block = re.search(
        r"### 11\.1\s+验证视口.*?(?=### 11\.2|\n## )", source, re.DOTALL
    )
    assert block is not None, "V3.1 §11.1 验证视口 block not found"
    body = block.group(0)
    # Base line must be 2560×1440 (16:9). 2560×1600 may appear only when
    # framed as supplemental cross-check.
    assert "2560×1440" in body, "V3.1 §11.1 must declare 2560×1440 base"
    # Promotion phrases disqualify the file.
    promotion = re.search(r"主(?:视觉)?(?:基线)?(?:参考)?\s*[::]?\s*2560×1600", body)
    assert promotion is None, (
        "V3.1 §11.1 must not promote 2560×1600 as the main baseline"
    )
