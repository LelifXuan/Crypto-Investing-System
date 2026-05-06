from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashMovement(Base):
    __tablename__ = "cash_movements"

    movement_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    movement_type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FundingEvent(Base):
    __tablename__ = "funding_events"

    funding_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    payment: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FXRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "source", "ts_event", name="uq_fx_rates_unique"),
    )

    fx_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String, nullable=False)
    quote_currency: Mapped[str] = mapped_column(String, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PnLSnapshot(Base):
    __tablename__ = "pnl_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    fees: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    funding: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    slippage_cost: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    exposure_notional: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    formula_version: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
