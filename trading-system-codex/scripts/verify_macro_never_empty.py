from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.macro.fallback_resolver import fallback_for_indicator

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = [
        ROOT / "app" / "monitoring" / "configs" / "portable_macro_never_empty_policy.v2.json",
        ROOT / "app" / "assets" / "seed_cache" / "macro_observations_seed.json",
        ROOT / "app" / "assets" / "seed_cache" / "macro_websearch_seed.json",
        ROOT / "app" / "assets" / "seed_cache" / "seed_manifest.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        print(json.dumps({"ok": False, "missing": missing}, ensure_ascii=False, indent=2))
        return 1

    sample = fallback_for_indicator("portable_never_empty_probe", None, "monthly")
    ok = (
        sample.get("status") == "unavailable_placeholder"
        and sample.get("is_scored") is False
        and sample.get("value") is None
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "sample_status": sample.get("status"),
                "sample_is_scored": sample.get("is_scored"),
                "sample_reason": sample.get("score_block_reason"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
