from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    MacroOverviewEventRead,
    MacroOverviewIndicatorRead,
    MacroOverviewLayerRead,
    MacroOverviewResponse,
)
from app.services.macro.fallback_resolver import fallback_for_indicator

UTC = timezone.utc
CONFIG_DIR = Path(__file__).resolve().parents[1] / "monitoring" / "configs"
INDICATOR_MAP_PATH = CONFIG_DIR / "macro_indicator_api_map.v1.json"

INVALID_TEXT_VALUES = {
    "unavailable",
    "source_error",
    "pending_release",
    "missing",
    "none",
    "null",
    "nan",
}
NON_SCORABLE_STATUSES = {
    "auth_missing",
    "disabled",
    "missing",
    "not_configured",
    "not_implemented",
    "parser_error",
    "pending",
    "proxy_required_unavailable",
    "rate_limited",
    "source_error",
    "unavailable",
    "unavailable_placeholder",
    "web_cached",
}
SCORABLE_TEXT_INDICATORS = {"fomc_event_window"}


@dataclass(frozen=True)
class MacroIndicatorSpec:
    indicator_key: str
    label: str
    tooltip: str
    layer_key: str
    frequency: str = "daily"
    unit: str = ""
    display_code: str | None = None
    display_label: str | None = None
    aliases: tuple[str, ...] = ()
    source_provider: str | None = None


@dataclass(frozen=True)
class MacroLayerSpec:
    layer_key: str
    label_cn: str
    indicators: tuple[MacroIndicatorSpec, ...]


LAYER_LABELS = {
    "rates_policy": "利率与政策",
    "inflation": "通胀与价格",
    "growth_labor": "增长与就业",
    "liquidity_credit": "流动性与信用",
    "cross_asset_confirmation": "跨资产确认",
    "event_window": "事件窗口",
}

MODULE_TO_LAYER = {
    "policy_rates": "rates_policy",
    "inflation_prices": "inflation",
    "growth_jobs": "growth_labor",
    "liquidity_credit": "liquidity_credit",
    "usd_real_rates": "cross_asset_confirmation",
    "cross_asset": "cross_asset_confirmation",
    "event_window": "event_window",
}

DISPLAY_CODE_BY_INDICATOR = {
    "effr": "EFFR",
    "us03m_yield": "US3M",
    "us02y_yield": "US2Y",
    "us10y_yield": "US10Y",
    "us30y_yield": "US30Y",
    "us10y_2y_spread": "US10Y-2Y",
    "us10y_3m_spread": "US10Y-3M",
    "cpi_yoy": "US CPI",
    "cpi_mom": "US CPI",
    "core_cpi_yoy": "US Core CPI",
    "core_cpi_mom": "US Core CPI",
    "pce_yoy": "US PCE",
    "core_pce_yoy": "US Core PCE",
    "nfp": "US NFP",
}

CLEAN_INDICATOR_LABELS = {
    "effr": ("美国有效联邦基金利率", "美联储政策利率的实际成交水平。"),
    "sofr": ("SOFR 隔夜融资利率", "美元隔夜资金成本，反映短端流动性。"),
    "us03m_yield": ("美国3个月国债收益率", "短端利率，常用于观察政策定价。"),
    "us02y_yield": ("美国2年期国债收益率", "对政策路径最敏感的国债收益率。"),
    "us10y_yield": ("美国10年期国债收益率", "全球风险资产定价的重要折现锚。"),
    "us30y_yield": ("美国30年期国债收益率", "长期增长、通胀和期限溢价的综合反映。"),
    "us10y_2y_spread": ("美债10Y-2Y利差", "收益率曲线斜率，观察衰退预期与政策压力。"),
    "us10y_3m_spread": ("美债10Y-3M利差", "更贴近货币政策约束的曲线斜率。"),
    "cpi_yoy": ("美国CPI同比", "居民消费价格指数同比，是通胀主指标。"),
    "cpi_mom": ("美国CPI环比", "观察当月通胀动能是否重新抬头。"),
    "core_cpi_yoy": ("美国核心CPI同比", "剔除食品和能源后的粘性通胀压力。"),
    "core_cpi_mom": ("美国核心CPI环比", "粘性通胀的短期动能。"),
    "pce_yoy": ("美国PCE同比", "美联储更偏好的通胀口径。"),
    "core_pce_yoy": ("美国核心PCE同比", "判断中期通胀压力的核心指标。"),
    "breakeven_5y": ("美国5年通胀预期", "TIPS 隐含通胀预期。"),
    "breakeven_10y": ("美国10年通胀预期", "市场对长期通胀的定价。"),
    "wti_oil": ("WTI原油", "能源价格会影响通胀预期和风险偏好。"),
    "nfp": ("美国非农就业", "新增就业影响政策预期和增长判断。"),
    "unemployment_rate": ("美国失业率", "劳动市场松紧程度。"),
    "average_hourly_earnings_yoy": ("美国平均时薪同比", "工资增速是服务通胀的重要线索。"),
    "initial_claims": ("美国初请失业金人数", "高频观察就业市场是否转弱。"),
    "continuing_claims": ("美国续请失业金人数", "观察失业后再就业难度。"),
    "jolts_openings": ("JOLTS职位空缺", "衡量劳动力需求与薪资压力。"),
    "gdp_qoq": ("美国GDP环比", "经济增长总量指标。"),
    "fed_balance_sheet": ("美联储资产负债表", "量化紧缩或扩表会影响美元流动性。"),
    "reverse_repo": ("隔夜逆回购余额", "美联储隔夜逆回购余额，反映流动性吸收。"),
    "bank_reserves": ("美国银行准备金", "银行体系可用流动性。"),
    "m2": ("美国M2货币供应", "广义货币供给变化。"),
    "hy_spread": ("美国高收益债利差", "信用风险溢价，走阔通常代表风险偏好下降。"),
    "investment_grade_spread": ("投资级信用利差", "企业融资压力和信用风险的温和口径。"),
    "financial_conditions": ("金融条件指数", "综合利率、信用、股票和汇率的金融环境指标。"),
    "dxy": ("美元指数DXY", "美元强弱影响全球流动性与风险资产偏好。"),
    "real_yield_10y": ("美国10年实际利率", "实际利率上行通常压制风险资产估值。"),
    "real_yield_5y": ("美国5年实际利率", "中期实际利率压力。"),
    "gold": ("黄金", "避险资产和实际利率预期的交叉验证。"),
    "vix": ("VIX波动率", "美股隐含波动率，衡量风险厌恶程度。"),
    "qqq": ("纳斯达克100 ETF", "科技股风险偏好的代表。"),
    "spy": ("标普500 ETF", "美股宽基风险偏好的代表。"),
    "hyg": ("高收益债 ETF", "信用风险偏好的交易型代理。"),
    "usd_cny": ("美元兑人民币", "离岸人民币压力与美元流动性的参考。"),
    "fomc_event_window": ("FOMC事件窗口", "美联储议息会议前后的风险窗口。"),
}

INDICATOR_LABELS = {
    "effr": ("美国有效联邦基金利率", "美联储政策利率的实际成交水平。"),
    "sofr": ("SOFR 隔夜融资利率", "美元隔夜资金成本，反映短端流动性。"),
    "us03m_yield": ("美国3个月国债收益率", "短端利率，常用于观察政策定价。"),
    "us02y_yield": ("美国2年期国债收益率", "对政策路径最敏感的国债收益率。"),
    "us10y_yield": ("美国10年期国债收益率", "全球风险资产定价的重要折现锚。"),
    "us30y_yield": ("美国30年期国债收益率", "长期增长、通胀和期限溢价的综合反映。"),
    "us10y_2y_spread": ("美债10Y-2Y利差", "收益率曲线斜率，观察衰退预期与政策压力。"),
    "us10y_3m_spread": ("美债10Y-3M利差", "更贴近货币政策约束的曲线斜率。"),
    "cpi_yoy": ("美国CPI同比", "居民消费价格指数同比，是通胀主指标。"),
    "cpi_mom": ("美国CPI环比", "观察当月通胀动能是否重新抬头。"),
    "core_cpi_yoy": ("美国核心CPI同比", "剔除食品和能源后的粘性通胀压力。"),
    "core_cpi_mom": ("美国核心CPI环比", "粘性通胀的短期动能。"),
    "pce_yoy": ("美国PCE同比", "美联储更偏好的通胀口径。"),
    "core_pce_yoy": ("美国核心PCE同比", "判断中期通胀压力的核心指标。"),
    "breakeven_5y": ("美国5年通胀预期", "TIPS 隐含通胀预期。"),
    "breakeven_10y": ("美国10年通胀预期", "市场对长期通胀的定价。"),
    "wti_oil": ("WTI原油", "能源价格会影响通胀预期和风险偏好。"),
    "nfp": ("美国非农就业", "新增就业影响政策预期和增长判断。"),
    "unemployment_rate": ("美国失业率", "劳动市场松紧程度。"),
    "average_hourly_earnings_yoy": ("美国平均时薪同比", "工资增速是服务通胀和就业热度的重要线索。"),
    "initial_claims": ("美国初请失业金人数", "高频观察就业市场是否转弱。"),
    "continuing_claims": ("美国续请失业金人数", "观察失业后再就业难度。"),
    "jolts_openings": ("JOLTS职位空缺", "衡量劳动力需求与薪资压力。"),
    "ism_manufacturing": ("ISM制造业PMI", "制造业景气度，50以上通常代表扩张。"),
    "ism_services": ("ISM服务业PMI", "服务业景气度，对美国经济韧性更敏感。"),
    "retail_sales": ("美国零售销售", "居民消费强弱的高频观察窗口。"),
    "gdp_qoq": ("美国GDP环比", "经济增长总量指标。"),
    "fed_balance_sheet": ("美联储资产负债表", "量化紧缩或扩表会影响美元流动性。"),
    "tga": ("美国财政部TGA", "财政部现金账户变化会影响美元流动性。"),
    "reverse_repo": ("隔夜逆回购余额", "美联储隔夜逆回购余额，反映流动性吸收。"),
    "bank_reserves": ("美国银行准备金", "银行体系可用流动性。"),
    "m2": ("美国M2货币供应", "广义货币供给变化。"),
    "hy_spread": ("美国高收益债利差", "信用风险溢价，走阔通常代表风险偏好下降。"),
    "investment_grade_spread": ("投资级信用利差", "企业融资压力和信用风险的温和口径。"),
    "financial_conditions": ("金融条件指数", "综合利率、信用、股票和汇率的金融环境指标。"),
    "dxy": ("美元指数DXY", "美元强弱影响全球流动性与风险资产偏好。"),
    "real_yield_10y": ("美国10年实际利率", "实际利率上行通常压制风险资产估值。"),
    "real_yield_5y": ("美国5年实际利率", "中期实际利率压力。"),
    "gold": ("黄金", "避险资产和实际利率预期的交叉验证。"),
    "vix": ("VIX波动率", "美股隐含波动率，衡量风险厌恶程度。"),
    "qqq": ("纳斯达克100 ETF", "科技股风险偏好的代表。"),
    "spy": ("标普500 ETF", "美股宽基风险偏好的代表。"),
    "hyg": ("高收益债 ETF", "信用风险偏好的交易型代理。"),
    "usd_cny": ("美元兑人民币", "离岸人民币压力与美元流动性的参考。"),
    "fomc_event_window": ("FOMC事件窗口", "美联储议息会议前后风险窗口。"),
}

ALIASES = {
    "effr": ("us_dff",),
    "us02y_yield": ("us_2y_yield",),
    "us10y_yield": ("us_10y_yield", "ust_10y_yield"),
    "us10y_2y_spread": ("us_10y_2y_spread",),
    "cpi_yoy": ("us_cpi_yoy",),
    "core_cpi_yoy": ("us_core_cpi_yoy",),
    "nfp": ("us_nfp",),
    "unemployment_rate": ("us_unemployment_rate",),
    "ism_manufacturing": ("ism_mfg_pmi",),
    "ism_services": ("ism_srv_pmi",),
    "hy_spread": ("hy_oas",),
    "reverse_repo": ("on_rrp",),
    "dxy": ("dollar_index",),
    "wti_oil": ("wti_crude",),
}

FALLBACK_LAYERS = (
    ("rates_policy", ("effr", "us02y_yield", "us10y_yield", "us10y_2y_spread")),
    ("inflation", ("cpi_yoy", "core_cpi_yoy", "breakeven_10y", "wti_oil")),
    ("growth_labor", ("nfp", "unemployment_rate", "ism_manufacturing", "ism_services")),
    ("liquidity_credit", ("hy_spread", "reverse_repo", "financial_conditions")),
    ("cross_asset_confirmation", ("dxy", "gold", "vix", "real_yield_10y")),
    ("event_window", ("fomc_event_window",)),
)


class MacroOverviewService:
    """Build a macro overview while keeping missing data out of scores."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build_overview(self, *, now: datetime | None = None) -> MacroOverviewResponse:
        now = now or datetime.now(UTC)
        observations = await self.repository.list_indicator_observations(limit=1200)
        definitions = {
            item.indicator_key: item
            for item in await self.repository.list_indicator_definitions(enabled_only=True)
        }
        events = await self.repository.list_macro_events(limit=300)
        latest_by_key = self._latest_observations(observations)

        layers: list[MacroOverviewLayerRead] = []
        layer_scores: dict[str, int] = {}
        for layer in self._load_layers():
            indicators = [
                self._indicator_read(layer, spec, latest_by_key, definitions)
                for spec in layer.indicators
            ]
            scored = [item for item in indicators if item.is_scored]
            score = (
                round(sum(_score_indicator(item) for item in scored) / len(scored))
                if scored
                else 50
            )
            layer_scores[layer.layer_key] = score
            layers.append(
                MacroOverviewLayerRead(
                    layer_key=layer.layer_key,
                    label_cn=layer.label_cn,
                    score=score,
                    bias=_score_to_bias(score),
                    summary=_layer_summary(layer.label_cn, score, scored, len(indicators)),
                    effective_count=len(scored),
                    total_count=len(indicators),
                    missing_count=sum(
                        1
                        for item in indicators
                        if item.status in {"missing", "unavailable_placeholder"}
                    ),
                    stale_count=sum(
                        1
                        for item in indicators
                        if item.status in {"stale", "stale_cache", "stale_seed"}
                    ),
                    cached_count=sum(
                        1
                        for item in indicators
                        if "cache" in item.status or item.status == "web_cached"
                    ),
                    is_scored=bool(scored),
                    not_scored_reason=None if scored else "当前层级缺少可评分数据。",
                    indicators=indicators,
                )
            )

        layer_contributions = _layer_contributions(layer_scores)
        total_score = _total_score(layer_contributions)
        event_items = _event_items(events, now)
        event_status, event_summary, next_event = _event_window(events, now)
        completeness = _data_completeness(layers)

        warnings = _warnings(layers)
        if event_status != "清晰":
            warnings.append(event_summary)

        return MacroOverviewResponse(
            regime_key=_regime_key(total_score),
            regime_label_cn=_regime_label(total_score),
            regime_summary=_regime_summary(total_score, completeness),
            policy_score=layer_scores.get("rates_policy", 50),
            inflation_score=layer_scores.get("inflation", 50),
            growth_score=layer_scores.get("growth_labor", 50),
            liquidity_score=layer_scores.get("liquidity_credit", 50),
            total_score=total_score,
            score_band=_score_band(total_score),
            score_explanation=_score_explanation(total_score, layer_contributions),
            confidence=_confidence(completeness),
            data_completeness=completeness,
            warnings=warnings,
            layer_contributions=layer_contributions,
            operation_bias=_operation_bias(total_score, completeness),
            event_window_status=event_status,
            event_window_summary=event_summary,
            next_event_title=next_event.title if next_event else None,
            next_event_at=next_event.scheduled_at if next_event else None,
            event_items=event_items,
            layers=layers,
        )

    def _load_layers(self) -> tuple[MacroLayerSpec, ...]:
        payload = _load_indicator_map()
        indicators = payload.get("indicators") if isinstance(payload, dict) else None
        if not isinstance(indicators, dict):
            return _fallback_layer_specs()

        grouped: dict[str, list[MacroIndicatorSpec]] = {key: [] for key in LAYER_LABELS}
        for key, item in indicators.items():
            if not isinstance(item, dict):
                continue
            layer_key = MODULE_TO_LAYER.get(str(item.get("module") or ""))
            if not layer_key:
                continue
            label, tooltip = _indicator_label(key)
            display_code, display_label = _display_fields(key, label)
            sources = item.get("sources") if isinstance(item.get("sources"), list) else []
            provider = (
                sources[0].get("source")
                if sources and isinstance(sources[0], dict)
                else None
            )
            grouped.setdefault(layer_key, []).append(
                MacroIndicatorSpec(
                    indicator_key=key,
                    label=label,
                    tooltip=tooltip,
                    layer_key=layer_key,
                    frequency=str(item.get("frequency") or "daily"),
                    unit=str(item.get("unit") or ""),
                    display_code=display_code,
                    display_label=display_label,
                    aliases=ALIASES.get(key, ()),
                    source_provider=provider,
                )
            )

        layers = [
            MacroLayerSpec(key, LAYER_LABELS[key], tuple(items))
            for key, items in grouped.items()
            if items
        ]
        if not any(layer.layer_key == "event_window" for layer in layers):
            event_specs = [
                MacroIndicatorSpec(
                    indicator_key="fomc_event_window",
                    label="FOMC事件窗口",
                    tooltip="美联储议息会议前后风险窗口。",
                    layer_key="event_window",
                    frequency="fomc",
                    source_provider="federal_reserve",
                )
            ]
            layers.append(
                MacroLayerSpec("event_window", LAYER_LABELS["event_window"], tuple(event_specs))
            )
        return tuple(layers) if layers else _fallback_layer_specs()

    def _indicator_read(
        self,
        layer: MacroLayerSpec,
        spec: MacroIndicatorSpec,
        latest_by_key: dict[str, Any],
        definitions: dict[str, Any],
    ) -> MacroOverviewIndicatorRead:
        _ = layer
        obs = _find_observation(latest_by_key, spec)
        if obs is None:
            fallback = fallback_for_indicator(spec.indicator_key, None, spec.frequency)
            return self._indicator_from_fallback(spec, fallback)

        fallback = fallback_for_indicator(spec.indicator_key, obs, spec.frequency)
        value = getattr(obs, "value_num", None)
        text_value = getattr(obs, "value_text", None)
        signal_state = getattr(obs, "signal_state", None)
        status = _normalize_status(signal_state, fallback.get("status"), value, text_value)
        is_scored = _is_scored_indicator(
            spec.indicator_key,
            status,
            signal_state,
            value,
            text_value,
            fallback.get("is_scored"),
        )
        block_reason = None if is_scored else _score_block_reason(status, fallback)
        definition = definitions.get(getattr(obs, "indicator_key", spec.indicator_key))
        tooltip = getattr(definition, "display_name", None) or spec.tooltip
        obs_ts = getattr(obs, "observation_ts", None)
        status_reason = _status_reason(status)

        return MacroOverviewIndicatorRead(
            indicator_key=spec.indicator_key,
            label=spec.label,
            display_code=spec.display_code,
            display_label=spec.display_label or spec.label,
            unit=spec.unit,
            tooltip=tooltip,
            region="global",
            source_provider=getattr(obs, "source_provider", None) or spec.source_provider,
            value_num=value if _decimal_or_none(value) is not None else None,
            value_text=text_value,
            observation_ts=obs_ts,
            signal_state=signal_state,
            status=status,
            fallback_level=fallback.get("fallback_level"),
            is_scored=is_scored,
            score_block_reason=block_reason,
            status_reason=status_reason,
            insight=_indicator_insight(
                spec.label,
                value,
                text_value,
                status,
                is_scored,
                obs_ts,
            ),
        )

    def _indicator_from_fallback(
        self,
        spec: MacroIndicatorSpec,
        fallback: dict[str, Any],
    ) -> MacroOverviewIndicatorRead:
        value = fallback.get("value")
        latest_date = fallback.get("latest_date")
        status = str(fallback.get("status") or "missing")
        status_reason = _status_reason(status)
        score_block_reason = fallback.get("score_block_reason")
        if status == "unavailable_placeholder":
            status_reason, score_block_reason = _placeholder_reason(spec)
        numeric = _decimal_or_none(value)
        is_scored = _is_scored_indicator(
            spec.indicator_key,
            status,
            None,
            numeric,
            None,
            fallback.get("is_scored"),
        )
        if not is_scored:
            score_block_reason = score_block_reason or _score_block_reason(status, fallback)
        return MacroOverviewIndicatorRead(
            indicator_key=spec.indicator_key,
            label=spec.label,
            display_code=spec.display_code,
            display_label=spec.display_label or spec.label,
            unit=spec.unit,
            tooltip=spec.tooltip,
            region="global",
            source_provider=str(fallback.get("source") or spec.source_provider or "placeholder"),
            value_num=numeric,
            value_text=None,
            observation_ts=_parse_datetime(latest_date),
            signal_state=None,
            status=status,
            fallback_level=fallback.get("fallback_level"),
            is_scored=is_scored,
            score_block_reason=score_block_reason,
            status_reason=status_reason,
            insight=_fallback_insight(spec.label, {**fallback, "is_scored": is_scored}),
        )

    def _latest_observations(self, observations: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in observations:
            if getattr(item, "category", None) != "macro":
                continue
            key = getattr(item, "indicator_key", None)
            if not key:
                continue
            current = result.get(key)
            if current is None or getattr(item, "observation_ts", datetime.min) > getattr(
                current,
                "observation_ts",
                datetime.min,
            ):
                result[key] = item
        return result


def _load_indicator_map() -> dict[str, Any]:
    if not INDICATOR_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDICATOR_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fallback_layer_specs() -> tuple[MacroLayerSpec, ...]:
    layers: list[MacroLayerSpec] = []
    for layer_key, indicator_keys in FALLBACK_LAYERS:
        specs = []
        for key in indicator_keys:
            label, tooltip = _indicator_label(key)
            display_code, display_label = _display_fields(key, label)
            specs.append(
                MacroIndicatorSpec(
                    indicator_key=key,
                    label=label,
                    tooltip=tooltip,
                    layer_key=layer_key,
                    display_code=display_code,
                    display_label=display_label,
                    aliases=ALIASES.get(key, ()),
                )
            )
        layers.append(MacroLayerSpec(layer_key, LAYER_LABELS[layer_key], tuple(specs)))
    return tuple(layers)


def _indicator_label(key: str) -> tuple[str, str]:
    if key in CLEAN_INDICATOR_LABELS:
        return CLEAN_INDICATOR_LABELS[key]
    if key in INDICATOR_LABELS:
        return INDICATOR_LABELS[key]
    readable = key.replace("_", " ").upper()
    return readable, f"{readable} 用于辅助判断宏观环境。"


def _display_fields(key: str, label: str) -> tuple[str | None, str]:
    code = DISPLAY_CODE_BY_INDICATOR.get(key)
    if not code:
        return None, label
    if label.upper().startswith(code.upper()):
        return code, label
    return code, f"{code} {label}"


def _find_observation(latest_by_key: dict[str, Any], spec: MacroIndicatorSpec) -> Any | None:
    for key in (spec.indicator_key, *spec.aliases):
        if key in latest_by_key:
            return latest_by_key[key]
    return None


def _normalize_status(
    signal_state: str | None,
    fallback_status: Any,
    value: Any | None,
    text_value: str | None,
) -> str:
    text = str(text_value or "").strip().lower()
    state = str(signal_state or "").strip().lower()
    if state in NON_SCORABLE_STATUSES or state in INVALID_TEXT_VALUES:
        return state
    if text in INVALID_TEXT_VALUES:
        return text if text != "unavailable" else "source_error"
    if value is None and text:
        return "ok"
    if fallback_status and str(fallback_status) not in {"missing", "pending"}:
        return str(fallback_status)
    return "ok"


def _is_scored_indicator(
    indicator_key: str,
    status: str,
    signal_state: str | None,
    value: Any | None,
    text_value: str | None,
    fallback_scored: Any,
) -> bool:
    normalized_status = str(status or "missing").lower()
    normalized_signal = str(signal_state or "").lower()
    normalized_text = str(text_value or "").strip().lower()
    if normalized_status in NON_SCORABLE_STATUSES or normalized_signal in NON_SCORABLE_STATUSES:
        return False
    if normalized_text in INVALID_TEXT_VALUES:
        return False
    if _decimal_or_none(value) is not None:
        return bool(fallback_scored)
    return indicator_key in SCORABLE_TEXT_INDICATORS and normalized_text in {"active", "inactive"}


def _score_block_reason(status: str, fallback: dict[str, Any]) -> str:
    return (
        fallback.get("score_block_reason")
        or fallback.get("status_reason")
        or _status_reason(status)
    )


def _decimal_or_none(value: Any | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _score_indicator(item: MacroOverviewIndicatorRead) -> int:
    value = item.value_num
    key = item.indicator_key
    if value is None and item.value_text:
        return 50
    if value is None:
        return 50
    x = float(value)

    if key in {"effr", "sofr", "us03m_yield", "us02y_yield", "us10y_yield", "us30y_yield"}:
        return _inverse_score(x, low=2.5, high=6.0)
    if key in {"real_yield_10y", "real_yield_5y"}:
        return _inverse_score(x, low=0.5, high=2.8)
    if key in {"us10y_2y_spread", "us10y_3m_spread"}:
        return _range_score(x, bearish_below=-0.7, bullish_above=0.4)
    if key in {
        "cpi_yoy",
        "core_cpi_yoy",
        "pce_yoy",
        "core_pce_yoy",
        "breakeven_5y",
        "breakeven_10y",
    }:
        return _inverse_score(x, low=2.0, high=5.0)
    if key in {"cpi_mom", "core_cpi_mom"}:
        return _inverse_score(x, low=0.15, high=0.55)
    if key in {"nfp", "retail_sales", "gdp_qoq"}:
        return _direct_score(x, low=0.0, high=250.0)
    if key in {"unemployment_rate", "initial_claims", "continuing_claims"}:
        return _inverse_score(x, low=3.5, high=5.5)
    if key in {"ism_manufacturing", "ism_services"}:
        return _direct_score(x, low=45.0, high=55.0)
    if key in {"hy_spread", "investment_grade_spread", "vix"}:
        return _inverse_score(x, low=3.5, high=8.0)
    if key in {"dxy", "usd_cny"}:
        return _inverse_score(x, low=98.0, high=108.0)
    if key in {"gold", "qqq", "spy", "hyg"}:
        return _direct_score(x, low=0.0, high=max(x * 1.2, 1.0))
    if key in {"wti_oil"}:
        return _range_mid_score(x, low=55.0, high=95.0)
    return 50


def _direct_score(value: float, *, low: float, high: float) -> int:
    return round(_clamp((value - low) / (high - low)) * 100)


def _inverse_score(value: float, *, low: float, high: float) -> int:
    return 100 - _direct_score(value, low=low, high=high)


def _range_score(value: float, *, bearish_below: float, bullish_above: float) -> int:
    return _direct_score(value, low=bearish_below, high=bullish_above)


def _range_mid_score(value: float, *, low: float, high: float) -> int:
    midpoint = (low + high) / 2
    distance = abs(value - midpoint) / ((high - low) / 2)
    return round((1 - _clamp(distance)) * 100)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_to_bias(score: int) -> str:
    if score >= 65:
        return "偏多"
    if score <= 35:
        return "偏空"
    return "中性"


def _score_band(score: int) -> str:
    if score >= 70:
        return "偏宽松"
    if score >= 55:
        return "中性偏暖"
    if score <= 30:
        return "偏紧"
    if score <= 45:
        return "中性偏紧"
    return "中性震荡"


def _layer_summary(
    label: str,
    score: int,
    scored: list[MacroOverviewIndicatorRead],
    total: int,
) -> str:
    if not scored:
        return f"{label}暂无可评分数据，仅保留状态展示。"
    return f"{label}当前为{_score_to_bias(score)}，有效指标 {len(scored)}/{total}。"


def _layer_contributions(layer_scores: dict[str, int]) -> dict[str, float]:
    weights = {
        "rates_policy": 0.25,
        "inflation": 0.2,
        "growth_labor": 0.2,
        "liquidity_credit": 0.15,
        "cross_asset_confirmation": 0.12,
        "event_window": 0.08,
    }
    return {
        key: round((layer_scores.get(key, 50) - 50) * weight, 2)
        for key, weight in weights.items()
    }


def _total_score(contributions: dict[str, float]) -> int:
    return round(max(0, min(100, 50 + sum(contributions.values()))))


def _data_completeness(layers: list[MacroOverviewLayerRead]) -> dict[str, float]:
    total = sum(layer.total_count for layer in layers)
    effective = sum(layer.effective_count for layer in layers)
    ratio = effective / total if total else 0.0
    return {
        "effective_count": effective,
        "total_count": total,
        "ratio": round(ratio, 4),
        "percent": round(ratio * 100, 2),
    }


def _confidence(completeness: dict[str, float]) -> str:
    ratio = float(completeness.get("ratio") or 0)
    if ratio >= 0.75:
        return "high"
    if ratio >= 0.45:
        return "medium"
    return "low"


def _operation_bias(score: int, completeness: dict[str, float]) -> str:
    if float(completeness.get("ratio") or 0) < 0.35:
        return "observe"
    if score >= 65:
        return "bullish"
    if score <= 35:
        return "bearish"
    return "neutral"


def _regime_key(score: int) -> str:
    if score >= 65:
        return "risk_on"
    if score <= 35:
        return "risk_off"
    return "neutral"


def _regime_label(score: int) -> str:
    return {
        "risk_on": "风险偏好改善",
        "risk_off": "风险偏好承压",
        "neutral": "中性震荡",
    }[_regime_key(score)]


def _regime_summary(score: int, completeness: dict[str, float]) -> str:
    return (
        f"宏观总分 {score}，评分区间为{_score_band(score)}；可评分指标 "
        f"{int(completeness.get('effective_count') or 0)}/"
        f"{int(completeness.get('total_count') or 0)}。"
    )


def _score_explanation(score: int, contributions: dict[str, float]) -> str:
    parts = [
        f"{LAYER_LABELS.get(key, key)}贡献 {value:+.2f}"
        for key, value in contributions.items()
    ]
    return "宏观总分以 50 的中性基准为起点；" + "；".join(parts) + f"；当前总分 {score}。"


def _warnings(layers: list[MacroOverviewLayerRead]) -> list[str]:
    warnings: list[str] = []
    for layer in layers:
        if not layer.is_scored:
            warnings.append(f"{layer.label_cn}暂无可评分数据。")
        elif layer.effective_count < max(1, layer.total_count // 3):
            warnings.append(f"{layer.label_cn}有效指标偏少，置信度较低。")
    return warnings[:6]


def _indicator_insight(
    label: str,
    value: Any | None,
    text_value: str | None,
    status: str,
    is_scored: bool,
    observation_ts: datetime | None,
) -> str:
    if not is_scored:
        return f"{label}暂不参与评分：{_status_reason(status)}"
    shown = _format_macro_value(value, text_value)
    suffix = f"，更新时间 {observation_ts.date().isoformat()}" if observation_ts else ""
    return f"{label}：{shown}{suffix}。"


def _format_macro_value(value: Any | None, text_value: str | None = None) -> str:
    shown = value if value is not None else text_value
    if shown is None or shown == "":
        return "—"
    if str(shown).strip().lower() in INVALID_TEXT_VALUES:
        return "—"
    number = _decimal_or_none(shown)
    if number is None:
        return str(shown)
    rounded = number.quantize(Decimal("0.01"))
    return format(rounded.normalize(), "f")


def _fallback_insight(label: str, fallback: dict[str, Any]) -> str:
    if fallback.get("is_scored"):
        return f"{label}使用{_fallback_label(fallback.get('fallback_level'))}，已纳入评分。"
    reason = fallback.get("score_block_reason") or fallback.get("status_reason") or "暂不参与评分。"
    return f"{label}暂不参与评分：{reason}"


def _fallback_label(value: Any) -> str:
    mapping = {
        "live_api": "实时接口",
        "seed_cache": "种子缓存",
        "stale_cache": "过期缓存",
        "web_cached": "网页快照",
        "unavailable_placeholder": "占位行",
    }
    return mapping.get(str(value), "缓存")


def _status_reason(status: str) -> str:
    mapping = {
        "ok": "数据可用。",
        "live": "实时接口可用。",
        "cached": "使用缓存数据。",
        "stale_cache": "使用过期缓存，置信度降低。",
        "seed_cache": "使用种子缓存，置信度较低。",
        "stale_seed": "种子缓存过期，只展示不评分。",
        "web_cached": "网页快照只展示不评分。",
        "missing": "缺少观测值。",
        "auth_missing": "数据源未配置 API Key。",
        "unavailable": "数据源暂不可用。",
        "unavailable_placeholder": "占位行不参与评分。",
        "source_error": "数据源请求失败。",
        "rate_limited": "数据源限流。",
        "parser_error": "数据源返回格式无法解析。",
        "disabled": "数据源已禁用。",
        "not_implemented": "数据源尚未接入。",
        "pending": "后台正在准备数据。",
        "pending_release": "指标等待正式发布。",
        "proxy_required_unavailable": "当前网络可能需要代理，但未检测到可用代理。",
    }
    return mapping.get(str(status), "状态暂不可用。")


def _placeholder_reason(spec: MacroIndicatorSpec) -> tuple[str, str]:
    provider = (spec.source_provider or "").lower()
    if spec.indicator_key in {"us10y_2y_spread", "us10y_3m_spread", "real_yield_10y"}:
        return (
            "该指标依赖其他宏观序列，依赖项缺失时不会派生。",
            "缺依赖指标",
        )
    if provider in {"tiingo", "openexchangerates", "alpha_vantage", "twelvedata"}:
        return (
            "当前指标需要外部行情源，便携版默认不强制配置。",
            "待接入行情源或 API Key",
        )
    if provider in {"fred", "bls", "bea"}:
        return (
            "当前运行缓存中没有该指标，需要执行宏观刷新并确认数据源可达。",
            "同步未运行或缓存未命中",
        )
    return (
        "当前指标尚未配置可用数据源映射。",
        "无数据源映射",
    )


def _event_items(events: list[Any], now: datetime) -> list[MacroOverviewEventRead]:
    items: list[MacroOverviewEventRead] = []
    for event in events[:30]:
        scheduled = _ensure_aware(event.scheduled_at)
        delta_hours = (scheduled - now).total_seconds() / 3600
        if abs(delta_hours) > 24 * 14:
            continue
        label = "已发布" if scheduled <= now else "即将发布"
        items.append(
            MacroOverviewEventRead(
                event_id=event.event_id,
                event_key=event.event_key,
                title=event.title,
                country_code=event.country_code,
                importance=event.importance,
                status=event.status,
                scheduled_at=scheduled,
                actual_value_num=event.actual_value_num,
                consensus_value_num=event.consensus_value_num,
                previous_value_num=event.previous_value_num,
                surprise_num=event.surprise_num,
                window_label=label,
                summary=f"{event.title}处于宏观事件观察窗口。",
            )
        )
    return items


def _event_window(events: list[Any], now: datetime) -> tuple[str, str, Any | None]:
    future = [event for event in events if _ensure_aware(event.scheduled_at) >= now]
    future.sort(key=lambda item: _ensure_aware(item.scheduled_at))
    if not future:
        return "清晰", "暂无临近高影响宏观事件。", None
    next_event = future[0]
    hours = (_ensure_aware(next_event.scheduled_at) - now).total_seconds() / 3600
    if hours <= 24:
        return "临近发布", f"下一项重点事件为 {next_event.title}，建议降低事件前追单。", next_event
    return "清晰", f"下一项重点事件为 {next_event.title}。", next_event


def _parse_datetime(value: Any | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
