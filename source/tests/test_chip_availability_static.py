"""B1+B2 chip_structure availability 静态守卫。

锁定:
  1. ChipStructureRead schema 必含 availability_state / availability_reason 字段
  2. risk_score / risk_label 必须是 Optional (可空), 不再硬编码 100/extreme
  3. alerts.js chipRiskMarkup 必含 availability_state 守卫 (不能删除回归)
  4. alerts.js chipStateMarkup 必须含 unavailable / stale_lkg 枚举值
  5. final_decision.py _conflicts 必须不含 risk_score_extreme 冲突分支
  6. market_context.py chip_structure _dependency_meta 必含 availability 分支
  7. chip_structure.py _missing_payload 必含 availability_state='missing'
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "app/schemas/market.py"
CHIP_SVC = ROOT / "app/services/chip_structure.py"
FINAL_DEC = ROOT / "app/services/final_decision.py"
MARKET_CTX = ROOT / "app/services/market_context.py"
ALERTS_JS = ROOT / "app/static/pages/alerts.js"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_schema_has_availability_state():
    """ChipStructureRead 必含 availability_state + availability_reason 字段。"""
    src = _read(SCHEMA)
    # 找 ChipStructureRead 类
    pattern = r"class ChipStructureRead\(BaseModel\):.*?(?=\n\nclass |\nclass |\Z)"
    cls_match = re.search(pattern, src, re.DOTALL)
    assert cls_match, "ChipStructureRead 类未找到"
    cls_body = cls_match.group(0)
    assert "availability_state" in cls_body, (
        "ChipStructureRead 缺少 availability_state 字段"
    )
    assert "availability_reason" in cls_body, (
        "ChipStructureRead 缺少 availability_reason 字段"
    )


def test_schema_risk_score_is_optional():
    """risk_score / risk_label 必须是 Optional, 默认值不再是 100/extreme。"""
    src = _read(SCHEMA)
    cls_match = re.search(
        r"class ChipStructureRead\(BaseModel\):.*?(?=\n\nclass |\nclass |\Z)", src, re.DOTALL
    )
    cls_body = cls_match.group(0)
    # risk_score / risk_label 必须允许 None
    rs = re.search(r"risk_score:\s*([^=\n]+)", cls_body)
    rl = re.search(r"risk_label:\s*([^=\n]+)", cls_body)
    assert rs, "risk_score 字段未找到"
    assert rl, "risk_label 字段未找到"
    assert "None" in rs.group(1) or "Optional" in rs.group(1) or "float | None" in rs.group(1), (
        f"risk_score 必须允许 None, 实际类型注解 {rs.group(1).strip()!r}"
    )
    assert "None" in rl.group(1) or "Optional" in rl.group(1) or "str | None" in rl.group(1), (
        f"risk_label 必须允许 None, 实际类型注解 {rl.group(1).strip()!r}"
    )


def test_alerts_chip_risk_markup_has_availability_guard():
    """alerts.js chipRiskMarkup 必含 availability 守卫, 防止 missing 时渲染「风险极高」。"""
    src = _read(ALERTS_JS)
    # 用 brace matching 抓完整函数体
    sig = re.search(r"function chipRiskMarkup\(", src)
    if not sig:
        raise AssertionError("chipRiskMarkup 函数未找到")
    i = sig.end()
    while i < len(src) and src[i] != "{":
        i += 1
    depth = 1
    i += 1
    in_str = None
    while i < len(src) and depth > 0:
        c = src[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == in_str:
                in_str = None
        elif c in ('"', "'", "`"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    body = src[sig.start():i]
    # 必须接受 availability 参数
    has_availability = re.search(
        r"chipRiskMarkup\(\s*\w+\s*,\s*availability", body
    ) or "availability" in body[:200]
    assert has_availability, "chipRiskMarkup 函数签名必须含 availability 参数"
    # 必须引用 chipAvailabilityGuards
    assert "chipAvailabilityGuards" in body, (
        "chipRiskMarkup 内部必须调用 chipAvailabilityGuards 守卫"
    )
    # 必须有「数据不可用」chip 渲染
    assert "数据不可用" in body, (
        "chipRiskMarkup 必须渲染「数据不可用」chip 用于 availability 守卫分支"
    )


def test_alerts_chip_state_markup_has_unavailable_and_stale_lkg():
    """chipStateMarkup 必含 unavailable 和 stale_lkg 映射。"""
    src = _read(ALERTS_JS)
    # 找 chipStateMarkup 的 mapping 字典 (在 function 体里)
    sig = re.search(r"function chipStateMarkup\(", src)
    i = sig.end()
    while i < len(src) and src[i] != "{":
        i += 1
    depth = 1
    i += 1
    in_str = None
    while i < len(src) and depth > 0:
        c = src[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == in_str:
                in_str = None
        elif c in ('"', "'", "`"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    body = src[sig.start():i]
    assert "unavailable" in body, "chipStateMarkup 缺少 unavailable 枚举"
    assert "stale_lkg" in body, "chipStateMarkup 缺少 stale_lkg 枚举"


def test_final_decision_no_risk_score_extreme_conflict():
    """final_decision._conflicts 不能再产生 risk_score_extreme 冲突。

    注释里提及 risk_score_extreme 是允许的(作为历史原因说明),
    但函数体内不能再有 'conflicts.append("risk_score_extreme")' 或同义触发代码。
    """
    src = _read(FINAL_DEC)
    lines = src.split("\n")
    start_line = None
    for idx, line in enumerate(lines, start=1):
        if re.match(r"^    def _conflicts\(", line):
            start_line = idx
            break
    assert start_line is not None, "_conflicts 函数未找到"
    end_line = len(lines)
    for idx in range(start_line + 1, len(lines) + 1):
        if idx > len(lines):
            break
        line = lines[idx - 1] if idx <= len(lines) else ""
        if re.match(r"^    def _final_action\(", line) or re.match(r"^    @staticmethod", line):
            end_line = idx - 1
            break
    body = "\n".join(lines[start_line - 1:end_line])
    # 删掉所有 # 开头的注释行后, 再断言不能出现 risk_score_extreme 的 append
    code_only = "\n".join(
        line for line in body.split("\n") if not line.strip().startswith("#")
    )
    assert 'conflicts.append("risk_score_extreme"' not in code_only, (
        "_conflicts 函数体内仍含 conflicts.append('risk_score_extreme'), 与 B1+B2 修复冲突"
    )
    # 同时, 不能再有依赖 risk_score >= 80 触发冲突的代码
    assert "risk_score" not in code_only or ">= 80" not in code_only, (
        "_conflicts 不再以 risk_score >= 80 作为冲突触发条件"
    )


def test_market_context_chip_dependency_uses_availability():
    """market_context._dependency_meta 调用 chip_structure 必须按 availability 分支。"""
    src = _read(MARKET_CTX)
    # 找包含 chip_structure 的 try/except 块
    # 简单断言: 必须出现 chip_availability 或 availability_state 关键字
    assert "chip_availability" in src or "availability_state" in src, (
        "market_context.py 缺少按 availability_state 分支处理 chip_structure 的代码"
    )


def test_chip_structure_missing_payload_sets_availability():
    """chip_structure._missing_payload 必须显式设 availability_state='missing'。"""
    src = _read(CHIP_SVC)
    # 找 _missing_payload 函数体
    sig = re.search(r"def _missing_payload\(", src)
    if not sig:
        raise AssertionError("_missing_payload 未找到")
    i = sig.end()
    while i < len(src) and src[i] != ":":
        i += 1
    while i < len(src) and src[i] != "\n":
        i += 1
    next_def = re.search(r"\n    def |\n    async def |\nclass ", src[i:])
    end = i + (next_def.start() if next_def else 2000)
    body = src[i:end]
    assert '"availability_state"' in body and '"missing"' in body, (
        "_missing_payload 必须显式设 availability_state='missing'"
    )
    # risk_score 必须为 None (不能再是 100)
    assert "None" in body and "risk_score" in body, (
        "_missing_payload risk_score 必须为 None, 不再误编码 100"
    )
