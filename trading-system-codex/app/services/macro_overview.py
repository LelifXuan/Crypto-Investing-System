from __future__ import annotations



from dataclasses import dataclass

from datetime import timezone, datetime, timedelta

UTC = timezone.utc

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

            label_cn="利率/政策",
            indicators=(
                MacroIndicatorSpec(
                    "us_dff",

                    "US DFF",

                    "US Federal Funds Rate",

                    region="US",

                ),

                MacroIndicatorSpec(

                    "us_2y_yield",

                    "US 2Y YIELD",

                    "US 2-Year Treasury Yield",

                    region="US",

                ),

                MacroIndicatorSpec(

                    "us_10y_yield",

                    "US 10Y YIELD",

                    "US 10-Year Treasury Yield",

                    region="US",

                ),

                MacroIndicatorSpec(

                    "us_10y_2y_spread",

                    "US 10Y 2Y SPREAD",
                    "",
                    region="US",

                ),

                MacroIndicatorSpec(

                    "cn_omo_net",

                    "CN OMO NET", "", region="CN",

                ),

                MacroIndicatorSpec(

                    "cn_fr007", "CN FR007", "", region="CN",

                ),

            ),

        ),

        MacroLayerSpec(

            layer_key="inflation",

            label_cn="",

            indicators=(

                MacroIndicatorSpec(

                    "us_cpi_yoy",

                    "US CPI YOY", "", region="US",

                ),

                MacroIndicatorSpec(

                    "us_core_cpi_yoy",

                    "US CORE CPI YOY", "", region="US",

                ),

                MacroIndicatorSpec(

                    "breakeven_10y",

                    "US 10Y BREAKEVEN", "", region="US",

                ),

                MacroIndicatorSpec(

                    "wti_crude", "WTI CRUDE", "", region="global"

                ),

                MacroIndicatorSpec(

                    "cn_cpi_yoy", "CN CPI YOY", "", region="CN"

                ),

                MacroIndicatorSpec(

                    "cn_ppi_yoy",

                    "CN PPI YOY",

                    "",

                    region="CN",

                ),

            ),

        ),

        MacroLayerSpec(

            layer_key="growth_labor",

            label_cn="增长/就业",
            
            indicators=(
                
                MacroIndicatorSpec(
                    
                    "us_nfp", "US NFP", "", region="US"

                ),

                MacroIndicatorSpec(

                    "unemployment_rate",

                    "US UNEMPLOYMENT RATE", "", region="US",

                ),

                MacroIndicatorSpec(

                    "ism_mfg_pmi",

                    "US ISM MFG PMI",

                    "",

                    region="US",

                ),

                MacroIndicatorSpec(

                    "ism_srv_pmi", "US ISM SRV PMI", "", region="US"

                ),

                MacroIndicatorSpec(

                    "cn_pmi_mfg",

                    "CN PMI MFG",

                    "",

                    region="CN",

                ),

                MacroIndicatorSpec(

                    "cn_retail_sales_yoy",

                    "CN RETAIL SALES YOY", "", region="CN",

                ),

            ),

        ),

        MacroLayerSpec(

            layer_key="liquidity_credit",

            label_cn="/ ",

            indicators=(

                MacroIndicatorSpec(

                    "hy_oas", "HY OAS", "", region="US"

                ),

                MacroIndicatorSpec(

                    "tga", "US TGA", "", region="US"

                ),

                MacroIndicatorSpec(

                    "on_rrp", "US ON RRP", "", region="US"

                ),

                MacroIndicatorSpec(

                    "financial_conditions",

                    "US FINANCIAL CONDITIONS", "", region="US",

                ),

                MacroIndicatorSpec(

                    "cn_shibor_3m",

                    "CN SHIBOR 3M",

                    "",

                    region="CN",

                ),

                MacroIndicatorSpec(

                    "cn_10y_cgb",

                    "CN 10Y CGB", "", region="CN",

                ),

            ),

        ),

        MacroLayerSpec(

            layer_key="cross_asset_confirmation",

            label_cn="",

            indicators=(

                MacroIndicatorSpec(

                    "dollar_index",

                    "DOLLAR INDEX", "", region="global",

                ),

                MacroIndicatorSpec(

                    "gold", "GOLD", "", region="global"

                ),

                MacroIndicatorSpec("vix", "VIX", "", region="US"),

                MacroIndicatorSpec(

                    "ust_10y_yield",

                    "UST 10Y YIELD",

                    "",

                    region="US",

                ),

                MacroIndicatorSpec(

                    "cn_usdcny",

                    "USD CNY", "", region="CN",

                ),

            ),

        ),

        MacroLayerSpec(

            layer_key="event_window",

            label_cn="事件窗口",
            
            indicators=(
                
                MacroIndicatorSpec(
                    
                    "fomc_event_window",

                    "FOMC EVENT WINDOW", "", region="US",

                ),

                MacroIndicatorSpec(

                    "us_cpi_yoy",

                    "US CPI YOY", "", region="US",

                ),

                MacroIndicatorSpec(

                    "us_nfp", "US NFP", "", region="US"

                ),

                MacroIndicatorSpec(

                    "cn_mof_bond_issuance",

                    "CN MOF BOND ISSUANCE", "", region="CN",

                ),

            ),

        ),

    )


    def __init__(self, repository: MarketRepository) -> None:

        self.repository = repository



    async def build_overview(self, *, now: datetime | None = None) -> MacroOverviewResponse:

        now = now or datetime.now(timezone.utc)

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

                insight="暂无最新观测，等待数据源更新。"

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

                insight="暂无最新观测，等待数据源更新。"

            )



        scheduled_at = (

            event.scheduled_at

            if event.scheduled_at.tzinfo

            else event.scheduled_at.replace(tzinfo=UTC)

        )

        delta = scheduled_at - now

        if delta > timedelta(days=3):

            insight = f"{event.title} 检"

        elif delta > timedelta(0):

            insight = (

                f"{event.title}  {self._humanize_delta(delta)} "

            )

        elif delta >= -timedelta(hours=6):

            insight = f"{event.title} "

        else:

            insight = f"{event.title} "



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

                - datetime.now(timezone.utc)

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

                window_label = ""
                summary = "事件窗口已进入监控范围"
            elif delta > timedelta(0):

                window_label = ""

                summary = f" {self._humanize_delta(delta)}"

            elif delta >= -timedelta(hours=6):

                window_label = ""

                summary = ""

            else:

                window_label = ""

                summary = "意外变化"



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
        
        total_seconds = int(delta.total_seconds())
        
        prefix = "还有" if total_seconds >= 0 else "已过去"
        
        abs_seconds = abs(total_seconds)
        hours = abs_seconds // 3600
        
        if hours >= 24:
            
            days = hours // 24
            
            remain = hours % 24
            
            if remain > 0:
                return f"{prefix} {days} 天 {remain} 小时"
            return f"{prefix} {days} 天"
        
        return f"{prefix} {hours} 小时"



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

            return "" if status == "" else summary

        if all(item.status != "live" for item in indicators):

            return ""

        if layer_key == "rates_policy":

            if score >= 20:

                return ""

            if score <= -20:

                return ""

            return ""

        if layer_key == "inflation":

            if score >= 20:

                return ""

            if score <= -20:

                return ""

            return ""

        if layer_key == "growth_labor":

            if score >= 20:

                return "风"

            if score <= -20:

                return ""

            return "PMI"

        if layer_key == "liquidity_credit":

            if score >= 20:

                return ""

            if score <= -20:

                return ""

            return ""

        if score >= 20:

            return ""

        if score <= -20:

            return ""

        return ""



    def _regime(

        self,

        *,

        policy_score: int,

        inflation_score: int,

        growth_score: int,

        liquidity_score: int,

        event_window_status: str,

    ) -> tuple[str, str, str]:

        if event_window_status in {"blocked", "risk_off"}:

            return "event_risk_hold", "risk_off", "risk_off"

        if growth_score >= 10 and inflation_score >= 10 and liquidity_score >= 5:

            return "goldilocks", "", ""

        if growth_score >= 8 and inflation_score <= -8:

            return "reflation", "", ""

        if growth_score <= -10 and inflation_score <= -8:

            return "stagflation_risk", "", ""

        if growth_score <= -10:

            return "growth_scare", "", "检"

        if policy_score <= -12 or liquidity_score <= -12:

            return "hawkish_tightening", "", ""

        return "range_bound", "", ""



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

            return "", "", None, None

        next_at, next_event = candidates[0]

        delta = next_at - now

        if timedelta(0) <= delta <= timedelta(hours=24):

            return (

                "",

                f"{next_event.title}",

                next_event.title,

                next_at,

            )

        if timedelta(0) <= delta <= timedelta(days=3):

            return (

                "",

                f"{next_event.title}",

                next_event.title,

                next_at,

            )

        if -timedelta(hours=1) <= delta < timedelta(0):

            return (

                "",

                f"{next_event.title}",

                next_event.title,

                next_at,

            )

        return "distant", f"下一个宏观事件：{next_event.title}，约 {self._humanize_delta(delta)}后", next_event.title, next_at



    def _indicator_insight(

        self, indicator_key: str, value: Decimal | None, signal_state: str | None

    ) -> str:

        if value is None:

            return signal_state or ""

        if indicator_key == "us_dff":

            return (

                ""

                if value >= Decimal("4.5")

                else ""

            )

        if indicator_key == "us_2y_yield":

            return (

                ""

                if value >= Decimal("4.5")

                else ""

            )

        if indicator_key in {"us_10y_yield", "ust_10y_yield"}:

            return (

                ""

                if value >= Decimal("4.4")

                else ""

            )

        if indicator_key in {"us_cpi_yoy", "us_core_cpi_yoy"}:

            return (

                ""

                if value >= Decimal("3.2")

                else ""

            )

        if indicator_key in {"cn_cpi_yoy", "cn_ppi_yoy"}:

            return (

                ""

                if value <= Decimal("0.5")

                else ""

            )

        if indicator_key in {"us_nfp", "ism_mfg_pmi", "ism_srv_pmi", "cn_pmi_mfg"}:

            return (

                ""

                if value >= Decimal("50")

                else ""

            )

        if indicator_key == "hy_oas":

            return (

                ""

                if value >= Decimal("4.8")

                else ""

            )

        if indicator_key == "financial_conditions":

            return (

                "风"

                if value >= Decimal("1")

                else ""

            )

        if indicator_key == "dollar_index":

            return (

                ""

                if value >= Decimal("105")

                else ""

            )

        if indicator_key == "vix":

            return (

                ""

                if value >= Decimal("22")

                else ""

            )

        if indicator_key in {"cn_usdcny", "cn_shibor_3m"}:

            return (

                ""

                if value >= Decimal("4")

                else ""

            )

        return signal_state or ""



    def _operation_bias(self, regime_key: str, event_window_status: str) -> str:

        if event_window_status in {", "", "}:

            return ""

        if regime_key in {"goldilocks", "reflation"}:

            return ""

        if regime_key in {"stagflation_risk", "growth_scare", "hawkish_tightening"}:

            return ""

        return ""



    @staticmethod

    def _score_to_bias(score: int) -> str:

        if score >= 20:

            return ""

        if score <= -20:

            return ""

        return ""



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
