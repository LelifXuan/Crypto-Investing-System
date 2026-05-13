from __future__ import annotations
from typing import Any

MONITORING_SOURCE_CATALOG: list[dict[str, Any]] = [
    {"key": "gateio_public_market", "name_cn": "Gate.io 公共行情", "category": "crypto_market", "requires_key": False, "enabled_default": True, "access_note": "用于 K 线、成交、部分合约行情。", "verification_required": True},
    {"key": "okx_public_market", "name_cn": "OKX 公共行情", "category": "crypto_market", "requires_key": False, "enabled_default": False, "access_note": "可作为 Gate.io 行情交叉校验与行情回源。", "verification_required": True},
    {"key": "alternative_me_fear_greed", "name_cn": "Alternative.me 恐慌贪婪指数", "category": "sentiment", "requires_key": False, "enabled_default": False, "access_note": "用于情绪拥挤度参考，不应直接作为交易信号。", "verification_required": True},
    {"key": "nbs_china", "name_cn": "国家统计局", "category": "china_macro", "requires_key": False, "enabled_default": False, "access_note": "用于 CPI、PPI、PMI、工业增加值等中国宏观数据。", "verification_required": True},
    {"key": "chinadata_live", "name_cn": "中国数据 API", "category": "china_macro", "requires_key": False, "enabled_default": False, "access_note": "可作为官方统计数据的 REST 访问入口。", "verification_required": True},
    {"key": "pbc", "name_cn": "中国人民银行", "category": "china_liquidity", "requires_key": False, "enabled_default": False, "access_note": "用于货币政策、公开市场操作、社融和流动性信息。", "verification_required": True},
    {"key": "safe", "name_cn": "国家外汇管理局", "category": "china_fx", "requires_key": False, "enabled_default": False, "access_note": "用于跨境资金、外储和外汇相关数据。", "verification_required": True},
    {"key": "shibor", "name_cn": "SHIBOR", "category": "china_rates", "requires_key": False, "enabled_default": False, "access_note": "用于人民币资金利率和流动性观察。", "verification_required": True},
    {"key": "cfets", "name_cn": "中国外汇交易中心", "category": "china_rates_fx", "requires_key": False, "enabled_default": False, "access_note": "用于汇率、利率和债券市场参考。", "verification_required": True},
    {"key": "local_csv_fallback", "name_cn": "本地 CSV 兜底数据", "category": "fallback", "requires_key": False, "enabled_default": True, "access_note": "当外部网络不可用时，允许用户导入宏观/事件/情绪数据。", "verification_required": False},
]

def list_monitoring_sources() -> list[dict[str, Any]]:
    return [dict(item) for item in MONITORING_SOURCE_CATALOG]
