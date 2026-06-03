from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

os.environ.setdefault("APP_DISTRIBUTION_MODE", "portable")
os.environ.setdefault("APP_BUNDLE_ROOT", str(Path(__file__).resolve().parents[1]))

BUNDLE_ROOT = Path(os.environ["APP_BUNDLE_ROOT"]).resolve()
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))


def main() -> int:
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
