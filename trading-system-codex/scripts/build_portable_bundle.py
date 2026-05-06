from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from release_common import DIST_DIR as DIST_ROOT  # noqa: E402
from release_common import PROJECT_ROOT, should_skip  # noqa: E402

PORTABLE_ROOT = DIST_ROOT / "portable_bundle"
PORTABLE_ZIP = DIST_ROOT / "portable_bundle.zip"


def main() -> int:
    if PORTABLE_ROOT.exists():
        shutil.rmtree(PORTABLE_ROOT)
    PORTABLE_ROOT.mkdir(parents=True, exist_ok=True)
    if PORTABLE_ZIP.exists():
        PORTABLE_ZIP.unlink()

    for path in PROJECT_ROOT.iterdir():
        if should_skip(path, root=PROJECT_ROOT):
            continue
        destination = PORTABLE_ROOT / path.name
        if path.is_dir():
            shutil.copytree(
                path,
                destination,
                dirs_exist_ok=True,
                ignore=lambda src, names: [
                    name for name in names if should_skip(Path(src) / name, root=PROJECT_ROOT)
                ],
            )
        else:
            shutil.copy2(path, destination)

    shutil.copy2(PROJECT_ROOT / "start_portable.bat", PORTABLE_ROOT / "start_portable.bat")
    shutil.copy2(PROJECT_ROOT / "start_portable.sh", PORTABLE_ROOT / "start_portable.sh")
    shutil.copy2(PROJECT_ROOT / "portable.env.example", PORTABLE_ROOT / "portable.env.example")
    archive_base = str(PORTABLE_ZIP.with_suffix(""))
    shutil.make_archive(archive_base, "zip", root_dir=PORTABLE_ROOT)
    print(f"portable bundle created at {PORTABLE_ROOT}")
    print(f"portable zip created at {PORTABLE_ZIP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
