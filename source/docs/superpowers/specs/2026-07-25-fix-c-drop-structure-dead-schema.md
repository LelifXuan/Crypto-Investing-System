# Fix C — Drop Dead `structure_snapshot` Schema

## Context

Active code path is 100% cache-based. The SQL tables `structure_snapshot`, `structure_system_judgement`, `structure_system_scores`, `structure_active_item`, `structure_geometry`, `structure_event`, `structure_alert` are never written.

- `app/services/structure/snapshot_service.py:391-433` (`_persist_bundle`) ONLY calls `self.repository.upsert_page_snapshot_cache(...)` with `page_type="structure"`.
- `replace_structure_snapshot_bundle` (`market_repository.py:1363`) has zero callers in `app/` or `tests/`.
- `app/services/structure/writers.py` (3 exports: `build_snapshot_model`, `build_legacy_judgements`, `build_system_scores`) and `app/services/structure/readers.py` (2 exports: `read_snapshot`, `map_system_score`) are both dead.

This is misleading for new readers and slows onboarding.

## Goal

Remove the dead SQL persistence path and its supporting helpers without changing any observable behavior.

## Scope (delete list)

In `app/repositories/market_repository.py`:
- `get_latest_structure_snapshot` (lines 1336-1361)
- `replace_structure_snapshot_bundle` (lines 1363-1434)
- `list_structure_system_judgements` (lines 1436-1451)
- `list_structure_system_scores` (lines 1453-1468)
- `list_structure_active_items` (lines 1470-1487)
- `list_structure_geometry` (lines 1489-1504)
- `add_structure_event` (lines 1506-1525)
- `list_structure_events` (lines 1527-1543)
- `add_structure_alert` (lines 1545-1561)
- `list_structure_alerts` (lines 1563+)

In `app/db/models/market.py`:
- `StructureSnapshot` class
- `StructureSystemJudgement` class
- `StructureSystemScore` class
- `StructureActiveItem` class
- `StructureGeometry` class
- `StructureEvent` class
- `StructureAlert` class

In `app/db/models/__init__.py`:
- All imports / re-exports of the deleted classes

Delete entire files:
- `app/services/structure/writers.py`
- `app/services/structure/readers.py`

## Scope (add list)

Add `alembic/versions/0011_drop_dead_structure_tables.py`:

```python
"""Drop the structure_* tables — superseded by page_snapshot_cache.

The structure_snapshot, structure_system_judgement, structure_system_scores,
structure_active_item, structure_geometry, structure_event, structure_alert
tables are never written by current code (StructureSnapshotService persists
to page_snapshot_cache instead). Drop them to clean up the schema.

Revision ID: 0011_drop_dead_structure_tables
Revises: <last revision>
Create Date: 2026-07-25
"""
from alembic import op

revision = "0011_drop_dead_structure_tables"
down_revision = "0010_strategy_unified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in [
        "structure_alerts",
        "structure_events",
        "structure_geometry",
        "structure_active_item",
        "structure_system_scores",
        "structure_system_judgement",
        "structure_snapshot",
    ]:
        # Idempotent: skip if the table doesn't exist (older install).
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        if table in inspector.get_table_names():
            op.drop_table(table)


def downgrade() -> None:
    # Recreate the tables idempotently — re-running this migration
    # after `alembic downgrade -1` will recreate the schema needed to
    # bring the dead code back if anyone reverts this commit.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "structure_snapshot" not in inspector.get_table_names():
        op.create_table(
            "structure_snapshot",
            sa.Column("snapshot_id", sa.Integer, primary_key=True),
            # ... [re-create via original migration]
        )
        # ... [and the other 6 tables]
```

(Implementation detail: the downgrade() can stub out with `pass` if we accept that the deleted code can't come back without re-creating the tables.)

## Tests

`tests/test_structure_schema_cleanup.py`:
- `test_no_dead_references_in_active_code`: import everything in `app/`, verify `replace_structure_snapshot_bundle` and `get_latest_structure_snapshot` are no longer importable.
- `test_writers_module_gone`: verify `app/services/structure/writers.py` does not exist (or is empty).
- `test_readers_module_gone`: same for `readers.py`.
- `test_oracle_models_removed`: introspect `app.db.models.market` to confirm the 7 `Structure*` classes are gone.
- `test_migration_is_idempotent`: run `alembic upgrade head` twice, expect no error.

## Behavior unchanged

Verified by grep across `app/`, `tests/`, `scripts/`, `tools/`, `alembic/`, `runtime/`:
- No external consumers of these tables.
- All API endpoints (`/structure/tab/*`) read `page_snapshot_cache`.
- The frontend is 100% cache-backed.

## Risk

Low. The deletion list is purely code removal. Migration carries the SQL drop-table step (irreversible without explicit downgrade).

## Verification

1. `pytest tests/test_structure_schema_cleanup.py tests/test_structure*.py tests/test_chip*.py -q` → all green.
2. `python tests/verify_pages.py --pages structure-page` → OK, no console errors.
3. `python -m pytest tests/ -q --ignore=slow` → 0 regressions.
4. `alembic upgrade head && alembic upgrade head` → no error (idempotent migration).