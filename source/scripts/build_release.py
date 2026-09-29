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
    # The private portable bundle is an explicit delivery act, never part of the
    # generic release flow: build_private_portable.py --output <zip> then
    # verify_portable_package.py --archive <zip> --extract.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
