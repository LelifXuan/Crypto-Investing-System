from __future__ import annotations

import argparse
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
    "runtime",
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
    "data/trading_system.db-journal",
    "data/trading_system.db-shm",
    "data/trading_system.db-wal",
}

REMOVABLE_FILE_GLOBS = {
    "**/*.pyc",
    "run/*.log",
}

CLEAR_CACHE_DIRS = {
    "cache",
    "data/cache",
    "tmp",
}

CLEAR_LOGS = {
    "logs",
}


def remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        return True
    except PermissionError:
        print(f"Skipped (in use): {path.relative_to(PROJECT_ROOT).as_posix()}")
        return False


def clear_dir(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    count = 0
    for item in path.iterdir():
        if remove_path(item):
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="清理项目工作区")
    parser.add_argument("--clear-data", action="store_true", help="清除 SQLite WAL/日志残留（保留主数据库）")
    parser.add_argument("--clear-logs", action="store_true", help="清除日志目录内容")
    parser.add_argument("--clear-cache", action="store_true", help="清除缓存目录内容")
    parser.add_argument("--clear-all", action="store_true", help="清除全部可清理内容（保留 DB + .env）")
    args = parser.parse_args()

    removed: list[str] = []

    if args.clear_all:
        args.clear_data = True
        args.clear_logs = True
        args.clear_cache = True

    for name in sorted(REMOVABLE_DIRS):
        path = PROJECT_ROOT / name
        if remove_path(path):
            removed.append(f"dir:{path.relative_to(PROJECT_ROOT).as_posix()}")

    for pattern in sorted(REMOVABLE_GLOBS):
        for path in PROJECT_ROOT.glob(pattern):
            if remove_path(path):
                removed.append(f"glob:{path.relative_to(PROJECT_ROOT).as_posix()}")

    for name in sorted(REMOVABLE_FILES):
        path = PROJECT_ROOT / name
        if remove_path(path):
            removed.append(f"file:{path.relative_to(PROJECT_ROOT).as_posix()}")

    for pattern in sorted(REMOVABLE_FILE_GLOBS):
        for path in PROJECT_ROOT.glob(pattern):
            if remove_path(path):
                removed.append(f"glob_pyc:{path.relative_to(PROJECT_ROOT).as_posix()}")

    if args.clear_cache:
        for name in sorted(CLEAR_CACHE_DIRS):
            path = PROJECT_ROOT / name
            cnt = clear_dir(path)
            if cnt:
                removed.append(f"cache:{path.relative_to(PROJECT_ROOT).as_posix()} ({cnt} items)")

    if args.clear_logs:
        for name in sorted(CLEAR_LOGS):
            path = PROJECT_ROOT / name
            cnt = clear_dir(path)
            if cnt:
                removed.append(f"logs:{path.relative_to(PROJECT_ROOT).as_posix()} ({cnt} items)")

    if removed:
        print(f"Cleaned {len(removed)} items:")
        for item in sorted(set(removed)):
            print(f"  - {item}")
    else:
        print("Nothing to clean.")


if __name__ == "__main__":
    main()
