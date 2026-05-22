from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "app" / "assets" / "seed_cache"
RUNTIME_DIR = ROOT / "runtime" / "cache" / "macro"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import bundled macro seed cache into runtime cache."
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing runtime seed files."
    )
    args = parser.parse_args()

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ("macro_observations_seed.json", "macro_websearch_seed.json", "seed_manifest.json"):
        source = SEED_DIR / name
        target = RUNTIME_DIR / name
        if not source.exists():
            continue
        if target.exists() and not args.force:
            continue
        shutil.copy2(source, target)
        copied.append(name)
    print(f"Imported {len(copied)} macro seed cache file(s): {', '.join(copied) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
