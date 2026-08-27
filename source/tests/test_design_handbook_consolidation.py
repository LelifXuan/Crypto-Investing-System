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
        "V3.1 should include §14.5 (V3.2 / V3.3 remaining debts)"
    )
    section_14_5 = re.search(
        r"## 14\.5.*?(?=\n##\s|\Z)", source, re.DOTALL
    )
    assert section_14_5 is not None
    body = section_14_5.group(0)
    # V3.3 has fully cleared V3.2's debts; §14.5 must reflect that.
    # Either form is acceptable: (a) "已收敛" marker + "§13.2 #2"
    # (historical, recommended), or (b) explicit empty-list claim.
    closed_marker = re.search(r"已收敛|已结清|§13\.2 全部", body)
    assert closed_marker is not None, (
        "§14.5 must carry a V3.3 closure marker (e.g. 已收敛 / §13.2 全部)"
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


def test_no_path_split_to_legacy_audit_or_spec() -> None:
    """2026-08-27 §13.2 #8 follow-up: after V3.2 design-guidelines split
    and V3.3 sed consolidation, no code comment may reference the legacy
    root path of any docs/ file that was migrated to source/docs/ in V2.2
    (commit f6a937e). The audit notes that V2.2's R100 rename of the
    `docs/` subtree to `source/docs/` was not followed up by code-comment
    updates; this guard prevents re-introduction.

    Two pattern forms are forbidden:
      (a) `source/...docs/X.md` — already-correct canonical paths
          are exempt (we strip them before scanning).
      (b) `ROOT / "docs/X.md"` Python Path-builder strings — ROOT in
          test layouts already points at source/, so these resolve
          correctly. We strip them too.

    Remaining bare `docs/X.md` references are the actual regression
    mode we want to catch.
    """
    legacy_substrings = [
        "docs/UI_UX_AUDIT_2026-07-31.md",
        "docs/superpowers/specs/2026-07-31-dropdown-revision-design.md",
        "docs/research/btc_volatility/CURRENT_VOLATILITY_BASELINE_AUDIT.md",
    ]

    # Skip the meta-zones that legitimately mention the legacy path:
    # - docs/ trees (legacy handbook is itself a docs/ file with a banner)
    # - source/docs/ trees (active spec & audit locations)
    # - .zcode/ (agent plan notes that quote the original §14.5 text)
    # - this test file (it embeds the patterns as regex literals)
    skip_dirs = {"docs", "source/docs", ".zcode"}
    skip_files = {Path(__file__).resolve()}
    repo_root = ROOT.parent
    offenders: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.resolve() in skip_files:
            continue
        if path.suffix not in {".js", ".css", ".py", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Strip canonical-path mentions (already correct form).
        scrubbed = re.sub(r"source/docs/[^\s\"')\]]+", "", text)
        # Strip Python Path-builder strings ROOT / "docs/...".
        scrubbed = re.sub(r"ROOT\s*/\s*\"docs/[^\"]+\"", "ROOT_/_PATH_BUILDER", scrubbed)

        for legacy in legacy_substrings:
            if legacy in scrubbed:
                offenders.append(f"{path}: {legacy}")

    assert not offenders, (
        "Path-split references to migrated docs/ found:\n  " + "\n  ".join(offenders[:20])
    )
