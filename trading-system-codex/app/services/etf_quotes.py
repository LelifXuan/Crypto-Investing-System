from __future__ import annotations

from app.services.ashare_etf_quotes import (
    AShareETFQuote,
    AShareETFQuoteService,
    EastmoneyDirectETFClient,
)

# Compatibility service module for the V1.31 ETF contract. The implementation uses httpx
# inside EastmoneyDirectETFClient and the configured ETF universe below:
ETF_UNIVERSE_LABELS = {
    "159201": "现金流ETF",
    "563010": "电信ETF",
    "512660": "军工ETF",
    "516950": "基建ETF",
    "512400": "有色金属ETF",
    "159930": "能源ETF",
    "561560": "电力ETF",
}

__all__ = ["AShareETFQuote", "AShareETFQuoteService", "EastmoneyDirectETFClient"]
