from __future__ import annotations

# ruff: noqa: E501
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

DataQuality = Literal["direct", "partial", "proxy", "missing"]
AllocationEffect = Literal["increase", "maintain", "pause", "split_add", "reduce", "watch"]


WEIGHTS = {
    "macro_monetary_environment": 0.25,
    "official_reserve_demand": 0.18,
    "supply_rigidity": 0.12,
    "portfolio_hedging_need": 0.15,
    "liquidity_selloff_rebound": 0.12,
    "derivatives_pressure": 0.12,
    "xaut_price_state": 0.06,
}


@dataclass(slots=True)
class WindowView:
    label: str
    headline: str
    facts: list[str]
    interpretation: str
    data_quality: DataQuality = "direct"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModuleCard:
    key: str
    title: str
    score: float
    confidence: float
    state: str
    data_quality: DataQuality
    headline: str
    facts: list[str]
    interpretation: str
    allocation_effect: AllocationEffect
    warnings: list[str] = field(default_factory=list)
    window_views: dict[str, WindowView] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(float(self.score), 1)
        data["confidence"] = round(float(self.confidence), 2)
        data["window_views"] = {
            key: value.to_dict() if isinstance(value, WindowView) else value
            for key, value in self.window_views.items()
        }
        return data


@dataclass(slots=True)
class PortfolioInput:
    total_portfolio_value: float
    current_gold_value: float
    monthly_new_cash: float = 0.0
    current_gold_cost: float | None = None
    is_quarterly_rebalance_month: bool = False
    crypto_weight: float | None = None
    us_equity_weight: float | None = None
    a_share_weight: float | None = None
    halo_etf_weight: float | None = None
    cashflow_etf_weight: float | None = None

    @property
    def current_weight(self) -> float:
        if self.total_portfolio_value <= 0:
            return 0.0
        return max(0.0, self.current_gold_value / self.total_portfolio_value)


@dataclass(slots=True)
class AllocationOptions:
    base_currency: str = "元"
    allow_quarterly_sell: bool = True
    max_monthly_gold_cash_fraction: float = 0.6
    prefer_staged_execution: bool = True
    material_overweight_threshold: float = 0.02


@dataclass(slots=True)
class AllocationPlan:
    allocation_state: str
    allocation_score: float
    target_range: dict[str, float]
    current_weight: float
    gap_to_target_min: float
    gap_above_target_max: float
    suggested_this_month: float
    execution_style: str
    primary_instruction: str
    decision_summary: str
    reasoning_steps: list[str]
    module_cards: list[dict[str, Any]]
    data_quality: dict[str, Any]
    warnings: list[str]
    drivers: dict[str, Any]
    asset_impact_summary: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        target_min = self.target_range["min"]
        target_max = self.target_range["max"]
        data.update(
            {
                "allocation_score": round(float(self.allocation_score), 1),
                "target_range": {"min": round(target_min, 4), "max": round(target_max, 4)},
                "current_weight": round(float(self.current_weight), 4),
                "gap_to_target_min": round(float(self.gap_to_target_min), 2),
                "gap_above_target_max": round(float(self.gap_above_target_max), 2),
                "suggested_this_month": round(float(self.suggested_this_month), 2),
                "target_weight_min": round(target_min, 4),
                "target_weight_max": round(target_max, 4),
                "gap_to_min_amount": round(float(self.gap_to_target_min), 2),
                "overweight_above_max_amount": round(float(self.gap_above_target_max), 2),
                "suggested_this_month_amount": round(float(self.suggested_this_month), 2),
                "summary": self.decision_summary,
                "risk_notes": list(self.warnings),
                "action": _legacy_action(self.allocation_state, self.execution_style),
            }
        )
        return data


def clamp(value: float | None, lo: float = 0.0, hi: float = 100.0) -> float:
    if value is None:
        return lo
    number = float(value)
    if not math.isfinite(number):
        return lo
    return max(lo, min(hi, number))


def _as_float(payload: Mapping[str, Any] | None, *keys: str) -> float | None:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def _ratio(payload: Mapping[str, Any] | None, *keys: str) -> float | None:
    value = _as_float(payload, *keys)
    if value is None:
        return None
    return value / 100 if abs(value) > 1 else value


def _nested(payload: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    value = (payload or {}).get(key)
    return value if isinstance(value, Mapping) else {}


def _iter_dicts(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value or [] if isinstance(item, Mapping)]


def _fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def _fmt_money(value: float, currency: str) -> str:
    return f"{value:,.0f}{currency}"


def _quality_from_present(present: int, total: int) -> DataQuality:
    if present <= 0:
        return "missing"
    if present < total:
        return "partial"
    return "direct"


def _confidence(quality: DataQuality, base: float = 0.75) -> float:
    factors = {"direct": 1.0, "proxy": 0.8, "partial": 0.58, "missing": 0.22}
    return round(base * factors[quality], 2)


def _portfolio_from_payload(payload: Mapping[str, Any]) -> PortfolioInput:
    portfolio = PortfolioInput(
        total_portfolio_value=_as_float(payload, "total_portfolio_value", "total_value") or 0.0,
        current_gold_value=max(0.0, _as_float(payload, "current_gold_value") or 0.0),
        monthly_new_cash=max(0.0, _as_float(payload, "monthly_new_cash") or 0.0),
        current_gold_cost=_as_float(payload, "current_gold_cost"),
        is_quarterly_rebalance_month=bool(payload.get("is_quarterly_rebalance_month", False)),
        crypto_weight=_ratio(payload, "crypto_weight"),
        us_equity_weight=_ratio(
            payload, "us_equity_weight", "us_stock_weight", "us_equity_allocation"
        ),
        a_share_weight=_ratio(payload, "a_share_weight", "ashare_weight", "cn_equity_weight"),
        halo_etf_weight=_ratio(payload, "halo_etf_weight"),
        cashflow_etf_weight=_ratio(payload, "cashflow_etf_weight"),
    )
    if portfolio.total_portfolio_value <= 0:
        raise ValueError("portfolio.total_value must be greater than 0")
    return portfolio


def _options_from_payload(payload: Mapping[str, Any] | None) -> AllocationOptions:
    payload = payload or {}
    return AllocationOptions(
        base_currency=str(payload.get("base_currency") or "元"),
        allow_quarterly_sell=bool(payload.get("allow_quarterly_sell", True)),
        max_monthly_gold_cash_fraction=clamp(
            _as_float(payload, "max_monthly_gold_cash_fraction") or 0.6,
            0.0,
            1.0,
        ),
        prefer_staged_execution=bool(payload.get("prefer_staged_execution", True)),
    )


def _goldhub_value(
    goldhub: Mapping[str, Any], key: str, *nested_paths: tuple[str, str]
) -> float | None:
    value = _as_float(goldhub, key)
    if value is not None:
        return value
    for parent, child in nested_paths:
        value = _as_float(_nested(goldhub, parent), child)
        if value is not None:
            return value
    return None


def _macro_layer(macro: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    layer_map = macro.get("layer_map")
    if isinstance(layer_map, Mapping) and isinstance(layer_map.get(key), Mapping):
        return layer_map[key]
    for layer in _iter_dicts(macro.get("layers")):
        if layer.get("layer_key") == key:
            return layer
    return {}


def _layer_score(macro: Mapping[str, Any], layer_key: str, fallback_key: str) -> float | None:
    value = _as_float(macro, fallback_key)
    if value is not None:
        return value
    return _as_float(_macro_layer(macro, layer_key), "score")


def _indicator_facts(layer: Mapping[str, Any], limit: int) -> list[str]:
    facts: list[str] = []
    for item in _iter_dicts(layer.get("indicators")):
        if not item.get("is_scored") and item.get("value_num") in (None, ""):
            continue
        label = str(
            item.get("display_label") or item.get("label") or item.get("indicator_key") or "指标"
        )
        value = (
            item.get("value_num")
            if item.get("value_num") not in (None, "")
            else item.get("value_text")
        )
        unit = str(item.get("unit") or "")
        try:
            number = float(value)
            shown = f"{number:.2f}{unit}" if abs(number) < 1000 else f"{number:,.0f}{unit}"
        except (TypeError, ValueError):
            shown = str(value or "-")
        facts.append(f"{label}：{shown}。")
        if len(facts) >= limit:
            break
    return facts


def _real_yield_5y_fact(macro: Mapping[str, Any]) -> str | None:
    for layer in _iter_dicts(macro.get("layers")):
        for item in _iter_dicts(layer.get("indicators")):
            if item.get("indicator_key") != "real_yield_5y":
                continue
            value = _as_float(item, "value_num")
            if value is None:
                return None
            source = str(item.get("source_provider") or "").strip()
            source_text = f"，来源 {source}" if source else ""
            return (
                f"美国5年期通胀保值国债收益率 {value:.2f}%{source_text}，"
                "代表黄金短中期持有机会成本和实际利率压力。"
            )
    return None


def _layer_fact(layer: Mapping[str, Any]) -> str | None:
    if not layer:
        return None
    label = str(layer.get("label_cn") or layer.get("layer_key") or "宏观层级")
    score = _as_float(layer, "score")
    effective = int(_as_float(layer, "effective_count") or 0)
    total = int(_as_float(layer, "total_count") or 0)
    bias = str(layer.get("bias") or "").strip()
    return (
        f"{label}评分 {score:.0f}{'，' + bias if bias else ''}，有效指标 {effective}/{total}。"
        if score is not None
        else None
    )


def _macro_card(macro: Mapping[str, Any]) -> ModuleCard:
    layer_scores = [
        _layer_score(macro, "rates_policy", "rates_policy_score"),
        _layer_score(macro, "inflation", "inflation_score"),
        _layer_score(macro, "growth_labor", "growth_labor_score"),
        _layer_score(macro, "cross_asset_confirmation", "cross_asset_score"),
        _layer_score(macro, "event_window", "event_window_score"),
    ]
    legacy_inputs = [
        _ratio(macro, "real_yield_10y_delta_4w", "real_rate_delta_4w"),
        _ratio(macro, "dxy_change_4w", "usd_change_4w"),
        _ratio(macro, "global_m2_delta_13w", "global_m2_yoy"),
        _ratio(macro, "inflation_yoy", "core_inflation_yoy"),
        _as_float(macro, "vix_level"),
    ]
    present = sum(value is not None for value in layer_scores) + sum(
        value is not None for value in legacy_inputs
    )
    quality = _quality_from_present(present, 10)
    if quality == "missing":
        return ModuleCard(
            "macro_monetary_environment",
            "宏观货币环境",
            50,
            _confidence("missing"),
            "missing",
            "missing",
            "宏观证据暂未完整返回，目标区间先按保守口径处理。",
            ["利率、通胀、美元、流动性和跨资产确认需要等待宏观总览刷新。"],
            "宏观缺失时不把黄金简单视作中性，也不直接当作看空，只降低判断置信度并保持执行保守。",
            "watch",
            ["宏观总览暂未形成完整输入。"],
        )

    score = _as_float(macro, "total_score")
    if score is None:
        available_scores = [value for value in layer_scores if value is not None]
        score = sum(available_scores) / len(available_scores) if available_scores else 50.0
    score = clamp(score)

    facts: list[str] = []
    for key in ("rates_policy", "inflation", "cross_asset_confirmation", "event_window"):
        fact = _layer_fact(_macro_layer(macro, key))
        if fact:
            facts.append(fact)
    facts.extend(str(item) for item in macro.get("macro_indicator_facts") or [])
    if real_yield_fact := _real_yield_5y_fact(macro):
        facts.insert(0, real_yield_fact)
    facts = facts[:5]
    if not facts:
        real_delta, dxy, m2, inflation, vix = legacy_inputs
        if real_delta is not None:
            facts.append(f"实际利率4周变化约 {_fmt_pct(real_delta, 2)}。")
        if dxy is not None:
            facts.append(f"美元4周变化约 {_fmt_pct(dxy, 1)}。")
        if m2 is not None:
            facts.append(f"全球流动性变化约 {_fmt_pct(m2, 1)}。")
        if inflation is not None:
            facts.append(f"通胀读数约 {_fmt_pct(inflation, 1)}。")
        if vix is not None:
            facts.append(f"VIX 处于 {vix:.1f}。")

    state = "supportive" if score >= 60 else "headwind" if score <= 42 else "neutral"
    headline = (
        "宏观组合对黄金配置形成支撑。"
        if state == "supportive"
        else "实际利率、美元或风险偏好对黄金配置形成压制。"
        if state == "headwind"
        else "宏观环境对黄金保持中性约束。"
    )
    return ModuleCard(
        "macro_monetary_environment",
        "宏观货币环境",
        score,
        _confidence(quality, 0.82),
        state,
        quality,
        headline,
        facts or ["宏观总览已返回，但有效指标有限。"],
        "黄金的目标区间由利率、通胀、增长、美元、跨资产风险和事件窗口共同约束；缺失项只降低置信度，不直接当作看空。",
        "increase" if score >= 60 else "pause" if score <= 42 else "maintain",
        [] if quality == "direct" else ["宏观输入不完整，结论需要保留安全边际。"],
    )


def _official_reserve_card(goldhub: Mapping[str, Any]) -> ModuleCard:
    buying_12m = _goldhub_value(
        goldhub, "central_bank_net_purchase_tonnes_12m", ("central_bank", "net_purchase_tonnes_12m")
    )
    buying_3m = _goldhub_value(
        goldhub, "central_bank_net_purchase_tonnes_3m", ("central_bank", "net_purchase_tonnes_3m")
    )
    present = sum(value is not None for value in [buying_12m, buying_3m])
    quality = _quality_from_present(present, 2)
    if quality == "missing":
        return ModuleCard(
            "official_reserve_demand",
            "官方储备需求",
            55,
            _confidence("missing"),
            "missing",
            "missing",
            "官方储备需求缺少本地 Goldhub/WGC 输入。",
            ["未找到央行净购金或储备需求数据。"],
            "官方储备是黄金长期配置的核心证据，缺失时保持温和中性但降低置信度。",
            "watch",
            ["官方储备需求数据缺失。"],
        )
    score = 50.0
    facts = []
    if buying_12m is not None:
        score += (
            24 if buying_12m >= 700 else 14 if buying_12m >= 300 else -8 if buying_12m < 0 else 4
        )
        facts.append(f"央行12个月净购金约 {buying_12m:.0f} 吨。")
    if buying_3m is not None:
        score += 12 if buying_3m >= 120 else -8 if buying_3m < 0 else 4
        facts.append(f"近3个月净购金约 {buying_3m:.0f} 吨。")
    final = clamp(score)
    return ModuleCard(
        "official_reserve_demand",
        "官方储备需求",
        final,
        _confidence(quality, 0.78),
        "strong_support" if final >= 75 else "supportive" if final >= 60 else "neutral",
        quality,
        "官方储备需求支撑黄金的长期配置角色。" if final >= 60 else "官方储备需求暂未形成强支撑。",
        facts,
        "央行和主权储备需求不直接决定短期价格，但会提高黄金在组合中的战略底仓价值。",
        "increase" if final >= 65 else "maintain",
        [] if quality == "direct" else ["官方储备数据不完整。"],
    )


def _supply_card(goldhub: Mapping[str, Any]) -> ModuleCard:
    mine = _goldhub_value(goldhub, "mine_production_yoy", ("supply", "mine_production_yoy"))
    aisc = _goldhub_value(goldhub, "aisc_yoy", ("supply", "aisc_yoy"))
    recycle = _goldhub_value(goldhub, "recycling_yoy", ("supply", "recycling_yoy"))
    balance = _goldhub_value(
        goldhub, "supply_demand_balance_tonnes", ("supply", "supply_demand_balance_tonnes")
    )
    present = sum(value is not None for value in [mine, aisc, recycle, balance])
    quality = _quality_from_present(present, 4)
    if quality == "missing":
        return ModuleCard(
            "supply_rigidity",
            "供给刚性",
            55,
            _confidence("missing"),
            "missing",
            "missing",
            "供给数据缺失，保留长期刚性假设。",
            ["未找到矿产、回收金、AISC 或供需平衡数据。"],
            "供给侧缺失不应被当作看空，只降低供给模块置信度。",
            "watch",
            ["供给刚性数据缺失。"],
        )
    score = 50.0
    facts = []
    if mine is not None:
        score += 8 if mine < 0.02 else -5 if mine > 0.05 else 2
        facts.append(f"矿产供应同比约 {_fmt_pct(mine, 1)}。")
    if aisc is not None:
        score += 10 if aisc > 0.05 else 2
        facts.append(f"AISC 同比约 {_fmt_pct(aisc, 1)}。")
    if recycle is not None:
        score -= 4 if recycle > 0.08 else 1
        facts.append(f"回收金同比约 {_fmt_pct(recycle, 1)}。")
    if balance is not None:
        score += 8 if balance < 0 else -5 if balance > 120 else 1
        facts.append(f"供需平衡约 {balance:.0f} 吨。")
    final = clamp(score)
    return ModuleCard(
        "supply_rigidity",
        "供给刚性",
        final,
        _confidence(quality, 0.72),
        "tight" if final >= 62 else "loose" if final < 40 else "neutral",
        quality,
        "供给偏紧增强黄金长期配置韧性。" if final >= 60 else "供给侧暂未形成明显增配理由。",
        facts,
        "黄金供给扩张慢，AISC 上行和供需缺口会提高长期配置价值。",
        "increase" if final >= 62 else "maintain",
        [] if quality == "direct" else ["供给数据不完整。"],
    )


def _portfolio_card(portfolio: PortfolioInput) -> ModuleCard:
    risk_weight = sum(
        value or 0
        for value in [
            portfolio.crypto_weight,
            portfolio.us_equity_weight,
            portfolio.a_share_weight,
            portfolio.halo_etf_weight,
        ]
    )
    cashflow = portfolio.cashflow_etf_weight or 0
    score = clamp(50 + min(30, risk_weight * 55) - min(8, cashflow * 15))
    facts = [
        f"当前黄金权重 {_fmt_pct(portfolio.current_weight, 1)}。",
        f"Crypto 权重约 {_fmt_pct(portfolio.crypto_weight or 0, 1)}。",
        f"美股权重约 {_fmt_pct(portfolio.us_equity_weight or 0, 1)}。",
        f"A股权重约 {_fmt_pct(portfolio.a_share_weight or 0, 1)}。",
    ]
    if portfolio.halo_etf_weight:
        facts.append(f"HALO 权重约 {_fmt_pct(portfolio.halo_etf_weight, 1)}。")
    if cashflow:
        facts.append(f"现金流 ETF 权重约 {_fmt_pct(cashflow, 1)}，不能完全替代黄金跨资产对冲。")
    return ModuleCard(
        "portfolio_hedging_need",
        "组合对冲需求",
        score,
        0.82,
        "high_hedge_need"
        if score >= 68
        else "moderate_hedge_need"
        if score >= 52
        else "low_hedge_need",
        "direct",
        "组合风险资产越高，黄金的跨市场对冲价值越高。",
        facts,
        "黄金配置面向整个投资组合，主要对冲 Crypto、美股、A股等风险资产在宏观冲击和流动性收缩时的同步回撤。",
        "increase" if score >= 62 else "maintain",
    )


def _market_window_logic(market: Mapping[str, Any], key: str, fallback: str) -> str:
    window = market.get(key)
    if isinstance(window, Mapping):
        return str(
            window.get("logic") or window.get("summary") or window.get("interpretation") or fallback
        )
    return fallback


def _liquidity_card(market: Mapping[str, Any], macro: Mapping[str, Any]) -> ModuleCard:
    ret_7d = _ratio(market, "ret_7d", "xaut_change_7d_pct")
    btc_ret = _ratio(market, "btc_ret_7d")
    nasdaq_ret = _ratio(market, "nasdaq_ret_7d")
    dxy_ret = _ratio(market, "dxy_ret_7d")
    vix_change = _ratio(market, "vix_change_7d")
    corr = _as_float(market, "gold_risk_corr_20d")
    vix_level = _as_float(macro, "vix_level")
    natr = _ratio(market, "natr_14", "natr_pct")
    liquidity_score = _layer_score(macro, "liquidity_credit", "liquidity_credit_score")
    cross_asset_score = _layer_score(macro, "cross_asset_confirmation", "cross_asset_score")
    present = sum(
        value is not None
        for value in [
            ret_7d,
            btc_ret,
            nasdaq_ret,
            dxy_ret,
            vix_change,
            corr,
            vix_level,
            natr,
            liquidity_score,
            cross_asset_score,
        ]
    )
    quality: DataQuality = "proxy" if present else "missing"
    stress = 0
    facts: list[str] = []
    if ret_7d is not None:
        stress += 2 if ret_7d <= -0.05 else -1 if ret_7d > 0.03 else 0
        facts.append(f"XAUT 7日变化约 {_fmt_pct(ret_7d, 1)}。")
    if btc_ret is not None and btc_ret <= -0.08:
        stress += 1
        facts.append(f"BTC 7日跌幅约 {_fmt_pct(btc_ret, 1)}。")
    if nasdaq_ret is not None and nasdaq_ret <= -0.04:
        stress += 1
        facts.append(f"纳指7日跌幅约 {_fmt_pct(nasdaq_ret, 1)}。")
    if dxy_ret is not None and dxy_ret > 0.01:
        stress += 1
        facts.append(f"美元7日走强约 {_fmt_pct(dxy_ret, 1)}。")
    if vix_change is not None and vix_change > 0.15:
        stress += 1
        facts.append(f"VIX 7日变化约 {_fmt_pct(vix_change, 1)}。")
    if corr is not None and corr > 0.35:
        stress += 1
        facts.append("黄金与风险资产相关性阶段性上升。")
    if vix_level is not None and vix_level >= 25:
        stress += 1
    if natr is not None and natr >= 0.035:
        stress += 1
        facts.append(f"XAUT 日线波动率约 {_fmt_pct(natr, 1)}。")
    if liquidity_score is not None:
        if liquidity_score <= 42:
            stress += 1
        facts.append(f"流动性信用层评分 {liquidity_score:.0f}。")
    facts.extend(str(item) for item in macro.get("liquidity_facts") or [])
    facts = list(dict.fromkeys(facts))[:5]

    daily_headline = (
        "日线存在同步去风险和执行滑点压力。" if stress >= 4 else "日线未显示明显流动性抛售。"
    )
    weekly_headline = (
        "周线流动性条件偏紧，长期配置仍需保留分批纪律。"
        if liquidity_score is not None and liquidity_score <= 42
        else "周线流动性条件没有破坏长期配置结构。"
    )
    window_views = {
        "daily": WindowView(
            "日线窗口",
            daily_headline,
            facts[:3] or ["短期跨资产压力输入有限。"],
            "日线窗口用于判断本月执行质量：若黄金、Crypto、美股同步承压且波动放大，低配补足应拆分执行。",
            quality,
        ),
        "weekly": WindowView(
            "周线窗口",
            weekly_headline,
            (macro.get("liquidity_facts") or facts)[0:4] or ["流动性信用层有效输入有限。"],
            "周线窗口用于判断长期配置结构：只要流动性收缩没有伴随长期对冲逻辑失效，黄金目标区间不因短期抛售被推翻。",
            "partial" if liquidity_score is None else quality,
        ),
    }
    if quality == "missing":
        return ModuleCard(
            "liquidity_selloff_rebound",
            "流动性抛售",
            50,
            _confidence("missing"),
            "missing",
            "missing",
            "未识别到流动性抛售输入。",
            ["缺少 XAUT 与跨资产压力输入。"],
            "缺少压力输入时不改变长期目标区间，但执行节奏保持谨慎。",
            "watch",
            ["流动性压力数据缺失。"],
            window_views,
        )
    if stress >= 4:
        return ModuleCard(
            "liquidity_selloff_rebound",
            "流动性抛售",
            45,
            0.68,
            "selloff_watch",
            quality,
            "存在流动性抛售或同步去风险迹象。",
            facts,
            "长期逻辑未必失效，但低配补仓不宜一次性完成，应等待价格和波动部分稳定后分批。",
            "split_add",
            ["流动性抛售阶段执行滑点和回撤风险较高。"],
            window_views,
        )
    return ModuleCard(
        "liquidity_selloff_rebound",
        "流动性抛售",
        55,
        0.62,
        "normal",
        quality,
        "暂未看到明显流动性抛售。",
        facts or ["跨资产压力输入有限。"],
        "没有同步去风险证据时，执行节奏主要跟随目标区间和月度现金约束。",
        "maintain",
        window_views=window_views,
    )


def _derivatives_card(goldhub: Mapping[str, Any], market: Mapping[str, Any]) -> ModuleCard:
    oi = _goldhub_value(
        goldhub,
        "futures_oi_change_4w",
        ("derivatives", "futures_oi_change_4w"),
        ("derivatives", "futures_oi_change"),
    )
    volume = _goldhub_value(
        goldhub, "futures_volume_zscore", ("derivatives", "futures_volume_zscore")
    )
    cot = _goldhub_value(
        goldhub, "cot_net_spec_percentile", ("derivatives", "cot_net_spec_percentile")
    )
    xaut_volume = _as_float(market, "volume_zscore")
    natr = _ratio(market, "natr_14", "natr_pct")
    present = sum(value is not None for value in [oi, volume, cot])
    proxy_present = sum(value is not None for value in [xaut_volume, natr])
    quality = (
        _quality_from_present(present, 3) if present else ("proxy" if proxy_present else "missing")
    )
    crowded = (
        (oi is not None and oi >= 0.08)
        or (volume is not None and volume >= 1.5)
        or (cot is not None and cot >= 0.75)
        or (xaut_volume is not None and xaut_volume >= 2.0)
        or (natr is not None and natr >= 0.04)
    )
    facts = []
    if oi is not None:
        facts.append(f"期货 OI 4周变化约 {_fmt_pct(_ratio({'v': oi}, 'v') or 0, 1)}。")
    if volume is not None:
        facts.append(f"期货成交量 z-score 约 {volume:.1f}。")
    if cot is not None:
        facts.append(f"COT 净多分位约 {_fmt_pct(_ratio({'v': cot}, 'v') or 0, 0)}。")
    if xaut_volume is not None:
        facts.append(f"XAUT 成交量 z-score 约 {xaut_volume:.1f}。")
    if natr is not None:
        facts.append(f"XAUT NATR 约 {_fmt_pct(natr, 1)}。")

    daily_quality: DataQuality = "proxy" if proxy_present else "missing"
    weekly_quality: DataQuality = _quality_from_present(present, 3) if present else "proxy"
    window_views = {
        "daily": WindowView(
            "日线窗口",
            "日线执行拥挤度偏高。" if crowded and proxy_present else "日线执行拥挤度暂未明显放大。",
            [fact for fact in facts if "XAUT" in fact][:3]
            or ["日线主要使用 XAUT 量价代理评估执行质量。"],
            "日线窗口只影响本月分批和滑点控制，不单独改变长期黄金目标区间。",
            daily_quality,
        ),
        "weekly": WindowView(
            "周线窗口",
            "周线持仓拥挤度需要分批消化。"
            if crowded and present
            else "周线衍生品拥挤未形成明确上限压制。",
            [fact for fact in facts if "期货" in fact or "COT" in fact][:3]
            or ["周线拥挤数据缺失，使用 XAUT 量价代理。"],
            "周线窗口用于观察期货持仓、成交和 COT 是否使配置执行需要更慢；它不单独推翻长期配置区间。",
            weekly_quality,
        ),
    }
    if quality == "missing":
        return ModuleCard(
            "derivatives_pressure",
            "衍生品压力",
            50,
            _confidence("missing"),
            "missing",
            "missing",
            "衍生品拥挤度缺少输入。",
            ["未找到期货持仓、成交量或 COT 分位。"],
            "衍生品压力主要影响执行节奏，不单独推翻长期配置区间。",
            "watch",
            ["衍生品压力数据缺失。"],
            window_views,
        )
    return ModuleCard(
        "derivatives_pressure",
        "衍生品压力",
        48 if crowded else 55,
        _confidence(quality, 0.7),
        "crowded" if crowded else "normal",
        quality,
        "衍生品持仓或成交出现拥挤，执行应分批。" if crowded else "衍生品压力未明显放大。",
        facts,
        "衍生品拥挤不改变长期目标区间，但会提高短期波动和执行分批的必要性。",
        "split_add" if crowded else "maintain",
        ["衍生品拥挤会放大短期波动。"] if crowded else [],
        window_views,
    )


def _window_logic(window: Any, label: str) -> str | None:
    if not isinstance(window, Mapping):
        return None
    logic = window.get("logic") or window.get("summary") or window.get("interpretation")
    trend = window.get("trend")
    ret = _ratio(window, "ret_30d", "ret_12w", "return")
    drawdown = _ratio(window, "drawdown", "drawdown_60d")
    parts = [f"{label}窗口"]
    if trend:
        parts.append(f"结构={trend}")
    if ret is not None:
        parts.append(f"变化={_fmt_pct(ret, 1)}")
    if drawdown is not None:
        parts.append(f"回撤={_fmt_pct(drawdown, 1)}")
    if logic:
        parts.append(str(logic))
    return "；".join(parts) + "。"


def _xaut_card(market: Mapping[str, Any]) -> ModuleCard:
    price = _as_float(market, "price", "xaut_price")
    ret_30d = _ratio(market, "ret_30d")
    drawdown = _ratio(market, "drawdown_60d", "drawdown_pct")
    natr = _ratio(market, "natr_14", "natr_pct")
    above_ma50 = market.get("above_ma50")
    above_ma200 = market.get("above_ma200")
    present = sum(
        value is not None for value in [price, ret_30d, drawdown, natr, above_ma50, above_ma200]
    )
    quality: DataQuality = "proxy" if present else "missing"
    if quality == "missing":
        return ModuleCard(
            "xaut_price_state",
            "XAUT",
            50,
            _confidence("missing"),
            "missing",
            "missing",
            "XAUT 代理行情缺失。",
            ["未读取到 XAUT_USDT 日线代理行情。"],
            "无行情时仍可给出配置框架，但执行金额应保守。",
            "watch",
            ["XAUT 代理行情缺失。"],
        )
    score = 50.0
    facts = []
    if price is not None:
        facts.append(f"XAUT 最新价约 {price:,.0f}。")
    if ret_30d is not None:
        score += 5 if ret_30d > 0 else -4 if ret_30d < -0.05 else 0
        facts.append(f"30日变化约 {_fmt_pct(ret_30d, 1)}。")
    if drawdown is not None:
        score += 4 if drawdown <= -0.08 else 0
        facts.append(f"60日回撤约 {_fmt_pct(drawdown, 1)}。")
    if natr is not None:
        facts.append(f"NATR 约 {_fmt_pct(natr, 1)}。")
    if above_ma50 is not None or above_ma200 is not None:
        facts.append(
            f"均线状态：MA50 {'上方' if above_ma50 else '下方'}，MA200 {'上方' if above_ma200 else '下方'}。"
        )
    daily_fact = _window_logic(market.get("daily_window"), "日线")
    weekly_fact = _window_logic(market.get("weekly_window"), "周线")
    facts.append(
        daily_fact or "日线窗口：用于判断本月执行质量，当前以 XAUT 日线价格、30日变化和波动率估算。"
    )
    facts.append(
        weekly_fact or "周线窗口：用于判断长期配置结构，当前以 MA200、60日回撤和中期变化近似。"
    )
    volatile = natr is not None and natr >= 0.035
    return ModuleCard(
        "xaut_price_state",
        "XAUT",
        clamp(score),
        0.65,
        "volatile" if volatile else "normal",
        quality,
        "XAUT 用作实时黄金价格代理，主要校准执行节奏。",
        facts,
        "日线窗口决定本月执行是否拆分，周线窗口决定长期配置结构是否仍成立；价格状态不单独决定长期比例。",
        "split_add" if volatile else "maintain",
        ["XAUT 波动偏高，执行应拆分。"] if volatile else [],
    )


def _target_range(score: float) -> dict[str, float]:
    if score >= 80:
        return {"min": 0.12, "max": 0.18}
    if score >= 60:
        return {"min": 0.08, "max": 0.12}
    if score >= 40:
        return {"min": 0.05, "max": 0.08}
    if score >= 20:
        return {"min": 0.03, "max": 0.05}
    return {"min": 0.0, "max": 0.03}


def _weighted_score(cards: list[ModuleCard]) -> float:
    total = 0.0
    weight_sum = 0.0
    for card in cards:
        weight = WEIGHTS.get(card.key, 0.0)
        total += card.score * weight
        weight_sum += weight
    return clamp(total / max(weight_sum, 0.01))


def _allocation_state(current_weight: float, target: Mapping[str, float]) -> str:
    if current_weight < target["min"]:
        return "underweight"
    if current_weight > target["max"]:
        return "overweight"
    return "within_range"


def _execution(
    portfolio: PortfolioInput,
    target: Mapping[str, float],
    cards: list[ModuleCard],
    options: AllocationOptions,
) -> tuple[str, str, float, str]:
    current_weight = portfolio.current_weight
    gap_to_min = max(
        0.0, portfolio.total_portfolio_value * target["min"] - portfolio.current_gold_value
    )
    gap_above_max = max(
        0.0, portfolio.current_gold_value - portfolio.total_portfolio_value * target["max"]
    )
    state = _allocation_state(current_weight, target)
    split_needed = options.prefer_staged_execution or any(
        card.allocation_effect == "split_add" for card in cards
    )
    macro_pause = any(
        card.key == "macro_monetary_environment" and card.allocation_effect == "pause"
        for card in cards
    )
    currency = options.base_currency
    if state == "underweight":
        if macro_pause:
            return (
                "pause_add",
                "宏观压力偏强，黄金低配但本月先暂停新增，等待实际利率或美元压力缓和。",
                0.0,
                "pause_add",
            )
        monthly_cap = portfolio.monthly_new_cash * options.max_monthly_gold_cash_fraction
        suggested = min(gap_to_min, monthly_cap)
        if suggested <= 0:
            return (
                "wait_for_cash",
                "黄金低于目标区间，但本月没有可用新增现金，先维持并等待下次现金流。",
                0.0,
                "wait_for_cash",
            )
        if split_needed:
            suggested = min(suggested, max(monthly_cap * 0.5, 0.0))
            return (
                "split_2_to_3_tranches",
                f"黄金低配，本月先用约 {_fmt_money(suggested, currency)} 分2到3批补足。",
                suggested,
                "split_2_to_3_tranches",
            )
        return (
            "monthly_add",
            f"黄金低配，本月使用约 {_fmt_money(suggested, currency)} 的新增现金补足到目标下沿。",
            suggested,
            "monthly_add",
        )
    if state == "overweight":
        material = current_weight - target["max"] >= options.material_overweight_threshold
        if portfolio.is_quarterly_rebalance_month and options.allow_quarterly_sell and material:
            return (
                "quarterly_reduce_to_upper_band",
                f"黄金明显超配，季度再平衡可下调约 {_fmt_money(gap_above_max, currency)} 至目标上沿。",
                -gap_above_max,
                "quarterly_reduce_to_upper_band",
            )
        return (
            "pause_add",
            "黄金高于目标区间，本月暂停新增；非季度窗口不主动降低黄金仓位。",
            0.0,
            "pause_add",
        )
    return (
        "maintain",
        "黄金处于目标区间，本月维持配置，只跟踪宏观与 XAUT 代理行情变化。",
        0.0,
        "maintain",
    )


def _data_quality(cards: list[ModuleCard]) -> dict[str, Any]:
    missing = [card.key for card in cards if card.data_quality == "missing"]
    partial = [card.key for card in cards if card.data_quality == "partial"]
    proxy = [card.key for card in cards if card.data_quality == "proxy"]
    avg_conf = sum(card.confidence for card in cards) / max(len(cards), 1)
    return {
        "confidence": round(avg_conf, 2),
        "missing_modules": missing,
        "partial_modules": partial,
        "proxy_modules": proxy,
        "uses_xaut_as_proxy": True,
        "note": "缺失模块会降低置信度，但不会被静默当成中性看待。",
    }


def _reasoning_steps(
    portfolio: PortfolioInput,
    target: Mapping[str, float],
    state: str,
    instruction: str,
    cards: list[ModuleCard],
    quality: Mapping[str, Any],
    options: AllocationOptions,
) -> list[str]:
    top_cards = sorted(cards, key=lambda card: card.score, reverse=True)[:2]
    state_label = {"underweight": "低配", "overweight": "超配", "within_range": "达标"}[state]
    steps = [
        f"目标区间来自宏观货币环境、官方储备需求、供给刚性、组合对冲需求和执行风险的加权结果，目前为 {_fmt_pct(target['min'], 0)} 到 {_fmt_pct(target['max'], 0)}。",
        f"当前黄金权重为 {_fmt_pct(portfolio.current_weight, 1)}，因此判断为{state_label}。",
        instruction,
        "主要支撑来自"
        + "、".join(card.title for card in top_cards)
        + "；"
        + "；".join(card.headline for card in top_cards),
    ]
    if quality.get("missing_modules") or quality.get("partial_modules"):
        steps.append("部分数据缺失或不完整，已降低置信度并把执行节奏调得更保守。")
    if options.prefer_staged_execution:
        steps.append("默认偏好分批执行，用来降低单一价格点和代理行情误差带来的执行风险。")
    return steps


def _decision_summary(state: str, target: Mapping[str, float], cards: list[ModuleCard]) -> str:
    support = [card.title for card in cards if card.allocation_effect == "increase"]
    caution = [
        card.title for card in cards if card.allocation_effect in {"split_add", "pause", "watch"}
    ]
    state_text = {
        "underweight": "当前黄金低配",
        "within_range": "当前黄金处于目标区间",
        "overweight": "当前黄金超配",
    }[state]
    support_text = "、".join(support[:2]) if support else "现有长期证据"
    caution_text = "；执行层面需要关注" + "、".join(caution[:2]) if caution else ""
    return f"{state_text}，V2 目标区间为 {_fmt_pct(target['min'], 0)} 到 {_fmt_pct(target['max'], 0)}。长期理由主要来自{support_text}{caution_text}。"


def _legacy_action(state: str, execution_style: str) -> str:
    if execution_style in {"split_2_to_3_tranches", "monthly_add"}:
        return "use_new_cash_to_add_gradually"
    if execution_style == "quarterly_reduce_to_upper_band":
        return "rebalance_down_to_target"
    if execution_style == "pause_add":
        return "pause_adding"
    if state == "within_range":
        return "maintain"
    return "wait_for_stabilization"


def build_gold_allocation_plan(
    portfolio_payload: Mapping[str, Any],
    *,
    macro: Mapping[str, Any] | None = None,
    goldhub: Mapping[str, Any] | None = None,
    market: Mapping[str, Any] | None = None,
    options: Mapping[str, Any] | None = None,
) -> AllocationPlan:
    portfolio = _portfolio_from_payload(portfolio_payload)
    options_payload = _options_from_payload(options)
    macro_payload = macro or {}
    goldhub_payload = goldhub or {}
    market_payload = market or {}
    cards = [
        _macro_card(macro_payload),
        _official_reserve_card(goldhub_payload),
        _supply_card(goldhub_payload),
        _portfolio_card(portfolio),
        _liquidity_card(market_payload, macro_payload),
        _derivatives_card(goldhub_payload, market_payload),
        _xaut_card(market_payload),
    ]
    score = _weighted_score(cards)
    target = _target_range(score)
    state = _allocation_state(portfolio.current_weight, target)
    execution_style, primary_instruction, suggested, _action = _execution(
        portfolio, target, cards, options_payload
    )
    quality = _data_quality(cards)
    warnings = [warning for card in cards for warning in card.warnings]
    decision_summary = _decision_summary(state, target, cards)
    steps = _reasoning_steps(
        portfolio, target, state, primary_instruction, cards, quality, options_payload
    )
    module_cards = [card.to_dict() for card in cards]
    gap_to_min = max(
        0.0, portfolio.total_portfolio_value * target["min"] - portfolio.current_gold_value
    )
    gap_above_max = max(
        0.0, portfolio.current_gold_value - portfolio.total_portfolio_value * target["max"]
    )
    return AllocationPlan(
        allocation_state=state,
        allocation_score=score,
        target_range=target,
        current_weight=portfolio.current_weight,
        gap_to_target_min=gap_to_min,
        gap_above_target_max=gap_above_max,
        suggested_this_month=suggested,
        execution_style=execution_style,
        primary_instruction=primary_instruction,
        decision_summary=decision_summary,
        reasoning_steps=steps,
        module_cards=module_cards,
        data_quality=quality,
        warnings=warnings,
        drivers={card["key"]: card for card in module_cards},
        asset_impact_summary={"gold": decision_summary},
    )
