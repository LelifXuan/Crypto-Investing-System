"""Fix C (2026-07-25) — verify dead structure_snapshot schema is gone.

The 7 structure_* SQL tables were never written by current code
(StructureSnapshotService persists to page_snapshot_cache). Their
Python plumbing — repository methods, ORM models, helpers — is also
dead.

These tests verify the dead code has been removed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_market_repository_has_no_structure_snapshot_writer():
    """`replace_structure_snapshot_bundle` is gone — the only writer
    to the dead tables. Active code persists to page_snapshot_cache
    via `upsert_page_snapshot_cache`."""
    import app.repositories.market_repository as mr

    for name in [
        "replace_structure_snapshot_bundle",
        "get_latest_structure_snapshot",
        "list_structure_system_judgements",
        "list_structure_system_scores",
        "list_structure_active_items",
        "list_structure_geometry",
        "list_structure_events",
        "list_structure_alerts",
        "add_structure_event",
        "add_structure_alert",
    ]:
        assert not hasattr(mr.MarketRepository, name), (
            f"MarketRepository.{name} should be removed (dead code)"
        )


def test_market_repository_does_not_import_structure_models():
    """The deleted ORM classes must not appear in the repository import
    block."""
    source = (ROOT / "app/repositories/market_repository.py").read_text(
        encoding="utf-8"
    )
    for name in [
        "StructureSnapshot",
        "StructureSystemJudgement",
        "StructureSystemScore",
        "StructureActiveItem",
        "StructureGeometry",
        "StructureEvent",
        "StructureAlert",
    ]:
        assert name not in source, (
            f"market_repository.py should not import {name}"
        )


def test_db_models_market_has_no_structure_classes():
    """The 7 dead ORM classes must be removed from app/db/models/market.py."""
    import app.db.models.market as m

    for name in [
        "StructureSnapshot",
        "StructureSystemJudgement",
        "StructureSystemScore",
        "StructureActiveItem",
        "StructureGeometry",
        "StructureEvent",
        "StructureAlert",
    ]:
        assert not hasattr(m, name), f"app.db.models.market.{name} should be removed"


def test_db_models_init_does_not_export_structure_classes():
    """__all__ + import block of app/db/models/__init__.py must not
    expose the dead classes."""
    source = (ROOT / "app/db/models/__init__.py").read_text(encoding="utf-8")
    for name in [
        "StructureSnapshot",
        "StructureSystemJudgement",
        "StructureSystemScore",
        "StructureActiveItem",
        "StructureGeometry",
        "StructureEvent",
        "StructureAlert",
    ]:
        assert name not in source, (
            f"app/db/models/__init__.py must not export {name}"
        )


def test_writers_module_deleted():
    """app/services/structure/writers.py contained dead ORM builders
    with zero callers. File must be gone."""
    p = ROOT / "app/services/structure/writers.py"
    assert not p.exists(), "writers.py should be deleted (dead code)"


def test_readers_module_deleted():
    """app/services/structure/readers.py contained dead read helpers
    with zero callers. File must be gone."""
    p = ROOT / "app/services/structure/readers.py"
    assert not p.exists(), "readers.py should be deleted (dead code)"


def test_active_structure_modules_remain():
    """Sanity check: the actually-active structure modules are intact.
    We deliberately kept them — they power the structure page."""
    active = [
        "classic.py",
        "common.py",
        "diagnostics.py",
        "events.py",
        "fusion.py",
        "pivots.py",
        "profile.py",
        "snapshot.py",
        "snapshot_service.py",
        "swing.py",
        "text_logic.py",
        "__init__.py",
    ]
    for name in active:
        assert (ROOT / f"app/services/structure/{name}").exists(), (
            f"active structure module {name} must remain"
        )
