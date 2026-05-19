from __future__ import annotations

from app.api.v1.endpoints.ashare_etf import etf_router as router

# Compatibility endpoint module for the V1.31 acceptance contract.
# The real router is mounted at /etf and exposes /catalog, /quotes, and /quotes/refresh.

__all__ = ["router"]
