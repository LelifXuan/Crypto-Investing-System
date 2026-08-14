from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_script(script_name: str) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name)],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> int:
    run_script("clean_release.py")
    run_script("create_release_zip.py")
    run_script("build_portable_bundle.py")
    run_script("portable_smoke.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
