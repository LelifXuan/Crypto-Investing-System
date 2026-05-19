#!/usr/bin/env python3
"""Cross-check audit findings and track remaining tasks across rounds."""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK_PATTERNS = {
    "overlay_extrapolation": {
        "file": "app/static/pages/structure.js",
        "check": "shouldExtendToLatest",
        "desc": "Safe overlay extrapolation with role-based opt-in"
    },
    "translation_status_endpoint": {
        "file": "app/api/v1/endpoints/market_events.py",
        "check": "translations/status",
        "desc": "Translation status endpoint exists"
    },
    "translation_db_stats": {
        "file": "app/api/v1/endpoints/market_events.py",
        "check": "MarketEventTranslationMap",
        "desc": "Translation status connected to real DB"
    },
    "viewport_hidden_filter": {
        "file": "app/static/pages/structure.js",
        "check": "visibleGeometry",
        "desc": "Viewport focus excludes hidden geometry"
    },
    "cache_first_get": {
        "file": "app/services/structure/snapshot_service.py",
        "check": "cache_state",
        "desc": "Cache-first GET pattern in structure service"
    },
    "macro_total_score": {
        "file": "app/schemas/market.py",
        "check": "total_score",
        "desc": "Macro total/composite score in schema"
    },
    "swing_pivots_param": {
        "file": "app/services/structure/swing.py",
        "check": "pivots:",
        "desc": "SwingScorer accepts optional shared pivots"
    },
    "strategy_tp_wording": {
        "file": "app/services/strategy_signal/strategy_generator.py",
        "check": "\u6b62\u76c8\u4f4d",
        "desc": "Strategy take-profit wording updated"
    },
    "monitoring_normal_label": {
        "file": "app/static/pages/monitoring.js",
        "check": "\u4e2d\u6027",
        "desc": "Normal -> neutral label fix"
    },
}

def main():
    results = []
    for key, item in CHECK_PATTERNS.items():
        path = REPO / item["file"]
        if not path.exists():
            results.append({"task": key, "status": "MISSING_FILE", "desc": item["desc"]})
            continue
        try:
            content = path.read_text(encoding="utf-8")
            if item["check"] in content:
                results.append({"task": key, "status": "PASS", "desc": item["desc"]})
            else:
                results.append({"task": key, "status": "FAIL", "desc": item["desc"]})
        except Exception:
            results.append({"task": key, "status": "FAIL", "desc": item["desc"]})

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] != "PASS")
    print(f"Cross-check: {passed}/{len(results)} passed, {failed} remaining")
    for r in results:
        icon = "PASS" if r["status"] == "PASS" else "FAIL" if r["status"] == "FAIL" else "MISS"
        print(f"  [{icon}] {r['task']}: {r['desc']}")

    if failed:
        print(f"\n{failed} task(s) still need attention. Run the build plan for remaining items.")
        return 1
    else:
        print("\nAll checks passed!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
