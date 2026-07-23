from __future__ import annotations


def data_status_label(status: str) -> str:
    labels = {
        "ok": "正常",
        "missing": "缺失",
        "stale": "过期",
        "cached": "缓存",
        "pending_release": "等待发布",
        "source_error": "数据源失败",
        "auth_missing": "缺少密钥",
        "rate_limited": "频率限制",
        "parser_error": "解析失败",
        "disabled": "未启用",
    }
    return labels.get(status, status)


def data_status_css(status: str) -> str:
    css_map = {
        "ok": "chip-favorable",
        "cached": "chip-neutral",
        "stale": "chip-warning",
        "pending_release": "chip-neutral",
        "missing": "chip-danger",
        "source_error": "chip-danger",
        "auth_missing": "chip-danger",
        "rate_limited": "chip-warning",
        "parser_error": "chip-danger",
        "disabled": "chip-neutral",
    }
    return css_map.get(status, "chip-neutral")


def confidence_label(confidence: str) -> str:
    labels = {"high": "高", "medium": "中", "low": "低", "insufficient": "数据不足"}
    return labels.get(confidence, confidence)


def confidence_css(confidence: str) -> str:
    css_map = {
        "high": "impact-favorable",
        "medium": "impact-neutral",
        "low": "impact-warning",
        "insufficient": "impact-danger",
    }
    return css_map.get(confidence, "impact-neutral")


def frequency_label(freq: str) -> str:
    labels = {
        "intraday": "日内",
        "daily": "每日",
        "weekly": "每周",
        "monthly": "每月",
        "quarterly": "每季",
        "fomc": "FOMC",
        "irregular": "不定期",
    }
    return labels.get(freq, freq)


def default_module_summary(module: dict) -> str:
    effective = module.get("effective_count", 0)
    total = module.get("total_count", 0)
    missing = module.get("missing_count", 0)
    stale = module.get("stale_count", 0)
    if total == 0:
        return "当前模块没有配置指标，未参与评分。"
    if effective == 0:
        reasons = []
        if missing:
            reasons.append(f"{missing} 项指标缺失")
        if stale:
            reasons.append(f"{stale} 项数据过期")
        reason_text = "、".join(reasons) if reasons else "暂无可评分指标"
        return f"系统判定：{reason_text}，该模块暂不参与评分。"
    if effective < total:
        return f"有效指标 {effective}/{total}，模块参与评分但数据完整度受限。"
    return f"全部 {total} 项指标数据正常，模块正常参与评分。"
