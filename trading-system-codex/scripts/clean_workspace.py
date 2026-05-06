from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REMOVABLE_DIRS = {
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "run",
    "build",
    "site",
    "htmlcov",
}

REMOVABLE_GLOBS = {
    "*.egg-info",
    "**/__pycache__",
}

REMOVABLE_FILES = {
    "coverage.xml",
    "trading_system.db-journal",
    "trading_system.db-shm",
    "trading_system.db-wal",
}

REMOVABLE_FILE_GLOBS = {
    "**/*.pyc",
    "run/*.log",
}


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except PermissionError:
        print(f"Skipped (in use): {path.relative_to(PROJECT_ROOT).as_posix()}")


def main() -> None:
    removed: list[str] = []

    for name in sorted(REMOVABLE_DIRS):
        path = PROJECT_ROOT / name
        if path.exists():
            remove_path(path)
            removed.append(path.relative_to(PROJECT_ROOT).as_posix())

    for pattern in sorted(REMOVABLE_GLOBS):
        for path in PROJECT_ROOT.glob(pattern):
            remove_path(path)
            removed.append(path.relative_to(PROJECT_ROOT).as_posix())

    for name in sorted(REMOVABLE_FILES):
        path = PROJECT_ROOT / name
        if path.exists():
            remove_path(path)
            removed.append(path.relative_to(PROJECT_ROOT).as_posix())

    for pattern in sorted(REMOVABLE_FILE_GLOBS):
        for path in PROJECT_ROOT.glob(pattern):
            remove_path(path)
            removed.append(path.relative_to(PROJECT_ROOT).as_posix())

    if removed:
        print("Removed:")
        for item in sorted(set(removed)):
            print(f"- {item}")
    else:
        print("Nothing to clean.")


if __name__ == "__main__":
    main()
