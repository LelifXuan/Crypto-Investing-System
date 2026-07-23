from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy import select

from app.core.decimal_utils import D
from app.db.models.market import StrategySignal, StrategySignalOutcome
from app.repositories.market_repository import MarketRepository

UTC = timezone.utc


class StrategyOutcomeEngine:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def update_signal_outcomes(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        stmt = select(StrategySignal).where(
            StrategySignal.signal_type == "market_strategy_signal",
            StrategySignal.direction.in_(["long", "short"]),
        )
        if instrument_id:
            stmt = stmt.where(StrategySignal.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(StrategySignal.timeframe == timeframe)
        stmt = stmt.order_by(StrategySignal.signal_ts.desc()).limit(limit)
        result = await self.repository.session.execute(stmt)
        signals = list(result.scalars().all())

        updated = 0
        skipped = 0
        for signal in signals:
            outcome = await self.build_outcome_for_signal(signal)
            if outcome is not None:
                existing = await self._get_existing_outcome(
                    signal.signal_key,
                    signal.timeframe,
                    signal.signal_ts,
                )
                if existing is not None:
                    self._merge_outcome(existing, outcome)
                else:
                    self.repository.session.add(outcome)
                updated += 1
            else:
                skipped += 1

        if updated > 0:
            await self.repository.session.flush()

        return {"updated": updated, "skipped": skipped, "total": len(signals)}

    async def build_outcome_for_signal(
        self, signal: StrategySignal
    ) -> StrategySignalOutcome | None:
        if signal.direction not in ("long", "short"):
            return None
        entry = float(signal.entry_price or 0)
        if entry <= 0:
            return None

        candles = await self.repository.list_candles_filtered(
            instrument_id=signal.instrument_id,
            timeframe=signal.timeframe,
            limit=200,
            from_ts=signal.signal_ts,
            ascending=True,
        )
        windows = [1, 3, 6, 12, 24]
        if not candles or len(candles) < max(windows):
            return self._insufficient_outcome(signal)

        return self._build_full_outcome(signal, candles, entry, windows)

    def _build_full_outcome(
        self,
        signal: StrategySignal,
        candles: list,
        entry: float,
        windows: list[int],
    ) -> StrategySignalOutcome:
        side = 1 if signal.direction == "long" else -1
        stop = float(signal.stop_loss_price or 0)
        tp1 = float(signal.take_profit_price or 0)
        tp2 = float(signal.metadata_json.get("take_profit_2") or 0) if signal.metadata_json else 0

        closes = [float(getattr(c, "close", c[-1] if isinstance(c, list) else 0)) for c in candles]
        highs = [float(getattr(c, "high", c[-1] if isinstance(c, list) else 0)) for c in candles]
        lows = [float(getattr(c, "low", c[-1] if isinstance(c, list) else 0)) for c in candles]

        window_returns = {}
        for w in windows:
            idx = min(w, len(candles)) - 1
            if idx >= 0:
                future_close = closes[idx]
                ret = side * (future_close - entry) / entry if entry > 0 else 0
                window_returns[f"bars_{w}"] = idx + 1
                window_returns[f"return_{w}"] = round(ret, 8)
            else:
                window_returns[f"bars_{w}"] = 0
                window_returns[f"return_{w}"] = None

        if signal.direction == "long":
            mfe = max(h / entry - 1 for h in highs)
            mae = min(low_val / entry - 1 for low_val in lows)
            sl_hit = any(low_val <= stop for low_val in lows) if stop > 0 else False
            tp1_hit = any(h >= tp1 for h in highs) if tp1 > 0 else False
            tp2_hit = any(h >= tp2 for h in highs) if tp2 > 0 else False
        else:
            mfe = max((entry - low_val) / entry for low_val in lows)
            mae = min((entry - h) / entry for h in highs)
            sl_hit = any(h >= stop for h in highs) if stop > 0 else False
            tp1_hit = any(low_val <= tp1 for low_val in lows) if tp1 > 0 else False
            tp2_hit = any(low_val <= tp2 for low_val in lows) if tp2 > 0 else False

        payload: dict[str, Any] = {}
        status = "active"
        stop_first = None
        tp_first = None
        ambiguous = False

        if sl_hit and (tp1_hit or tp2_hit):
            sl_bars = self._first_hit_bar(signal.direction, candles, "stop", stop)
            tp_bars = self._first_hit_bar(signal.direction, candles, "tp", tp1 if tp1 > 0 else tp2)
            if sl_bars == tp_bars and sl_bars is not None:
                ambiguous = True
                status = "active"
                payload["hit_order"] = "ambiguous_same_bar"
            elif sl_bars is not None and (tp_bars is None or sl_bars < tp_bars):
                stop_first = True
                tp_first = False
                status = "stop_hit"
            else:
                stop_first = False
                tp_first = True
                status = "tp1_hit" if tp1_hit else "tp2_hit"
        elif sl_hit:
            stop_first = True
            status = "stop_hit"
        elif tp1_hit:
            tp_first = True
            status = "tp1_hit"
        elif tp2_hit:
            tp_first = True
            status = "tp2_hit"

        if ambiguous:
            payload["sl_hit_bar"] = sl_bars
            payload["tp_hit_bar"] = tp_bars

        return StrategySignalOutcome(
            signal_key=signal.signal_key,
            signal_type=signal.signal_type,
            recommendation_id=signal.recommendation_id,
            instrument_id=signal.instrument_id,
            timeframe=signal.timeframe,
            signal_ts=signal.signal_ts,
            direction=signal.direction,
            entry_ref_price=D(str(entry)),
            outcome_status=status,
            bars_1=window_returns.get("bars_1"),
            bars_3=window_returns.get("bars_3"),
            bars_6=window_returns.get("bars_6"),
            bars_12=window_returns.get("bars_12"),
            bars_24=window_returns.get("bars_24"),
            return_1=D(str(window_returns["return_1"])) if window_returns.get("return_1") is not None else None,
            return_3=D(str(window_returns["return_3"])) if window_returns.get("return_3") is not None else None,
            return_6=D(str(window_returns["return_6"])) if window_returns.get("return_6") is not None else None,
            return_12=D(str(window_returns["return_12"])) if window_returns.get("return_12") is not None else None,
            return_24=D(str(window_returns["return_24"])) if window_returns.get("return_24") is not None else None,
            mfe=D(str(round(mfe, 8))),
            mae=D(str(round(mae, 8))),
            stop_hit_first=stop_first,
            take_profit_hit_first=tp_first,
            payload_json=payload,
        )

    def _insufficient_outcome(self, signal: StrategySignal) -> StrategySignalOutcome:
        return StrategySignalOutcome(
            signal_key=signal.signal_key,
            signal_type=signal.signal_type,
            recommendation_id=signal.recommendation_id,
            instrument_id=signal.instrument_id,
            timeframe=signal.timeframe,
            signal_ts=signal.signal_ts,
            direction=signal.direction,
            outcome_status="insufficient_data",
            entry_ref_price=signal.entry_price,
        )

    @staticmethod
    def _first_hit_bar(direction: str, candles: list, hit_type: str, price: float) -> int | None:
        for i, c in enumerate(candles):
            high = float(getattr(c, "high", 0))
            low = float(getattr(c, "low", 0))
            if direction == "long":
                if hit_type == "stop" and low <= price:
                    return i + 1
                if hit_type == "tp" and high >= price:
                    return i + 1
            else:
                if hit_type == "stop" and high >= price:
                    return i + 1
                if hit_type == "tp" and low <= price:
                    return i + 1
        return None

    async def _get_existing_outcome(
        self,
        signal_key: str,
        timeframe: str,
        signal_ts,
    ) -> StrategySignalOutcome | None:
        result = await self.repository.session.execute(
            select(StrategySignalOutcome).where(
                StrategySignalOutcome.signal_key == signal_key,
                StrategySignalOutcome.timeframe == timeframe,
                StrategySignalOutcome.signal_ts == signal_ts,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _merge_outcome(existing: StrategySignalOutcome, new: StrategySignalOutcome) -> None:
        existing.outcome_status = new.outcome_status
        existing.return_1 = new.return_1
        existing.return_3 = new.return_3
        existing.return_6 = new.return_6
        existing.return_12 = new.return_12
        existing.return_24 = new.return_24
        existing.bars_1 = new.bars_1
        existing.bars_3 = new.bars_3
        existing.bars_6 = new.bars_6
        existing.bars_12 = new.bars_12
        existing.bars_24 = new.bars_24
        existing.mfe = new.mfe
        existing.mae = new.mae
        existing.stop_hit_first = new.stop_hit_first
        existing.take_profit_hit_first = new.take_profit_hit_first
        existing.entry_ref_price = new.entry_ref_price
        existing.payload_json = new.payload_json
