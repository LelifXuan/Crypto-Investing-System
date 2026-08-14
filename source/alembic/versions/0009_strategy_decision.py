"""strategy decision ledger

Revision ID: 0009_strategy_decision
Revises: 0008_computed_dataset_cache
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_strategy_decision"
down_revision = "0008_computed_dataset_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_decision",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("timeframe", sa.String(), nullable=False),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("execution_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("risk_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("capital_ceiling_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("position_side", sa.String(), nullable=True),
        sa.Column("position_notional", sa.Numeric(38, 18), nullable=True),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("config_version", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("conflict_json", sa.JSON(), nullable=False),
        sa.Column("action_plan_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("decision_id", name="uq_strategy_decision_id"),
    )
    for column in ["decision_id", "instrument_id", "timeframe", "decision_ts", "action", "direction", "position_side", "input_hash"]:
        op.create_index(f"ix_strategy_decision_{column}", "strategy_decision", [column])

    op.create_table(
        "strategy_decision_outcome",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("bars_1_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("bars_3_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("bars_6_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("bars_12_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("bars_24_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("fee_adjusted_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("slippage_adjusted_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("mfe", sa.Numeric(18, 8), nullable=True),
        sa.Column("mae", sa.Numeric(18, 8), nullable=True),
        sa.Column("stop_hit_first", sa.Boolean(), nullable=True),
        sa.Column("take_profit_hit_first", sa.Boolean(), nullable=True),
        sa.Column("confirmation_hit", sa.Boolean(), nullable=True),
        sa.Column("invalidation_hit", sa.Boolean(), nullable=True),
        sa.Column("review_label", sa.String(), nullable=True),
        sa.Column("attribution_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategy_decision_outcome_decision_id", "strategy_decision_outcome", ["decision_id"])

    op.create_table(
        "strategy_iteration_proposal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=True),
        sa.Column("timeframe", sa.String(), nullable=True),
        sa.Column("proposal_type", sa.String(), nullable=False),
        sa.Column("target_module", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False, server_default="medium"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("suggested_change_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("proposal_id", name="uq_strategy_iteration_proposal_id"),
    )
    for column in ["proposal_id", "instrument_id", "timeframe", "proposal_type", "status"]:
        op.create_index(f"ix_strategy_iteration_proposal_{column}", "strategy_iteration_proposal", [column])


def downgrade() -> None:
    op.drop_table("strategy_iteration_proposal")
    op.drop_table("strategy_decision_outcome")
    op.drop_table("strategy_decision")
