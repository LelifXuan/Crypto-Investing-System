"""Acceptance tests for T02: next_trigger preserves str / list / dict.

The audit found that ``_decision_as_mapping(decision.get('next_trigger'))``
silently dropped string and list triggers because the formatter only
understood dict shapes. The strategy generator can legitimately emit any
of: a human string (the dominant case), a list of trigger conditions, or
a structured dict (legacy). All three must surface in the trading row.
"""

from __future__ import annotations

from app.services.terminal_summary_engine import _decision_format_trigger


def test_trigger_string_is_preserved() -> None:
    text = "等待 4H 周期出现明确触发信号后重新评估入场。"
    rendered = _decision_format_trigger(text)
    assert "下一触发器" in rendered
    assert text in rendered


def test_trigger_empty_string_returns_empty() -> None:
    assert _decision_format_trigger("") == ""


def test_trigger_none_returns_empty() -> None:
    assert _decision_format_trigger(None) == ""


def test_trigger_empty_list_returns_empty() -> None:
    assert _decision_format_trigger([]) == ""


def test_trigger_empty_dict_returns_empty() -> None:
    assert _decision_format_trigger({}) == ""


def test_trigger_list_of_strings_is_joined() -> None:
    rendered = _decision_format_trigger(
        [
            "等待 4H 收盘站稳结构 invalidation 上方",
            "成交量同步放大",
            "CVD 转正",
        ]
    )
    assert "下一触发器" in rendered
    assert "等待 4H 收盘站稳结构 invalidation 上方" in rendered
    assert "成交量同步放大" in rendered
    assert "CVD 转正" in rendered
    # Joined with semicolons, not commas
    assert "；" in rendered
    assert "，" not in rendered.split("下一触发器：")[1]


def test_trigger_list_filters_empty_items() -> None:
    rendered = _decision_format_trigger(["条件一", "", None, "条件二"])
    assert "条件一" in rendered
    assert "条件二" in rendered
    # Should not have doubled separators
    assert "；；" not in rendered
    assert "；None" not in rendered


def test_trigger_dict_uses_legacy_formatter() -> None:
    rendered = _decision_format_trigger(
        {
            "label": "4H 突破",
            "price": 82000,
            "timeframe": "4h",
        }
    )
    assert "下一触发器" in rendered
    assert "4H 突破" in rendered
    assert "4h" in rendered
    assert "82000" in rendered


def test_trigger_dict_with_missing_fields_renders_partial() -> None:
    rendered = _decision_format_trigger({"label": "突破"})
    assert "下一触发器" in rendered
    assert "突破" in rendered


def test_trigger_tuple_is_treated_like_list() -> None:
    rendered = _decision_format_trigger(("条件一", "条件二"))
    assert "条件一" in rendered
    assert "条件二" in rendered
