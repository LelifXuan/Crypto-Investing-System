from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.repositories.market_repository import MarketRepository
from app.schemas.gold_allocation import (
    GoldAllocationPlanRequest,
    GoldAllocationPlanResponse,
    GoldExecutionPlanRequest,
    GoldExecutionPlanResponse,
    GoldMarketStateResponse,
)
from app.services.gold_allocation_engine import build_gold_allocation_plan
from app.services.gold_dca_dip import (
    GoldExecutionComposer,
    GoldExecutionState,
    GoldSettings,
    QuoteSnapshot,
    build_indicator_snapshot,
    indicator_from_mapping,
    normalize_candle,
    now_utc,
)
from app.services.gold_macro_adapter import _gold_macro_snapshot, macro_overview_to_gold_macro
from app.schemas.gold_v3 import (
    GoldContractRef,
    GoldIndicatorConfirmation,
    GoldSignalLight,
    GoldSpotDca,
    GoldV3AllocationResponse,
)
from app.services.gold_derivatives import GoldDerivativesService
from app.services.macro_overview import MacroOverviewService
from app.services.xaut_market_state import XAUT_INSTRUMENT_ID, XautMarketStateService

router = APIRouter(prefix="/gold", tags=["gold"])


def _repository(session: AsyncSession | None) -> MarketRepository | None:
    return MarketRepository(session) if session is not None else None


async def _macro_payload(repo: MarketRepository | None) -> dict:
    if repo is None:
        return {}
    try:
        overview = await MacroOverviewService(repo).build_overview()
    except Exception:
        return {}
    return macro_overview_to_gold_macro(overview)


async def _market_state(repo: MarketRepository | None, *, force: bool = False) -> dict:
    return await XautMarketStateService(repo).build_state(force=force)


def _compute_technical_indicators(candles: list) -> dict:
    """Compute RSI(14), Bollinger %B(20,2), EMA20 distance, CCI(20) from candles.

    Returns empty dict if < 21 candles (not enough data for 20-period indicators).
    """
    if len(candles) < 21:
        return {}

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    typicals = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]

    # ── RSI(14) ──
    rsi = _compute_rsi(closes, 14)

    # ── Bollinger %B (20, 2) ──
    boll = _compute_bollinger_pct_b(closes, 20, 2)

    # ── EMA20 distance ──
    ema20 = _compute_ema(closes, 20)
    ema20_dist = (closes[-1] - ema20) / ema20 if ema20 and ema20 != 0 else None

    # ── CCI(20) ──
    cci = _compute_cci(typicals, closes, 20)

    return {
        "rsi_14": rsi,
        "boll_pct_b": boll,
        "ema20_distance": ema20_dist,
        "cci_20": cci,
    }


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's smoothed RSI."""
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[-(period + 1) + i] - closes[-(period + 1) + i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_ema(values: list[float], period: int) -> float | None:
    """Exponential moving average."""
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return ema


def _compute_bollinger_pct_b(closes: list[float], period: int = 20, num_std: float = 2.0) -> float | None:
    """Bollinger %B = (price - lower) / (upper - lower). 0 = at lower band, 1 = at upper band."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    sma = sum(window) / period
    variance = sum((v - sma) ** 2 for v in window) / period
    std = variance ** 0.5
    upper = sma + num_std * std
    lower = sma - num_std * std
    if upper == lower:
        return 0.5
    return (closes[-1] - lower) / (upper - lower)


def _compute_cci(typicals: list[float], closes: list[float], period: int = 20) -> float | None:
    """Commodity Channel Index. Uses typical price for mean, close for deviation."""
    if len(typicals) < period:
        return None
    window = typicals[-period:]
    sma = sum(window) / period
    mean_dev = sum(abs(tp - sma) for tp in window) / period
    if mean_dev == 0:
        return 0.0
    return (typicals[-1] - sma) / (0.015 * mean_dev)


def _aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=None).astimezone()
    return value


def _settings(payload: GoldExecutionPlanRequest) -> GoldSettings:
    values = {
        "daily_dca_amount": payload.daily_dca_amount,
        "dip_add_amount": payload.dip_add_amount,
        "cooldown_days": payload.cooldown_days,
        "quote_max_age_seconds": payload.quote_max_age_seconds,
        "available_cash": payload.available_cash,
    }
    if payload.settings is not None:
        values.update(payload.settings.model_dump(exclude_none=True))
    return GoldSettings(**values)


async def _execution_inputs(
    payload: GoldExecutionPlanRequest,
    repo: MarketRepository | None,
) -> tuple[QuoteSnapshot, object | None, dict]:
    diagnostics: dict = {"source": "request_override" if payload.quote else "xaut_daily_cache"}
    candles = [
        item
        for item in (normalize_candle(item) for item in (payload.candles or []))
        if item
    ]
    if not candles and repo is not None:
        try:
            candles = [
                item
                for item in (
                    normalize_candle(candle)
                    for candle in await repo.list_candles(XAUT_INSTRUMENT_ID, "1d", limit=260)
                )
                if item
            ]
        except Exception:
            candles = []
    indicators = indicator_from_mapping(payload.indicators) or build_indicator_snapshot(candles)
    if payload.quote is not None:
        quote = QuoteSnapshot(
            price=payload.quote.price,
            updated_at=_aware(payload.quote.updated_at),
        )
    elif candles:
        latest = candles[-1]
        quote = QuoteSnapshot(price=latest.close, updated_at=_aware(latest.ts))
    else:
        quote = QuoteSnapshot(price=0.0, updated_at=now_utc().replace(year=1970))
    diagnostics["candle_count"] = len(candles)
    diagnostics["has_indicators"] = indicators is not None
    return quote, indicators, diagnostics


@router.post("/allocation/plan", response_model=GoldAllocationPlanResponse)
async def plan_gold_allocation(
    payload: GoldAllocationPlanRequest,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldAllocationPlanResponse:
    try:
        plan = build_gold_allocation_plan(
            payload.portfolio.model_dump(),
            macro=payload.macro or {},
            goldhub=payload.goldhub or {},
            market=payload.market or {},
            options=payload.options.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GoldAllocationPlanResponse.model_validate(plan.to_dict())


@router.post("/execution-plan", response_model=GoldExecutionPlanResponse)
async def plan_gold_execution(
    payload: GoldExecutionPlanRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldExecutionPlanResponse:
    repo = _repository(session)
    now = _aware(payload.now) if payload.now else now_utc()
    quote, indicators, input_diagnostics = await _execution_inputs(payload, repo)
    plan = GoldExecutionComposer().compose(
        symbol=payload.symbol,
        quote=quote,
        now=now,
        settings=_settings(payload),
        state=GoldExecutionState(
            executed_today=payload.executed_today,
            last_dip_add_date=payload.last_dip_add_date,
            last_dip_cycle_id=payload.last_dip_cycle_id,
        ),
        indicators=indicators,
    ).to_dict()
    plan["diagnostics"].update(input_diagnostics)
    return GoldExecutionPlanResponse.model_validate(plan)


@router.get("/market-state", response_model=GoldMarketStateResponse)
async def get_gold_market_state(
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldMarketStateResponse:
    state = await _market_state(_repository(session), force=force)
    return GoldMarketStateResponse.model_validate(state)


@router.get("/allocation", response_model=GoldAllocationPlanResponse)
async def get_gold_allocation(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldAllocationPlanResponse:
    repo = _repository(session)
    portfolio = {
        "total_portfolio_value": 200_000,
        "current_gold_value": 10_000,
        "monthly_new_cash": 5_000,
        "current_gold_cost": 9_500,
        "is_quarterly_rebalance_month": False,
    }
    plan = build_gold_allocation_plan(
        portfolio,
        macro=await _macro_payload(repo),
        goldhub={},
        market=await _market_state(repo),
    )
    return GoldAllocationPlanResponse.model_validate(plan.to_dict())


@router.get("/v3/allocation", response_model=GoldV3AllocationResponse)
async def get_gold_v3_allocation(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldV3AllocationResponse:
    """V3 gold allocation — simplified two-layer model."""
    repo = _repository(session)
    macro_payload = await _macro_payload(repo)
    market_state = await _market_state(repo)
    macro_snapshot = _gold_macro_snapshot(macro_payload or {})

    # ── Build 3 signal lights ──
    _SIGNAL_LIGHT_META = {
        "real_yield_10y": ("实际利率", "TIPS 10Y"),
        "dxy": ("美元指数", "DXY"),
        "vix": ("波动率", "VIX"),
    }
    signals = []
    for key in ("real_yield_10y", "dxy", "vix"):
        data = macro_snapshot.get(key, {})
        label, code = _SIGNAL_LIGHT_META.get(key, (key, key.upper()))
        signals.append(GoldSignalLight(
            key=key,
            label=data.get("display_label", label),
            code=code,
            value=data.get("value"),
            unit=data.get("unit", ""),
            bias=data.get("bias", "missing"),
            bias_label={
                "strong_bullish": "强势看多", "bullish": "看多",
                "neutral": "中性", "bearish": "看空",
                "strong_bearish": "强势看空", "missing": "数据不足",
            }.get(data.get("bias", "missing"), "中性"),
            bias_reason=data.get("bias_reason", ""),
            source=data.get("source", ""),
        ))

    # ── Spot summary ──
    bearish_count = sum(1 for s in signals if s.bias in {"bearish", "strong_bearish"})
    bullish_count = sum(1 for s in signals if s.bias in {"bullish", "strong_bullish"})
    if bearish_count >= 2:
        spot_summary = "⚠ 偏谨慎 — 宏观逆风，建议维持基础定投不追高"
    elif bullish_count >= 2:
        spot_summary = "✅ 偏积极 — 宏观友好，可考虑适当增加定投"
    else:
        spot_summary = "➖ 中性 — 宏观不形成方向性约束，按既定纪律执行"

    liquidity_shock = macro_snapshot.get("_diagnostics", {}).get("liquidity_shock_detected", False)

    # ── Spot DCA ──
    current_weight = 10_000 / 200_000  # 0.05, matching existing V2 default
    tips_val = macro_snapshot.get("real_yield_10y", {}).get("value")
    dxy_val = macro_snapshot.get("dxy", {}).get("value")

    # Target range from TIPS + DXY
    if tips_val is not None and tips_val <= 0.5:
        target_min, target_max = 0.10, 0.15
    elif tips_val is not None and tips_val <= 1.5:
        if dxy_val is not None and dxy_val >= 105:
            target_min, target_max = 0.05, 0.08
        else:
            target_min, target_max = 0.08, 0.12
    elif tips_val is not None and tips_val < 2.0:
        target_min, target_max = 0.05, 0.08
    elif tips_val is not None and tips_val < 2.8:
        if dxy_val is not None and dxy_val >= 108:
            target_min, target_max = 0.03, 0.05
        else:
            target_min, target_max = 0.05, 0.08
    else:
        target_min, target_max = 0.0, 0.03

    weight_state = "underweight" if current_weight < target_min else (
        "overweight" if current_weight > target_max else "within_range"
    )
    if current_weight <= target_min + 0.005:
        weight_state = "at_min"

    base_amount = 500.0
    dip_multiplier = 2.0

    # Macro gate
    tips_ok = tips_val is not None and tips_val < 2.8
    dxy_ok = dxy_val is None or dxy_val < 108
    macro_gate_passed = tips_ok and dxy_ok

    # Drawdown trigger
    drawdown_60d = market_state.get("drawdown_60d")
    drawdown_threshold = 0.08
    drawdown_triggered = drawdown_60d is not None and abs(drawdown_60d) >= drawdown_threshold

    # Indicator confirmations — compute from candles
    candles = []
    if repo is not None:
        try:
            candles = [
                item for item in (
                    normalize_candle(c) for c in await repo.list_candles(XAUT_INSTRUMENT_ID, "1d", limit=260)
                ) if item
            ]
        except Exception:
            candles = []
    tech = _compute_technical_indicators(candles) if len(candles) >= 21 else {}
    vol_z = market_state.get("volume_zscore")

    rsi_val = tech.get("rsi_14")
    boll_val = tech.get("boll_pct_b")
    ema20_dist = tech.get("ema20_distance")
    cci_val = tech.get("cci_20")

    confirmations = [
        GoldIndicatorConfirmation(
            label="RSI(14)", value=rsi_val,
            display=f"{rsi_val:.0f}" if rsi_val is not None else "—",
            condition="≤40", passed=(rsi_val is not None and rsi_val <= 40),
        ),
        GoldIndicatorConfirmation(
            label="布林位置", value=boll_val,
            display=f"{boll_val:.2f}" if boll_val is not None else "—",
            condition="≤0.2", passed=(boll_val is not None and boll_val <= 0.2),
        ),
        GoldIndicatorConfirmation(
            label="距EMA20", value=ema20_dist,
            display=f"{ema20_dist * 100:.1f}%" if ema20_dist is not None else "—",
            condition="≤-2%", passed=(ema20_dist is not None and ema20_dist <= -0.02),
        ),
        GoldIndicatorConfirmation(
            label="CCI(20)", value=cci_val,
            display=f"{cci_val:.0f}" if cci_val is not None else "—",
            condition="≤-80", passed=(cci_val is not None and cci_val <= -80),
        ),
        GoldIndicatorConfirmation(
            label="成交量", value=vol_z,
            display=f"Z={vol_z:.1f}" if vol_z is not None else "—",
            condition="Z≥1.5", passed=(vol_z is not None and vol_z >= 1.5),
        ),
    ]
    confirmations_passed = sum(1 for c in confirmations if c.passed)

    # Recommendation
    if not macro_gate_passed:
        recommended = 0.0
        reason = "暂停定投（宏观门禁关闭：利率过高或美元过强）"
    elif drawdown_triggered and confirmations_passed >= 3:
        recommended = base_amount + base_amount * dip_multiplier
        reason = f"基础定投 + 加仓（回撤触发 + 指标确认 {confirmations_passed}/5）"
    elif drawdown_triggered:
        recommended = base_amount
        reason = f"基础定投（加仓未触发：指标确认 {confirmations_passed}/5 不满足）"
    else:
        recommended = base_amount
        reason = "基础定投（回撤未触发）"

    spot = GoldSpotDca(
        current_weight=current_weight,
        target_min=target_min,
        target_max=target_max,
        weight_state=weight_state,
        base_amount=base_amount,
        dip_multiplier=dip_multiplier,
        macro_gate_passed=macro_gate_passed,
        macro_gate_reason=f"TIPS<2.8%{' AND DXY<108' if dxy_ok else ' BUT DXY≥108'}",
        drawdown_triggered=drawdown_triggered,
        drawdown_60d=drawdown_60d,
        drawdown_threshold=drawdown_threshold,
        indicator_confirmations=confirmations,
        confirmations_passed=confirmations_passed,
        confirmations_required=3,
        recommended_amount=round(recommended, 2),
        recommendation_reason=reason,
    )

    contract = GoldContractRef(
        price=market_state.get("price"),
        above_ma50=market_state.get("above_ma50"),
        ma50_value=market_state.get("sma_50"),
        above_ma200=market_state.get("above_ma200"),
        ma200_value=market_state.get("sma_200"),
        drawdown_60d=drawdown_60d,
        natr_14=market_state.get("natr_14"),
        volume_zscore=market_state.get("volume_zscore"),
        updated_at=market_state.get("updated_at") or "",
    )

    return GoldV3AllocationResponse(
        signals=signals,
        spot_summary=spot_summary,
        liquidity_shock_detected=liquidity_shock,
        spot=spot,
        contract=contract,
    )


@router.get("/derivatives")
async def get_gold_derivatives(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict:
    """Gate.io OI/funding rate + local COT snapshot."""
    return await GoldDerivativesService().build_snapshot()
