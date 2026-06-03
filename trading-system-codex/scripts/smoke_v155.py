"""V1.5.5 smoke test for monitoring decision_brief pipeline.

Run with: python scripts/smoke_v155.py
Saves JSON output to runtime_dev/v155_smoke.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.services.terminal_summary_engine import TerminalSummaryEngine


def main() -> None:
    engine = TerminalSummaryEngine()

    # ⑥ weak_bearish: monitoring now agrees with structure page
    result = engine.build(
        structure={
            "regime": "trending",
            "overall_bias": "weak_bearish",
            "score": 45,
            "confidence": 0.6,
            "suggested_action": "偏空震荡",
            "risk": "跌破前低",
            "source": "structure_bundle",
        },
        alerts_bundle={
            "chip_structure": {
                "direction": "bearish",
                "invalidation_conditions": [
                    "价格重新回到关键区间内部。"
                ],
            }
        },
        strategy_bundle={"decision": {"strategy_state": "OBSERVE"}},
        timeframe_snapshots={
            "1w": {"bias": "bullish", "score": 60},
            "1d": {"bias": "bearish", "score": 35},
            "4h": {"bias": "bearish", "score": 28},
        },
    )

    output = {
        "regime": result["regime"],
        "bias": result["bias"],
        "confidence": result["confidence"],
        "headline": result["headline"],
        "structure_module": {
            "state": result["module_scores"]["structure"]["state"],
            "impact": result["module_scores"]["structure"]["impact"],
            "score": result["module_scores"]["structure"]["score"],
        },
        "decision_brief_rows": [
            {
                "key": row["key"],
                "title": row["title"],
                "summary": row["summary"],
                "bullets": row.get("bullets", []),
                "source_refs_meta": row.get("source_refs_meta", []),
            }
            for row in result["decision_brief"]["rows"]
        ],
    }

    out_path = Path("runtime_dev/v155_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
