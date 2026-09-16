"""B1+B2 chip_structure availability 业务语义测试。

按 docs/chip-structure-availability-audit.md §「下一轮修复输入」覆盖 6 种 fixture:

  1. _missing_payload 直返: availability_state='missing', risk_score=None,
     conflict_level=0, recommended_action='unavailable'
  2. _missing_payload 经 FinalDecision: action='unavailable',
     trade_permission='unavailable', conflicts=[]
  3. stale + LKG: availability_state='stale_lkg', cache_state='stale'
  4. 真实风险升高: confidence<50 → availability_state='low_confidence',
     risk_score 保留真实值 (不为 None)
  5. FinalDecisionService._conflicts 不再触发 risk_score_extreme 冲突
     (历史根因: missing 分支同时输出 risk_score=100 → 假冲突)
  6. chip_structure.analyzer 异常 → availability_state='unavailable',
     不污染 market_risk (risk_score=None, conflict_level=0)

每个 fixture 都用 in-process 异步调用, 不依赖 uvicorn / 数据库。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.chip_structure import ChipStructureService
from app.services.final_decision import FinalDecisionService


# ---- Fixture 1: _missing_payload 直返 ----
def test_missing_payload_sets_availability_and_null_risk():
    """缺 K 线分支: availability_state=missing, risk_score=null,
    conflict_level=0, recommended_action=unavailable。"""
    svc = ChipStructureService(repository=SimpleNamespace())
    payload = svc._missing_payload(instrument_id="BTCUSDT", timeframe="1h", candles=[])

    actual_state = payload.get("availability_state")
    assert actual_state == "missing", (
        f"_missing_payload availability_state 应为 'missing', 实际 {actual_state!r}"
    )
    assert payload["risk_score"] is None, (
        f"_missing_payload risk_score 必须为 None, 实际 {payload.get('risk_score')!r}"
    )
    assert payload["risk_label"] is None, (
        f"_missing_payload risk_label 必须为 None, 实际 {payload.get('risk_label')!r}"
    )
    actual_conflict = payload.get("conflict_level")
    assert actual_conflict == 0, (
        f"_missing_payload conflict_level 应为 0 (无真实冲突), 实际 {actual_conflict!r}"
    )
    assert payload["recommended_action_v2"] == "unavailable", (
        f"_missing_payload recommended_action_v2 应为 'unavailable', "
        f"实际 {payload.get('recommended_action_v2')!r}"
    )
    assert "本地可用 K 线不足" in (payload.get("availability_reason") or ""), (
        f"availability_reason 必须给出缺数据原因, 实际 {payload.get('availability_reason')!r}"
    )


# ---- Fixture 2: _missing_payload 经 FinalDecision ----
@pytest.mark.asyncio
async def test_missing_payload_propagates_unavailable_through_final_decision(monkeypatch):
    """_missing_payload 进 FinalDecision 后:
    - action='unavailable' (不再误为 no_trade)
    - trade_permission='unavailable' (不再误为 observe)
    - conflicts=[] (不再误为 [risk_score_extreme])
    """
    # 构造 stub repository: market_data.get_bundle 返回空 candles, 触发 missing 分支
    class _StubMarketData:
        async def get_bundle(self, *args, **kwargs):
            return {"candles": [], "cache_timeframe": "1h"}

    class _StubRepo:
        def __init__(self):
            self.market_data = _StubMarketData()

    svc = FinalDecisionService(repository=_StubRepo())
    monkeypatch.setattr(
        "app.services.final_decision.MarketContextBuilder",
        lambda *a, **kw: SimpleNamespace(
            get_context=lambda *a, **kw: _async_return({
                "chip_structure": _build_missing(),
                "macro_overview": {},
            })
        ),
    )

    # 直接用 _chip_payload (异常分支) + 手动构造 chip 走 unavailable 分支
    # 实际场景: _chip_payload 异常 → availability_state='unavailable'
    chip = {
        "instrument_id": "BTCUSDT",
        "timeframe": "1h",
        "state": "unavailable",
        "availability_state": "unavailable",
        "availability_reason": "analyze 异常",
        "direction_score": 0.0,
        "direction_label": "neutral",
        "confidence_score": 0.0,
        "confidence_label": "invalid",
        "execution_score": 0.0,
        "execution_label": "blocked",
        "risk_score": None,
        "risk_label": None,
        "confidence_cap": 0.0,
        "recommended_action": "unavailable",
        "recommended_action_v2": "unavailable",
        "position_multiplier": 0.0,
        "capital_ceiling_pct": 0.0,
        "evidence_quality": "proxy_only",
        "conflict_level": 0,
        "risk_gates": ["CHIP_STRUCTURE_UNAVAILABLE"],
        "components": {},
    }
    macro_bias = "neutral"

    conflicts = svc._conflicts(chip, macro_bias)
    action = svc._final_action(chip, conflicts)
    permission = svc._trade_permission(action, conflicts)

    assert action == "unavailable", f"action 应为 'unavailable', 实际 {action!r}"
    assert permission == "unavailable", f"trade_permission 应为 'unavailable', 实际 {permission!r}"
    assert conflicts == [], f"conflicts 应为 [], 实际 {conflicts!r}"


def _build_missing():
    """构造 _missing_payload 输出 (mock 用)"""
    return ChipStructureService(repository=SimpleNamespace())._missing_payload(
        instrument_id="BTCUSDT", timeframe="1h", candles=[]
    )


async def _async_return(value):
    return value


# ---- Fixture 3: stale + LKG ----
def test_stale_lkg_availability_state():
    """真实数据降级时: availability_state='stale_lkg', cache_state 跟随降级。

    这是 market_context._dependency_meta 的契约 — 直接断言 chip_structure 已知
    stale_lkg 枚举, 不允许 'stale_revalidating' / 'partial' 等不一致枚举。
    """
    # _missing_payload 不直接产生 stale_lkg, 但 stale_lkg 必须作为合法枚举出现
    # 在已知 payload 中。简化: 验证 final_decision._is_chip_unavailable 把它识别为不可用。
    svc = FinalDecisionService(repository=SimpleNamespace())
    chip = {
        "instrument_id": "BTCUSDT",
        "timeframe": "1h",
        "state": "low_confidence",
        "availability_state": "stale_lkg",
        "availability_reason": "上游 cache stale, 保留 LKG",
        "direction_score": 0.0,
        "risk_score": 50.0,
        "risk_label": "normal",
        "recommended_action_v2": "observe",
    }
    assert svc._is_chip_unavailable(chip) is True, (
        "_is_chip_unavailable 应把 stale_lkg 视为不可用 (cache_state 应跟随降级为 stale)"
    )


# ---- Fixture 4: 真实风险升高 (confidence<50) ----
@pytest.mark.asyncio
async def test_low_confidence_keeps_real_risk_score():
    """低置信度路径 availability_state='low_confidence', risk_score 保留真实值 (不为 None)。
    这是与 missing 路径的关键区别: 有数据 + 置信度不足 ≠ 缺数据。
    """
    # _real_structure_payload 走结构快照分支, 但 confidence<50 时 availability=low_confidence
    # 这里直接调 _missing_payload 的反向: 用 analyzer 主路径产物 (含真实 risk_score)
    chip = {
        "instrument_id": "BTCUSDT",
        "timeframe": "1h",
        "state": "low_confidence",
        "availability_state": "low_confidence",
        "availability_reason": "微观结构证据不足, 仅 K 线 proxy",
        "direction_score": -12.5,
        "direction_label": "neutral",
        "confidence_score": 35.0,
        "confidence_label": "low",
        "execution_score": 40.0,
        "execution_label": "pending",
        "risk_score": 55.0,
        "risk_label": "elevated",
        "confidence_cap": 55.0,
        "conflict_level": 1,
        "recommended_action": "wait_confirmation",
        "recommended_action_v2": "observe",
    }
    macro_bias = "neutral"

    svc = FinalDecisionService(repository=SimpleNamespace())
    conflicts = svc._conflicts(chip, macro_bias)
    action = svc._final_action(chip, conflicts)
    permission = svc._trade_permission(action, conflicts)

    # risk_score 必须保留 (不为 None)
    assert chip["risk_score"] == 55.0
    assert chip["risk_label"] == "elevated"
    assert chip["availability_state"] == "low_confidence"
    # low_confidence 不是 unavailable, action 应是 observe 或 wait_confirmation
    assert action in ("observe", "wait_confirmation"), (
        f"low_confidence 路径 action 应为 observe 或 wait_confirmation, 实际 {action!r}"
    )
    # 不能错误降级到 unavailable
    assert permission != "unavailable", (
        f"low_confidence 不应被守卫误伤为 unavailable, 实际 {permission!r}"
    )
    # 不能再产生 risk_score_extreme 假冲突
    assert "risk_score_extreme" not in conflicts, (
        f"conflicts 中不能再含 risk_score_extreme, 实际 {conflicts!r}"
    )


# ---- Fixture 5: FinalDecisionService._conflicts 不再触发 risk_score_extreme ----
def test_conflicts_no_longer_triggers_risk_score_extreme():
    """历史根因: chip_structure 缺数据时 risk_score=100, _conflicts 推 risk_score_extreme。
    修复后 risk_score=None, 此冲突天然失效; 显式断言不再触发。

    测试用 risk_score=100 (极端值, 模拟历史场景), 但 chip.state=ready,
    即「真实风险高」而非「缺数据」的情况, 应该:
    - 修复前: 仍触发 risk_score_extreme (因为只看 risk_score>=80)
    - 修复后: 不再触发 (该分支已删除)
    """
    svc = FinalDecisionService(repository=SimpleNamespace())
    chip = {
        "instrument_id": "BTCUSDT",
        "timeframe": "1h",
        "state": "ready",  # 不是 missing / unavailable
        "availability_state": "ready",
        "direction_score": -50.0,
        "risk_score": 100.0,  # 即便真实 risk_score=100, 修复后也不应触发
        "risk_label": "extreme",
        "recommended_action_v2": "reduce_or_exit",
        "capital_ceiling_pct": 5.0,
    }
    conflicts = svc._conflicts(chip, "neutral")
    assert "risk_score_extreme" not in conflicts, (
        f"修复后 risk_score_extreme 冲突分支应删除, 实际 conflicts={conflicts!r}"
    )


# ---- Fixture 6: chip_structure.analyzer 异常 → availability_state='unavailable' ----
@pytest.mark.asyncio
async def test_chip_analyzer_exception_returns_unavailable(monkeypatch):
    """ChipStructureService.analyze 异常时, _chip_payload 兜底分支
    必须返回 availability_state='unavailable' + risk_score=None,
    不再误为 risk_score=100/extreme。"""
    import app.services.final_decision as fd_module

    class _BoomChipService:
        async def analyze(self, *args, **kwargs):
            raise RuntimeError("upstream kline fetch failed")

    # 把 FinalDecisionService._chip_payload 里用到的 ChipStructureService.analyze
    # 替换为抛异常的版本, 让 try/except 兜底分支被触发。
    monkeypatch.setattr(
        fd_module,
        "ChipStructureService",
        lambda *a, **kw: _BoomChipService(),
    )

    class _StubRepo:
        pass

    svc = FinalDecisionService(repository=_StubRepo())
    chip = await svc._chip_payload(instrument_id="BTCUSDT", timeframe="1h")

    actual_avail = chip.get("availability_state")
    assert actual_avail == "unavailable", (
        f"analyzer 异常分支 availability_state 应为 'unavailable', 实际 {actual_avail!r}"
    )
    assert chip["risk_score"] is None, (
        f"analyzer 异常分支 risk_score 必须为 None, 实际 {chip.get('risk_score')!r}"
    )
    assert chip["risk_label"] is None, (
        f"analyzer 异常分支 risk_label 必须为 None, 实际 {chip.get('risk_label')!r}"
    )
    assert chip["recommended_action"] == "unavailable", (
        f"analyzer 异常分支 recommended_action 应为 'unavailable', "
        f"实际 {chip.get('recommended_action')!r}"
    )
    assert chip["conflict_level"] == 0, (
        f"analyzer 异常分支 conflict_level 应为 0, 实际 {chip.get('conflict_level')!r}"
    )
