from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    MacroOverviewEventRead,
    MacroOverviewIndicatorRead,
    MacroOverviewLayerRead,
    MacroOverviewResponse,
)

UTC = timezone.utc


@dataclass(frozen=True)
class MacroIndicatorSpec:
    indicator_key: str
    label: str
    tooltip: str
    region: str = "global"


@dataclass(frozen=True)
class MacroLayerSpec:
    layer_key: str
    label_cn: str
    indicators: tuple[MacroIndicatorSpec, ...]


class MacroOverviewService:
    """Build a user-facing macro overview without treating missing data as zero."""

    LAYERS: tuple[MacroLayerSpec, ...] = (
        MacroLayerSpec(
            "rates_policy",
            "利率与政策",
            (
                MacroIndicatorSpec("us_dff", "美国有效联邦基金利率", "美联储政策利率的实际成交水平。", "US"),
                MacroIndicatorSpec("us_2y_yield", "美国2年期国债收益率", "短端利率预期，反映市场对政策路径的定价。", "US"),
                MacroIndicatorSpec("us_10y_yield", "美国10年期国债收益率", "长端无风险利率，是风险资产估值的重要折现锚。", "US"),
                MacroIndicatorSpec("us_10y_2y_spread", "美债10Y-2Y利差", "收益率曲线斜率，用于观察衰退预期和政策压力。", "US"),
            ),
        ),
        MacroLayerSpec(
            "inflation",
            "通胀与价格",
            (
                MacroIndicatorSpec("us_cpi_yoy", "美国CPI同比", "美国居民消费价格指数同比，是通胀主指标。", "US"),
                MacroIndicatorSpec("us_core_cpi_yoy", "美国核心CPI同比", "剔除食品和能源后的通胀，更能反映粘性通胀。", "US"),
                MacroIndicatorSpec("breakeven_10y", "美国10年通胀预期", "TIPS 隐含通胀预期，衡量市场对未来通胀的定价。", "US"),
                MacroIndicatorSpec("wti_crude", "WTI原油", "能源价格会影响通胀预期和风险偏好。", "global"),
            ),
        ),
        MacroLayerSpec(
            "growth_labor",
            "增长与就业",
            (
                MacroIndicatorSpec("us_nfp", "美国非农就业", "美国非农新增就业人数，影响政策预期和风险偏好。", "US"),
                MacroIndicatorSpec("us_unemployment_rate", "美国失业率", "劳动市场松紧程度。", "US"),
                MacroIndicatorSpec("ism_mfg_pmi", "美国ISM制造业PMI", "制造业景气度，50以上通常代表扩张。", "US"),
                MacroIndicatorSpec("ism_srv_pmi", "美国ISM服务业PMI", "服务业景气度，对美国经济韧性更敏感。", "US"),
            ),
        ),
        MacroLayerSpec(
            "liquidity_credit",
            "流动性与信用",
            (
                MacroIndicatorSpec("hy_oas", "美国高收益债利差", "信用风险溢价，利差走阔通常代表风险偏好下降。", "US"),
                MacroIndicatorSpec("tga", "美国财政部TGA", "财政部现金账户变化会影响美元流动性。", "US"),
                MacroIndicatorSpec("on_rrp", "隔夜逆回购余额", "美联储隔夜逆回购余额，反映流动性停放规模。", "US"),
                MacroIndicatorSpec("financial_conditions", "美国金融条件指数", "综合利率、信用、股市和汇率的金融环境指标。", "US"),
            ),
        ),
        MacroLayerSpec(
            "cross_asset_confirmation",
            "跨资产确认",
            (
                MacroIndicatorSpec("dollar_index", "美元指数DXY", "美元强弱影响全球流动性与加密资产风险偏好。", "global"),
                MacroIndicatorSpec("gold", "黄金", "避险资产与实际利率预期的交叉验证。", "global"),
                MacroIndicatorSpec("vix", "VIX波动率", "美股隐含波动率，衡量风险厌恶程度。", "US"),
                MacroIndicatorSpec("ust_10y_yield", "美债10年收益率", "跨资产确认用的长端利率。", "US"),
            ),
        ),
        MacroLayerSpec(
            "event_window",
            "事件窗口",
            (
                MacroIndicatorSpec("fomc_event_window", "FOMC事件窗口", "美联储议息会议附近的事件风险。", "US"),
                MacroIndicatorSpec("us_cpi_yoy", "美国CPI事件", "CPI公布窗口对风险资产波动的影响。", "US"),
                MacroIndicatorSpec("us_nfp", "美国非农事件", "非农公布窗口对政策预期的影响。", "US"),
            ),
        ),
    )

    STALE_LIMITS: dict[str, timedelta] = {
        "event_window": timedelta(days=30),
        "growth_labor": timedelta(days=45),
        "inflation": timedelta(days=45),
        "liquidity_credit": timedelta(days=21),
        "rates_policy": timedelta(days=7),
        "cross_asset_confirmation": timedelta(days=7),
    }

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build_overview(self, *, now: datetime | None = None) -> MacroOverviewResponse:
        now = now or datetime.now(UTC)
        observations = await self.repository.list_indicator_observations(limit=800)
        definitions = {
            item.indicator_key: item
            for item in await self.repository.list_indicator_definitions(enabled_only=True)
        }
        events = await self.repository.list_macro_events(limit=300)
        latest_by_key = self._latest_observations(observations)

        layers: list[MacroOverviewLayerRead] = []
        layer_scores: dict[str, int] = {}
        for layer in self.LAYERS:
            indicators = [
                self._indicator_read(layer, spec, latest_by_key.get(spec.indicator_key), definitions, now)
                for spec in layer.indicators
            ]
            scored = [item for item in indicators if item.is_scored]
            score = round(sum(_score_indicator(item) for item in scored) / len(scored)) if scored else 50
            layer_scores[layer.layer_key] = score
            layers.append(
                MacroOverviewLayerRead(
                    layer_key=layer.layer_key,
                    label_cn=layer.label_cn,
                    score=score,
                    bias=_score_to_bias(score),
                    summary=_layer_summary(layer.layer_key, score, scored, len(indicators)),
                    effective_count=len(scored),
                    total_count=len(indicators),
                    missing_count=sum(1 for item in indicators if item.status == "missing"),
                    stale_count=sum(1 for item in indicators if item.status == "stale"),
                    cached_count=sum(1 for item in indicators if item.status == "cached"),
                    is_scored=bool(scored),
                    not_scored_reason=None if scored else "当前层级缺少可评分数据",
                    indicators=indicators,
                )
            )

        layer_contributions = _layer_contributions(layer_scores)
        total_score = _total_score(layer_contributions)
        event_items = _event_items(events, now)
        event_status, event_summary, next_event = _event_window(events, now)
        operation_bias = _operation_bias(total_score, event_status)

        return MacroOverviewResponse(
            regime_key=_regime_key(total_score),
            regime_label_cn=_score_band(total_score),
            regime_summary=_regime_summary(total_score),
            policy_score=layer_scores.get("rates_policy", 50),
            inflation_score=layer_scores.get("inflation", 50),
            growth_score=layer_scores.get("growth_labor", 50),
            liquidity_score=layer_scores.get("liquidity_credit", 50),
            total_score=total_score,
            score_scale="0 ~ 100",
            score_band=_score_band(total_score),
            score_explanation=_score_explanation(layer_contributions),
            confidence=_confidence(layers),
            data_completeness=_completeness(layers),
            warnings=_warnings(layers, total_score),
            layer_contributions=layer_contributions,
            operation_bias=operation_bias,
            event_window_status=event_status,
            event_window_summary=event_summary,
            next_event_title=next_event.title if next_event else None,
            next_event_at=next_event.scheduled_at if next_event else None,
            event_items=event_items,
            layers=layers,
        )

    @staticmethod
    def _latest_observations(observations: list[Any]) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for item in observations:
            current = latest.get(item.indicator_key)
            if current is None or item.observation_ts > current.observation_ts:
                latest[item.indicator_key] = item
        return latest

    def _indicator_read(
        self,
        layer: MacroLayerSpec,
        spec: MacroIndicatorSpec,
        observation: Any | None,
        definitions: dict[str, Any],
        now: datetime,
    ) -> MacroOverviewIndicatorRead:
        definition = definitions.get(spec.indicator_key)
        source_provider = getattr(definition, "source_provider", None) if definition else None
        if observation is None:
            return MacroOverviewIndicatorRead(
                indicator_key=spec.indicator_key,
                label=spec.label,
                tooltip=spec.tooltip,
                region=spec.region,
                source_provider=source_provider,
                status="missing",
                is_scored=False,
                status_reason="暂无可用观测值",
                signal_state=None,
                insight=f"{spec.label} 暂无可评分数据。",
            )

        age = now - observation.observation_ts
        stale_limit = self.STALE_LIMITS.get(layer.layer_key, timedelta(days=14))
        is_stale = age > stale_limit
        status = "stale" if is_stale else "live"
        status_reason = "数据已过期，暂不参与评分" if is_stale else "数据有效，参与评分"
        return MacroOverviewIndicatorRead(
            indicator_key=spec.indicator_key,
            label=spec.label,
            tooltip=spec.tooltip,
            region=spec.region,
            source_provider=getattr(observation, "source_provider", source_provider),
            value_num=observation.value_num,
            value_text=observation.value_text,
            observation_ts=observation.observation_ts,
            signal_state=observation.signal_state,
            status=status,
            is_scored=not is_stale,
            status_reason=status_reason,
            insight=_indicator_insight(spec.label, observation.value_num, observation.signal_state, status),
        )


def _score_indicator(item: MacroOverviewIndicatorRead) -> int:
    state_scores = {
        "bullish": 70,
        "bearish": 30,
        "strong": 70,
        "weak": 35,
        "positive": 65,
        "negative": 35,
        "risk_on": 72,
        "risk_off": 25,
        "neutral": 50,
        "normal": 50,
    }
    if item.signal_state in state_scores:
        return state_scores[item.signal_state]
    if item.value_num is None:
        return 50
    value = Decimal(str(item.value_num))
    key = item.indicator_key
    if key in {"us_dff", "us_2y_yield", "us_10y_yield", "ust_10y_yield"}:
        if value >= Decimal("5"):
            return 30
        if value >= Decimal("4"):
            return 42
        if value <= Decimal("2"):
            return 65
        return 50
    if key in {"us_cpi_yoy", "us_core_cpi_yoy", "breakeven_10y"}:
        if value >= Decimal("4"):
            return 25
        if value >= Decimal("3"):
            return 38
        if value <= Decimal("2.2"):
            return 62
        return 50
    if key in {"hy_oas", "vix", "financial_conditions"}:
        if value >= Decimal("25") and key == "vix":
            return 25
        if value >= Decimal("5") and key == "hy_oas":
            return 28
        return 50
    if key in {"us_nfp", "ism_mfg_pmi", "ism_srv_pmi"}:
        if value >= Decimal("50"):
            return 60
        return 40
    return 50


def _score_to_bias(score: int) -> str:
    if score >= 58:
        return "偏多"
    if score <= 42:
        return "偏空"
    return "中性"


def _layer_summary(layer_key: str, score: int, scored: list[Any], total: int) -> str:
    if not scored:
        return "当前层级缺少有效数据，暂不单独给出方向判断。"
    names = {
        "rates_policy": "利率与政策",
        "inflation": "通胀与价格",
        "growth_labor": "增长与就业",
        "liquidity_credit": "流动性与信用",
        "cross_asset_confirmation": "跨资产确认",
        "event_window": "事件窗口",
    }
    return f"{names.get(layer_key, '宏观层级')}当前为{_score_to_bias(score)}，有效指标 {len(scored)}/{total}。"


def _indicator_insight(label: str, value: Decimal | None, state: str | None, status: str) -> str:
    if status == "stale":
        return f"{label} 数据已过期，当前只作为背景信息。"
    if value is None:
        return f"{label} 暂无数值。"
    state_text = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}.get(state or "", "中性")
    return f"{label} 最新值为 {value}，系统解读为{state_text}。"


def _layer_contributions(layer_scores: dict[str, int]) -> dict[str, float]:
    weights = {
        "rates_policy": 0.24,
        "inflation": 0.22,
        "growth_labor": 0.18,
        "liquidity_credit": 0.18,
        "cross_asset_confirmation": 0.12,
        "event_window": 0.06,
    }
    return {
        key: round((layer_scores.get(key, 50) - 50) * weight, 2)
        for key, weight in weights.items()
    }


def _total_score(contributions: dict[str, float]) -> int:
    return max(0, min(100, round(50 + sum(contributions.values()))))


def _score_band(score: int) -> str:
    if score >= 70:
        return "风险偏好较强"
    if score >= 58:
        return "风险偏好温和"
    if score <= 30:
        return "风险收缩较强"
    if score <= 42:
        return "风险偏好偏弱"
    return "中性震荡"


def _regime_key(score: int) -> str:
    if score >= 58:
        return "risk_on"
    if score <= 42:
        return "risk_off"
    return "neutral"


def _regime_summary(score: int) -> str:
    if score >= 58:
        return "宏观环境偏向支持风险资产，但仍需要价格结构确认。"
    if score <= 42:
        return "宏观环境偏谨慎，风险资产更容易受到流动性或政策压力影响。"
    return "宏观环境方向不强，建议结合价格结构和事件窗口观察。"


def _score_explanation(contributions: dict[str, float]) -> str:
    labels = {
        "rates_policy": "利率与政策",
        "inflation": "通胀与价格",
        "growth_labor": "增长与就业",
        "liquidity_credit": "流动性与信用",
        "cross_asset_confirmation": "跨资产确认",
        "event_window": "事件窗口",
    }
    parts = ["宏观总分以 50 的中性基准为起点"]
    for key, value in contributions.items():
        parts.append(f"{labels.get(key, key)}贡献 {value:+.2f}")
    return "；".join(parts)


def _confidence(layers: list[MacroOverviewLayerRead]) -> str:
    completeness = _completeness(layers).get("ratio", 0)
    if completeness >= 0.75:
        return "high"
    if completeness >= 0.5:
        return "medium"
    if completeness >= 0.25:
        return "low"
    return "insufficient"


def _completeness(layers: list[MacroOverviewLayerRead]) -> dict[str, float]:
    total = sum(layer.total_count for layer in layers)
    effective = sum(layer.effective_count for layer in layers)
    return {
        "effective_count": float(effective),
        "total_count": float(total),
        "ratio": round(effective / total, 3) if total else 0.0,
    }


def _warnings(layers: list[MacroOverviewLayerRead], total_score: int) -> list[str]:
    warnings: list[str] = []
    if _completeness(layers).get("ratio", 0) < 0.5:
        warnings.append("当前有效宏观指标不足，宏观总分只作为低置信度参考。")
    if total_score <= 30:
        warnings.append("宏观总分处于低位，系统判断当前风险偏好偏弱。")
    elif total_score >= 70:
        warnings.append("宏观总分处于高位，但仍需要价格结构确认。")
    return warnings


def _operation_bias(total_score: int, event_status: str) -> str:
    if event_status == "临近发布":
        return "观望"
    if total_score >= 58:
        return "偏多"
    if total_score <= 42:
        return "偏空"
    return "观望"


def _event_items(events: list[Any], now: datetime) -> list[MacroOverviewEventRead]:
    items: list[MacroOverviewEventRead] = []
    for event in sorted(events, key=lambda item: item.scheduled_at)[:12]:
        delta = event.scheduled_at - now
        if delta.total_seconds() >= 0:
            window = "即将发布" if delta <= timedelta(days=3) else "未来事件"
        else:
            window = "已发布" if abs(delta) <= timedelta(days=3) else "历史事件"
        items.append(
            MacroOverviewEventRead(
                event_id=event.event_id,
                event_key=event.event_key,
                title=event.title,
                country_code=event.country_code,
                importance=event.importance,
                status=event.status,
                scheduled_at=event.scheduled_at,
                actual_value_num=event.actual_value_num,
                consensus_value_num=event.consensus_value_num,
                previous_value_num=event.previous_value_num,
                surprise_num=event.surprise_num,
                window_label=window,
                summary="事件已纳入宏观风险窗口监控。",
            )
        )
    return items


def _event_window(events: list[Any], now: datetime) -> tuple[str, str, Any | None]:
    future = sorted((event for event in events if event.scheduled_at >= now), key=lambda item: item.scheduled_at)
    if not future:
        return "无临近事件", "当前没有临近的高优先级宏观事件。", None
    next_event = future[0]
    delta = next_event.scheduled_at - now
    if delta <= timedelta(days=1):
        return "临近发布", f"{next_event.title} 将在 24 小时内发布，建议降低事件前追单权重。", next_event
    if delta <= timedelta(days=3):
        return "事件临近", f"{next_event.title} 将在 3 天内发布，注意波动率抬升。", next_event
    return "常规窗口", "当前没有迫近的重大宏观事件。", next_event
