from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, PrimaryKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Fill(Base):
    __tablename__ = "fills"
    __table_args__ = (UniqueConstraint("source", "account_id", "fill_id", name="uq_fills_source_account_fill"),)

    fill_pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fill_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    fee_currency: Mapped[str] = mapped_column(String, nullable=False)
    liquidity: Mapped[str] = mapped_column(String, nullable=False, default="UNKNOWN")
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ts_ingest: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositionView(Base):
    __tablename__ = "position_views"
    __table_args__ = (
        PrimaryKeyConstraint("account_id", "strategy_id", "instrument_id", "cost_method", name="pk_position_views"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    cost_method: Mapped[str] = mapped_column(String, nullable=False)
    net_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    avg_cost_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    gross_notional: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    realized_pnl_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    unrealized_pnl_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    margin_used: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    leverage: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
