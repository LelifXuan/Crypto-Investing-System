from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.network.proxy_detector import detect_proxy, safe_proxy_state, write_proxy_state


def main() -> int:
    result = detect_proxy()
    write_proxy_state(result)
    print(json.dumps(safe_proxy_state(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
