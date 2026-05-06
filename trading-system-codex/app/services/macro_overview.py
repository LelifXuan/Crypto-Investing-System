from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    MacroOverviewEventRead,
    MacroOverviewIndicatorRead,
    MacroOverviewLayerRead,
    MacroOverviewResponse,
)

ZERO = Decimal("0")


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
    LAYERS: tuple[MacroLayerSpec, ...] = (
        MacroLayerSpec(
            layer_key="rates_policy",
            label_cn="利率 / 政策",
            indicators=(
                MacroIndicatorSpec(
                    "us_dff",
                    "US DFF",
                    "联邦基金利率决定美元资金成本与风险偏好的上限。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_2y_yield",
                    "US 2Y YIELD",
                    "2 年期美债最敏感地反映政策路径预期。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_10y_yield",
                    "US 10Y YIELD",
                    "10 年期收益率决定长端折现率与成长资产估值压力。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_10y_2y_spread",
                    "US 10Y 2Y SPREAD",
                    "期限利差用于识别紧缩、倒挂与修复。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "cn_omo_net",
                    "CN OMO NET",
                    "公开市场净投放或回笼反映短端流动性的松紧变化。",
                    region="CN",
                ),
                MacroIndicatorSpec(
                    "cn_fr007", "CN FR007", "FR007 代表中国资金面的边际松紧。", region="CN"
                ),
            ),
        ),
        MacroLayerSpec(
            layer_key="inflation",
            label_cn="通胀",
            indicators=(
                MacroIndicatorSpec(
                    "us_cpi_yoy",
                    "US CPI YOY",
                    "整体通胀决定市场能否继续交易宽松预期。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_core_cpi_yoy",
                    "US CORE CPI YOY",
                    "核心通胀黏性决定政策转向的难度。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "breakeven_10y",
                    "US 10Y BREAKEVEN",
                    "隐含通胀预期用于确认再通胀或降温方向。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "wti_crude", "WTI CRUDE", "油价抬升往往会放大输入型通胀压力。", region="global"
                ),
                MacroIndicatorSpec(
                    "cn_cpi_yoy", "CN CPI YOY", "中国 CPI 用于确认内需与居民物价压力。", region="CN"
                ),
                MacroIndicatorSpec(
                    "cn_ppi_yoy",
                    "CN PPI YOY",
                    "中国 PPI 反映工业链价格压力与制造业修复斜率。",
                    region="CN",
                ),
            ),
        ),
        MacroLayerSpec(
            layer_key="growth_labor",
            label_cn="增长 / 就业",
            indicators=(
                MacroIndicatorSpec(
                    "us_nfp", "US NFP", "非农就业决定增长韧性与政策维持偏紧的风险。", region="US"
                ),
                MacroIndicatorSpec(
                    "unemployment_rate",
                    "US UNEMPLOYMENT RATE",
                    "失业率上行常是增长拐点信号。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "ism_mfg_pmi",
                    "US ISM MFG PMI",
                    "制造业 PMI 用于确认增长修复或收缩。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "ism_srv_pmi", "US ISM SRV PMI", "服务 PMI 更贴近总需求韧性。", region="US"
                ),
                MacroIndicatorSpec(
                    "cn_pmi_mfg",
                    "CN PMI MFG",
                    "中国制造业 PMI 影响全球商品链和风险偏好。",
                    region="CN",
                ),
                MacroIndicatorSpec(
                    "cn_retail_sales_yoy",
                    "CN RETAIL SALES YOY",
                    "社零代表内需与消费修复速度。",
                    region="CN",
                ),
            ),
        ),
        MacroLayerSpec(
            layer_key="liquidity_credit",
            label_cn="流动性 / 信用",
            indicators=(
                MacroIndicatorSpec(
                    "hy_oas", "HY OAS", "高收益信用利差恶化通常先于风险资产承压。", region="US"
                ),
                MacroIndicatorSpec(
                    "tga", "US TGA", "TGA 变化会影响美元流动性的抽水节奏。", region="US"
                ),
                MacroIndicatorSpec(
                    "on_rrp", "US ON RRP", "ON RRP 变化代表系统内闲置流动性的缓冲。", region="US"
                ),
                MacroIndicatorSpec(
                    "financial_conditions",
                    "US FINANCIAL CONDITIONS",
                    "金融条件决定风险资产承压还是缓解。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "cn_shibor_3m",
                    "CN SHIBOR 3M",
                    "Shibor 反映中国信用与流动性的松紧。",
                    region="CN",
                ),
                MacroIndicatorSpec(
                    "cn_10y_cgb",
                    "CN 10Y CGB",
                    "中债收益率曲线反映国内增长和信用预期。",
                    region="CN",
                ),
            ),
        ),
        MacroLayerSpec(
            layer_key="cross_asset_confirmation",
            label_cn="跨资产确认",
            indicators=(
                MacroIndicatorSpec(
                    "dollar_index",
                    "DOLLAR INDEX",
                    "美元方向确认全球风险偏好与流动性。",
                    region="global",
                ),
                MacroIndicatorSpec(
                    "gold", "GOLD", "黄金结合利率与美元判断避险还是宽松交易。", region="global"
                ),
                MacroIndicatorSpec("vix", "VIX", "VIX 直接确认风险偏好是否恶化。", region="US"),
                MacroIndicatorSpec(
                    "ust_10y_yield",
                    "UST 10Y YIELD",
                    "长端利率用于确认估值压力是否缓解。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "cn_usdcny",
                    "USD CNY",
                    "人民币方向可确认中国流动性与资本流向压力。",
                    region="CN",
                ),
            ),
        ),
        MacroLayerSpec(
            layer_key="event_window",
            label_cn="事件窗口",
            indicators=(
                MacroIndicatorSpec(
                    "fomc_event_window",
                    "FOMC EVENT WINDOW",
                    "核心宏观事件窗口优先影响仓位管理。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_cpi_yoy",
                    "US CPI YOY",
                    "美国通胀发布时间经常触发利率与风险资产重定价。",
                    region="US",
                ),
                MacroIndicatorSpec(
                    "us_nfp", "US NFP", "就业数据发布时间会放大美元和收益率波动。", region="US"
                ),
                MacroIndicatorSpec(
                    "cn_mof_bond_issuance",
                    "CN MOF BOND ISSUANCE",
                    "国债发行与供给压力会影响流动性和债市节奏。",
                    region="CN",
                ),
            ),
        ),
    )

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

        latest_by_key: dict[str, object] = {}
        for item in observations:
            current = latest_by_key.get(item.indicator_key)
            if current is None or item.observation_ts > current.observation_ts:
                latest_by_key[item.indicator_key] = item

        layers: list[MacroOverviewLayerRead] = []
        layer_scores: dict[str, int] = {}
        for layer in self.LAYERS:
            indicators = []
            for spec in layer.indicators:
                if layer.layer_key == "event_window":
                    indicators.append(self._build_event_indicator_read(spec, events, now))
                else:
                    indicators.append(
                        self._build_indicator_read(
                            spec,
                            definitions.get(spec.indicator_key),
                            latest_by_key.get(spec.indicator_key),
                        )
                    )
            score = self._score_layer(layer.layer_key, indicators)
            layer_scores[layer.layer_key] = score
            layers.append(
                MacroOverviewLayerRead(
                    layer_key=layer.layer_key,
                    label_cn=layer.label_cn,
                    score=score,
                    bias=self._score_to_bias(score),
                    summary=self._layer_summary(layer.layer_key, score, indicators, now, events),
                    indicators=indicators,
                )
            )

        event_status, event_summary, next_event_title, next_event_at = self._event_window(
            now, events
        )
        event_items = self._build_event_items(now, events)
        policy_score = layer_scores.get("rates_policy", 0)
        inflation_score = layer_scores.get("inflation", 0)
        growth_score = layer_scores.get("growth_labor", 0)
        liquidity_score = layer_scores.get("liquidity_credit", 0)

        regime_key, regime_label_cn, regime_summary = self._regime(
            policy_score=policy_score,
            inflation_score=inflation_score,
            growth_score=growth_score,
            liquidity_score=liquidity_score,
            event_window_status=event_status,
        )

        return MacroOverviewResponse(
            regime_key=regime_key,
            regime_label_cn=regime_label_cn,
            regime_summary=regime_summary,
            policy_score=policy_score,
            inflation_score=inflation_score,
            growth_score=growth_score,
            liquidity_score=liquidity_score,
            operation_bias=self._operation_bias(regime_key, event_status),
            event_window_status=event_status,
            event_window_summary=event_summary,
            next_event_title=next_event_title,
            next_event_at=next_event_at,
            event_items=event_items,
            layers=layers,
        )

    def _build_indicator_read(
        self, spec: MacroIndicatorSpec, definition, observation
    ) -> MacroOverviewIndicatorRead:
        label = spec.label
        if definition and getattr(definition, "display_name", None):
            label = str(definition.display_name).upper().replace("_", " ")
        if observation is None:
            return MacroOverviewIndicatorRead(
                indicator_key=spec.indicator_key,
                label=label,
                tooltip=spec.tooltip,
                region=spec.region,
                status="pending",
                insight="待接入或暂无最新值。",
            )
        return MacroOverviewIndicatorRead(
            indicator_key=spec.indicator_key,
            label=label,
            tooltip=spec.tooltip,
            region=spec.region,
            source_provider=observation.source_provider,
            value_num=observation.value_num,
            value_text=observation.value_text,
            observation_ts=observation.observation_ts,
            signal_state=observation.signal_state,
            status="live",
            insight=self._indicator_insight(
                spec.indicator_key, observation.value_num, observation.signal_state
            ),
        )

    def _build_event_indicator_read(
        self, spec: MacroIndicatorSpec, events, now: datetime
    ) -> MacroOverviewIndicatorRead:
        event_key = self._event_key_for_indicator(spec.indicator_key)
        event = self._nearest_event(events, event_key)
        if event is None:
            return MacroOverviewIndicatorRead(
                indicator_key=spec.indicator_key,
                label=spec.label,
                tooltip=spec.tooltip,
                region=spec.region,
                status="pending",
                insight="当前还没有可用的宏观日历事件。",
            )

        scheduled_at = (
            event.scheduled_at
            if event.scheduled_at.tzinfo
            else event.scheduled_at.replace(tzinfo=UTC)
        )
        delta = scheduled_at - now
        if delta > timedelta(days=3):
            insight = f"{event.title} 已进入日历，但距离发布时间仍较远。"
        elif delta > timedelta(0):
            insight = (
                f"{event.title} 将在 {self._humanize_delta(delta)} 后发布，当前进入事件观察窗口。"
            )
        elif delta >= -timedelta(hours=6):
            insight = f"{event.title} 刚刚发布，需等待市场完成第一轮重定价。"
        else:
            insight = f"{event.title} 已发布，可结合实际值与预期差继续跟踪。"

        return MacroOverviewIndicatorRead(
            indicator_key=spec.indicator_key,
            label=spec.label,
            tooltip=spec.tooltip,
            region=spec.region,
            source_provider=event.provider_key,
            value_num=event.actual_value_num
            if event.actual_value_num is not None
            else event.consensus_value_num,
            value_text=None,
            observation_ts=scheduled_at,
            signal_state=event.status,
            status="live",
            insight=insight,
            event_title=event.title,
            event_status=event.status,
            scheduled_at=scheduled_at,
            actual_value_num=event.actual_value_num,
            consensus_value_num=event.consensus_value_num,
            previous_value_num=event.previous_value_num,
            surprise_num=event.surprise_num,
        )

    def _event_key_for_indicator(self, indicator_key: str) -> str:
        mapping = {
            "fomc_event_window": "fomc",
            "us_cpi_yoy": "us_cpi",
            "us_nfp": "us_nfp",
            "ism_mfg_pmi": "ism_mfg",
            "ism_srv_pmi": "ism_srv",
            "cn_mof_bond_issuance": "cn_mof_bond_issuance",
        }
        return mapping.get(indicator_key, indicator_key)

    def _nearest_event(self, events, event_key: str):
        matched = [item for item in events if item.event_key == event_key]
        if not matched:
            return None
        matched.sort(
            key=lambda item: abs(
                (
                    item.scheduled_at
                    if item.scheduled_at.tzinfo
                    else item.scheduled_at.replace(tzinfo=UTC)
                )
                - datetime.now(UTC)
            )
        )
        return matched[0]

    def _build_event_items(self, now: datetime, events) -> list[MacroOverviewEventRead]:
        core_keys = {"fomc", "us_cpi", "us_nfp", "ism_mfg", "ism_srv", "cn_mof_bond_issuance"}
        selected = []
        for event in events:
            if event.event_key not in core_keys:
                continue
            scheduled_at = (
                event.scheduled_at
                if event.scheduled_at.tzinfo
                else event.scheduled_at.replace(tzinfo=UTC)
            )
            if scheduled_at < now - timedelta(hours=24):
                continue
            selected.append((scheduled_at, event))
        selected.sort(key=lambda item: item[0])

        result = []
        for scheduled_at, event in selected[:6]:
            delta = scheduled_at - now
            if delta > timedelta(days=3):
                window_label = "后续事件"
                summary = "已经进入宏观日历，但距离当前观察窗口仍较远。"
            elif delta > timedelta(0):
                window_label = "即将发布"
                summary = f"距离发布还有 {self._humanize_delta(delta)}，建议预留波动缓冲。"
            elif delta >= -timedelta(hours=6):
                window_label = "刚刚发布"
                summary = "事件刚发布，优先等待市场完成第一轮定价。"
            else:
                window_label = "已发布"
                summary = "可读取实际值、预期值和 surprise，继续跟踪后续资产反应。"

            result.append(
                MacroOverviewEventRead(
                    event_id=event.event_id,
                    event_key=event.event_key,
                    title=event.title,
                    country_code=event.country_code,
                    importance=event.importance,
                    status=event.status,
                    scheduled_at=scheduled_at,
                    actual_value_num=event.actual_value_num,
                    consensus_value_num=event.consensus_value_num,
                    previous_value_num=event.previous_value_num,
                    surprise_num=event.surprise_num,
                    window_label=window_label,
                    summary=summary,
                )
            )
        return result

    def _humanize_delta(self, delta: timedelta) -> str:
        hours = int(delta.total_seconds() // 3600)
        if hours >= 24:
            days = hours // 24
            remain = hours % 24
            return f"{days} 天 {remain} 小时"
        return f"{max(hours, 0)} 小时"

    def _score_layer(self, layer_key: str, indicators: list[MacroOverviewIndicatorRead]) -> int:
        scorers = {
            "rates_policy": self._score_rates_policy,
            "inflation": self._score_inflation,
            "growth_labor": self._score_growth_labor,
            "liquidity_credit": self._score_liquidity_credit,
            "cross_asset_confirmation": self._score_cross_asset,
            "event_window": lambda _: 0,
        }
        raw_score = scorers[layer_key](indicators)
        if layer_key == "event_window":
            return max(-100, min(100, raw_score))
        live_items = [item for item in indicators if item.status == "live"]
        coverage = len(live_items) / max(len(indicators), 1)
        adjusted = raw_score * (0.45 + 0.55 * coverage)
        return max(-100, min(100, round(adjusted)))

    def _score_rates_policy(self, indicators: list[MacroOverviewIndicatorRead]) -> int:
        score = 0
        score += self._bucket_score(
            self._value(indicators, "us_dff"),
            [(3, 20), (4.5, 8), (5.5, -10), (99, -22)],
            lower_is_better=True,
        )
        score += self._bucket_score(
            self._value(indicators, "us_2y_yield"),
            [(3.5, 18), (4.5, 6), (5.2, -8), (99, -18)],
            lower_is_better=True,
        )
        score += self._bucket_score(
            self._value(indicators, "us_10y_yield"),
            [(3.8, 10), (4.4, 4), (5.0, -6), (99, -12)],
            lower_is_better=True,
        )
        spread = self._value(indicators, "us_10y_2y_spread")
        if spread is not None:
            if spread > Decimal("0.20"):
                score += 12
            elif spread > Decimal("-0.20"):
                score += 3
            elif spread > Decimal("-0.75"):
                score -= 10
            else:
                score -= 18
        return score

    def _score_inflation(self, indicators: list[MacroOverviewIndicatorRead]) -> int:
        score = 0
        score += self._bucket_score(
            self._value(indicators, "us_cpi_yoy"),
            [(2.5, 22), (3.2, 10), (4.0, -8), (99, -20)],
            lower_is_better=True,
        )
        score += self._bucket_score(
            self._value(indicators, "us_core_cpi_yoy"),
            [(2.8, 18), (3.4, 8), (4.0, -8), (99, -18)],
            lower_is_better=True,
        )
        oil = self._value(indicators, "wti_crude")
        if oil is not None:
            if oil >= Decimal("95"):
                score -= 12
            elif oil >= Decimal("85"):
                score -= 6
            elif oil >= Decimal("60"):
                score += 2
            else:
                score -= 2
        return score

    def _score_growth_labor(self, indicators: list[MacroOverviewIndicatorRead]) -> int:
        score = 0
        score += self._bucket_score(
            self._value(indicators, "us_nfp"), [(120, -10), (180, 4), (260, 10), (500, -8)]
        )
        unemployment = self._value(indicators, "unemployment_rate")
        if unemployment is not None:
            if unemployment <= Decimal("3.8"):
                score += 8
            elif unemployment <= Decimal("4.4"):
                score += 2
            else:
                score -= 12
        ism = self._value(indicators, "ism_mfg_pmi")
        if ism is not None:
            score += 8 if ism >= Decimal("50") else -8
        return score

    def _score_liquidity_credit(self, indicators: list[MacroOverviewIndicatorRead]) -> int:
        score = 0
        hy = self._value(indicators, "hy_oas")
        if hy is not None:
            if hy <= Decimal("3.5"):
                score += 18
            elif hy <= Decimal("4.8"):
                score += 4
            else:
                score -= 16
        fin = self._value(indicators, "financial_conditions")
        if fin is not None:
            if fin <= Decimal("0"):
                score += 8
            elif fin <= Decimal("1"):
                score += 2
            else:
                score -= 8
        return score

    def _score_cross_asset(self, indicators: list[MacroOverviewIndicatorRead]) -> int:
        score = 0
        dxy = self._value(indicators, "dollar_index")
        if dxy is not None:
            if dxy <= Decimal("101"):
                score += 12
            elif dxy <= Decimal("105"):
                score += 2
            else:
                score -= 10
        vix = self._value(indicators, "vix")
        if vix is not None:
            if vix <= Decimal("16"):
                score += 10
            elif vix <= Decimal("22"):
                score += 2
            else:
                score -= 12
        return score

    def _layer_summary(
        self,
        layer_key: str,
        score: int,
        indicators: list[MacroOverviewIndicatorRead],
        now: datetime,
        events,
    ) -> str:
        if layer_key == "event_window":
            status, summary, _, _ = self._event_window(now, events)
            return "未来三天暂无核心宏观事件窗口。" if status == "无风险" else summary
        if all(item.status != "live" for item in indicators):
            return "当前关键项仍有缺口，先按待接入状态观察。"
        if layer_key == "rates_policy":
            if score >= 20:
                return "政策约束边际缓和，利率层更支持风险偏好。"
            if score <= -20:
                return "政策压力仍在，利率层暂不支持过度扩张仓位。"
            return "利率层中性，等待更明确的政策与曲线方向。"
        if layer_key == "inflation":
            if score >= 20:
                return "通胀降温有利于宽松预期回归。"
            if score <= -20:
                return "通胀压力仍在，风险资产仍受估值约束。"
            return "通胀层中性，继续观察核心项与油价。"
        if layer_key == "growth_labor":
            if score >= 20:
                return "增长与就业偏韧性，风险资产有基本面支撑。"
            if score <= -20:
                return "增长层偏弱，优先防范需求回落。"
            return "增长层暂无一致方向，继续跟踪就业和 PMI。"
        if layer_key == "liquidity_credit":
            if score >= 20:
                return "流动性与信用暂未明显恶化。"
            if score <= -20:
                return "信用或流动性压力偏高，仓位宜更保守。"
            return "流动性层中性，等待信用利差或资金面确认。"
        if score >= 20:
            return "跨资产定价偏支持风险偏好。"
        if score <= -20:
            return "跨资产确认偏谨慎，风险偏好尚未真正回暖。"
        return "跨资产信号分化，先看确认。"

    def _regime(
        self,
        *,
        policy_score: int,
        inflation_score: int,
        growth_score: int,
        liquidity_score: int,
        event_window_status: str,
    ) -> tuple[str, str, str]:
        if event_window_status in {"预警中", "临近发布", "待确认"}:
            return "event_risk_hold", "观望整理", "事件窗口较近，更适合以观察和等待确认走势为主。"
        if growth_score >= 10 and inflation_score >= 10 and liquidity_score >= 5:
            return "goldilocks", "金发姑娘", "增长韧性与通胀降温共振，风险资产环境相对友好。"
        if growth_score >= 8 and inflation_score <= -8:
            return "reflation", "再通胀修复", "增长修复仍在，但通胀约束重新抬头。"
        if growth_score <= -10 and inflation_score <= -8:
            return "stagflation_risk", "滞胀风险", "增长走弱与通胀约束并存，最不利于风险资产。"
        if growth_score <= -10:
            return "growth_scare", "增长担忧", "增长层转弱，先防范风险偏好回落。"
        if policy_score <= -12 or liquidity_score <= -12:
            return "hawkish_tightening", "紧缩压制", "政策或流动性约束偏紧，仓位宜保守。"
        return "range_bound", "观望整理", "宏观分数分化较大，更适合以观察和等待确认为主。"

    def _event_window(self, now: datetime, events) -> tuple[str, str, str | None, datetime | None]:
        core_keys = {"fomc", "us_cpi", "us_nfp", "ism_mfg", "ism_srv", "cn_mof_bond_issuance"}
        candidates = []
        for event in events:
            scheduled_at = (
                event.scheduled_at
                if event.scheduled_at.tzinfo
                else event.scheduled_at.replace(tzinfo=UTC)
            )
            if event.event_key in core_keys and scheduled_at >= now - timedelta(hours=1):
                candidates.append((scheduled_at, event))
        candidates.sort(key=lambda item: item[0])
        if not candidates:
            return "无风险", "未来三天暂无核心宏观事件窗口。", None, None
        next_at, next_event = candidates[0]
        delta = next_at - now
        if timedelta(0) <= delta <= timedelta(hours=24):
            return (
                "临近发布",
                f"{next_event.title} 将在 24 小时内发布，仓位宜控制节奏。",
                next_event.title,
                next_at,
            )
        if timedelta(0) <= delta <= timedelta(days=3):
            return (
                "预警中",
                f"{next_event.title} 已进入三日预警窗口，建议预留反应空间。",
                next_event.title,
                next_at,
            )
        if -timedelta(hours=1) <= delta < timedelta(0):
            return (
                "待确认",
                f"{next_event.title} 刚发布，建议等待市场重新定价。",
                next_event.title,
                next_at,
            )
        return "无风险", "未来三天暂无核心宏观事件窗口。", next_event.title, next_at

    def _indicator_insight(
        self, indicator_key: str, value: Decimal | None, signal_state: str | None
    ) -> str:
        if value is None:
            return signal_state or "暂无最新值"
        if indicator_key == "us_dff":
            return (
                "政策利率仍高于宽松区间。"
                if value >= Decimal("4.5")
                else "政策利率边际回落，更利于风险偏好修复。"
            )
        if indicator_key == "us_2y_yield":
            return (
                "短端利率仍偏紧，市场宽松预期受限。"
                if value >= Decimal("4.5")
                else "短端利率回落，紧缩约束边际缓和。"
            )
        if indicator_key in {"us_10y_yield", "ust_10y_yield"}:
            return (
                "长端利率偏高，估值折现压力仍在。"
                if value >= Decimal("4.4")
                else "长端利率回落，对估值更友好。"
            )
        if indicator_key in {"us_cpi_yoy", "us_core_cpi_yoy"}:
            return (
                "美国通胀偏高，宽松预期受限。"
                if value >= Decimal("3.2")
                else "美国通胀降温，估值压力边际缓和。"
            )
        if indicator_key in {"cn_cpi_yoy", "cn_ppi_yoy"}:
            return (
                "中国价格读数偏弱，更偏向需求修复待确认。"
                if value <= Decimal("0.5")
                else "中国价格读数改善，内需修复更有支撑。"
            )
        if indicator_key in {"us_nfp", "ism_mfg_pmi", "ism_srv_pmi", "cn_pmi_mfg"}:
            return (
                "增长偏强，基本面仍有支撑。"
                if value >= Decimal("50")
                else "增长偏弱，需防范需求回落。"
            )
        if indicator_key == "hy_oas":
            return (
                "高收益信用利差走阔，信用压力偏高。"
                if value >= Decimal("4.8")
                else "高收益信用利差仍受控。"
            )
        if indicator_key == "financial_conditions":
            return (
                "金融条件偏紧，风险资产承压。"
                if value >= Decimal("1")
                else "金融条件尚未明显收紧。"
            )
        if indicator_key == "dollar_index":
            return (
                "美元偏强，跨资产确认更偏谨慎。"
                if value >= Decimal("105")
                else "美元压力可控，跨资产确认中性。"
            )
        if indicator_key == "vix":
            return (
                "波动率偏高，风险偏好不稳。"
                if value >= Decimal("22")
                else "波动率仍处于相对可控区间。"
            )
        if indicator_key in {"cn_usdcny", "cn_shibor_3m"}:
            return (
                "中国流动性与汇率压力偏高。"
                if value >= Decimal("4")
                else "中国流动性环境暂时平稳。"
            )
        return signal_state or "等待更多数据确认。"

    def _operation_bias(self, regime_key: str, event_window_status: str) -> str:
        if event_window_status in {"预警中", "临近发布", "待确认"}:
            return "观望"
        if regime_key in {"goldilocks", "reflation"}:
            return "做多"
        if regime_key in {"stagflation_risk", "growth_scare", "hawkish_tightening"}:
            return "减仓"
        return "观望"

    @staticmethod
    def _score_to_bias(score: int) -> str:
        if score >= 20:
            return "偏多"
        if score <= -20:
            return "偏空"
        return "中性"

    @staticmethod
    def _value(indicators: list[MacroOverviewIndicatorRead], key: str) -> Decimal | None:
        for item in indicators:
            if item.indicator_key == key:
                return item.value_num
        return None

    @staticmethod
    def _bucket_score(
        value: Decimal | None, thresholds: list[tuple[float, int]], *, lower_is_better: bool = False
    ) -> int:
        if value is None:
            return 0
        if lower_is_better:
            for limit, score in thresholds:
                if value <= Decimal(str(limit)):
                    return score
            return thresholds[-1][1]
        for limit, score in thresholds:
            if value <= Decimal(str(limit)):
                return score
        return thresholds[-1][1]
