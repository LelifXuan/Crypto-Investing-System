"""strategy signal ledger tables

Revision ID: 0010_strategy_signal_tables
Revises: 0009_strategy_decision
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_strategy_signal_tables"
down_revision = "0009_strategy_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_signal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_key", sa.String(length=128), nullable=False),
        sa.Column("recommendation_id", sa.String(length=128), nullable=True),
        sa.Column("template_key", sa.String(length=128), nullable=True),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column("signal_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("signal_state", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("entry_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("take_profit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("position_size_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("signal_source", sa.String(length=64), nullable=False, server_default="ai_generated"),
        sa.Column("trigger_indicators_json", sa.JSON(), nullable=False),
        sa.Column("context_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("market_condition_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("signal_key", "timeframe", "signal_ts", name="uq_strategy_signal_unique"),
    )
    for column in [
        "signal_key",
        "recommendation_id",
        "template_key",
        "signal_type",
        "instrument_id",
        "timeframe",
        "signal_ts",
    ]:
        op.create_index(f"ix_strategy_signal_{column}", "strategy_signal", [column])

    op.create_table(
        "strategy_signal_outcome",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_key", sa.String(length=128), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("recommendation_id", sa.String(length=128), nullable=True),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column("signal_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("entry_ref_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("exit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("outcome_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("bars_1", sa.Integer(), nullable=True),
        sa.Column("bars_3", sa.Integer(), nullable=True),
        sa.Column("bars_6", sa.Integer(), nullable=True),
        sa.Column("bars_12", sa.Integer(), nullable=True),
        sa.Column("bars_24", sa.Integer(), nullable=True),
        sa.Column("return_1", sa.Numeric(18, 8), nullable=True),
        sa.Column("return_3", sa.Numeric(18, 8), nullable=True),
        sa.Column("return_6", sa.Numeric(18, 8), nullable=True),
        sa.Column("return_12", sa.Numeric(18, 8), nullable=True),
        sa.Column("return_24", sa.Numeric(18, 8), nullable=True),
        sa.Column("mfe", sa.Numeric(18, 8), nullable=True),
        sa.Column("mae", sa.Numeric(18, 8), nullable=True),
        sa.Column("fee_adjusted_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("slippage_adjusted_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("stop_hit_first", sa.Boolean(), nullable=True),
        sa.Column("take_profit_hit_first", sa.Boolean(), nullable=True),
        sa.Column("confirmation_hit", sa.Boolean(), nullable=True),
        sa.Column("invalidation_hit", sa.Boolean(), nullable=True),
        sa.Column("trailing_stop_activated", sa.Boolean(), nullable=True),
        sa.Column("atr_at_entry", sa.Numeric(18, 8), nullable=True),
        sa.Column("atr_at_exit", sa.Numeric(18, 8), nullable=True),
        sa.Column("risk_reward_actual", sa.Numeric(10, 4), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "signal_key",
            "timeframe",
            "signal_ts",
            name="uq_strategy_signal_outcome_unique",
        ),
    )
    for column in [
        "signal_key",
        "signal_type",
        "recommendation_id",
        "instrument_id",
        "timeframe",
        "signal_ts",
    ]:
        op.create_index(f"ix_strategy_signal_outcome_{column}", "strategy_signal_outcome", [column])

    op.create_table(
        "strategy_signal_review",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_key", sa.String(length=128), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("problem_type", sa.String(length=128), nullable=True),
        sa.Column("root_cause", sa.String(), nullable=True),
        sa.Column("affected_module", sa.String(length=128), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("suggested_fix", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategy_signal_review_signal_key", "strategy_signal_review", ["signal_key"])
    op.create_index("ix_strategy_signal_review_review_type", "strategy_signal_review", ["review_type"])
    op.create_index("ix_strategy_signal_review_problem_type", "strategy_signal_review", ["problem_type"])


def downgrade() -> None:
    op.drop_table("strategy_signal_review")
    op.drop_table("strategy_signal_outcome")
    op.drop_table("strategy_signal")
