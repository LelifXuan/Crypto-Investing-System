"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-04 00:00:00
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def upgrade() -> None:
    op.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute(
        """
        drop table if exists audit_logs cascade;
        drop table if exists market_event_instruments cascade;
        drop table if exists market_events cascade;
        drop table if exists indicator_values cascade;
        drop table if exists market_candles cascade;
        drop table if exists pnl_snapshots cascade;
        drop table if exists position_snapshots cascade;
        drop table if exists position_views cascade;
        drop table if exists mark_prices cascade;
        drop table if exists fx_rates cascade;
        drop table if exists funding_events cascade;
        drop table if exists cash_movements cascade;
        drop table if exists fills cascade;
        drop table if exists orders cascade;
        drop table if exists event_store cascade;
        drop table if exists instruments cascade;
        drop table if exists strategies cascade;
        drop table if exists accounts cascade;
        drop table if exists tenants cascade;
        """
    )
