"""Published scan identity and expiry use the same cache contract as the API."""

from datetime import datetime

from app.services.strategy_unified.opportunity_scanner import (
    OpportunityScanner,
    _extract_scan_item,
)


def test_scan_result_expiry_is_future_and_utc():
    result = OpportunityScanner._result(
        [], ["btc-usdt-perp"], ("4h",), source="published_snapshots"
    )
    scanned = datetime.fromisoformat(result.scanned_at)
    expiry = datetime.fromisoformat(result.cache_meta["fresh_until"])
    assert scanned.tzinfo is not None
    assert expiry.tzinfo == scanned.tzinfo
    assert expiry > scanned


def test_scan_cell_records_exact_published_unified_identity():
    payload = {"snapshot_key": "btc-usdt-perp:published", "status": "ready"}
    item = _extract_scan_item(payload, "btc-usdt-perp", "BTC", "4h")
    assert item.source_snapshot_key == payload["snapshot_key"]
    assert not item.qualified
