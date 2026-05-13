from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarkPrice(Base):
    __tablename__ = "mark_prices"

    mark_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    mark_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "ts_open", "source", name="uq_market_candles_unique"),
    )

    candle_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    ts_open: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndicatorValue(Base):
    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "timeframe", "indicator_name", "params_hash", "ts_value",
            name="uq_indicator_values_unique"
        ),
    )

    indicator_value_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    indicator_name: Mapped[str] = mapped_column(String, nullable=False)
    params_hash: Mapped[str] = mapped_column(String, nullable=False)
    ts_value: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndicatorRefreshPolicy(Base):
    __tablename__ = "indicator_refresh_policies"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "timeframe", "price_kind", "source_preference",
            name="uq_indicator_refresh_policies_unique",
        ),
    )

    policy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    price_kind: Mapped[str] = mapped_column(String, nullable=False, default="last")
    source_preference: Mapped[str] = mapped_column(String, nullable=False, default="gateio")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    persist_candles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fetch_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    parameters_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MarketEvent(Base):
    __tablename__ = "market_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    reliability: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ts_ingest: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketEventInstrument(Base):
    __tablename__ = "market_event_instruments"

    event_id: Mapped[str] = mapped_column(ForeignKey("market_events.event_id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), primary_key=True)
