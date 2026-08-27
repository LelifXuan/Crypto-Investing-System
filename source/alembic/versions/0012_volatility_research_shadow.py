"""append-only BTC volatility research shadow tables

Revision ID: 0012_volatility_research_shadow
Revises: 0011_drop_dead_structure_tables
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.db.types import ExactNumeric

revision = "0012_volatility_research_shadow"
down_revision = "0011_drop_dead_structure_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "volatility_research_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.String(),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.Column("integration_status", sa.String(length=32), nullable=False),
        sa.Column("price_volatility_json", sa.JSON(), nullable=False),
        sa.Column("options_expectations_json", sa.JSON(), nullable=False),
        sa.Column("tail_pricing_json", sa.JSON(), nullable=False),
        sa.Column("leverage_crowding_json", sa.JSON(), nullable=False),
        sa.Column("liquidation_pressure_json", sa.JSON(), nullable=False),
        sa.Column("basis_funding_structure_json", sa.JSON(), nullable=False),
        sa.Column("quality_json", sa.JSON(), nullable=False),
        sa.Column("timestamp_contract_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("instrument_id", "timeframe", "event_time", "formula_version", "integration_status"):
        op.create_index(
            f"ix_volatility_research_snapshots_{column}",
            "volatility_research_snapshots",
            [column],
        )

    op.create_table(
        "volatility_feature_observations",
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=64),
            sa.ForeignKey("volatility_research_snapshots.snapshot_id"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.String(),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("feature_key", sa.String(length=96), nullable=False),
        sa.Column("parameter_set_id", sa.String(length=64), nullable=False),
        sa.Column("value_num", ExactNumeric(38, 18), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("missing_reason", sa.String(length=160), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "snapshot_id",
            "feature_key",
            "parameter_set_id",
            name="uq_volatility_feature_snapshot_key_params",
        ),
    )
    for column in (
        "snapshot_id",
        "instrument_id",
        "timeframe",
        "feature_key",
        "event_time",
        "formula_version",
    ):
        op.create_index(
            f"ix_volatility_feature_observations_{column}",
            "volatility_feature_observations",
            [column],
        )


def downgrade() -> None:
    op.drop_table("volatility_feature_observations")
    op.drop_table("volatility_research_snapshots")
