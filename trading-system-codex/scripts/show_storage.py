from __future__ import annotations

import argparse
from pathlib import Path

CATEGORIES = {
    "数据文件": [
        "data/trading_system.db",
        "data/trading_system.db-wal",
        "data/trading_system.db-shm",
    ],
    "缓存目录": ["data/cache", "cache"],
    "日志文件": ["logs"],
    "临时文件": ["tmp"],
    "便携运行数据": ["runtime"],
    "Python 虚拟环境": [".venv"],
    "Python 缓存": ["__pycache__", ".pytest_cache", ".ruff_cache"],
    "配置文件": [".env", ".env.example", "pyproject.toml"],
    "导出文件": ["data/exports"],
    "导入文件": ["data/imports"],
    "备份文件": ["data/backups"],
}


def dir_size(root: Path) -> tuple[int, float]:
    count = 0
    size = 0.0
    if not root.is_dir():
        return 0, 0.0
    for p in root.rglob("*"):
        if p.is_file():
            count += 1
            size += p.stat().st_size
    return count, size


def main():
    parser = argparse.ArgumentParser(description="显示项目存储使用情况")
    parser.add_argument("--root", default=".", help="项目根目录")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    total_size = 0.0
    total_files = 0
    results = []

    for label, paths in CATEGORIES.items():
        cat_size = 0.0
        cat_files = 0
        details = []
        for rel in paths:
            p = root / rel
            if p.is_file():
                sz = p.stat().st_size
                cat_size += sz
                cat_files += 1
                details.append(f"{rel} ({_fmt(sz)})")
            elif p.is_dir():
                cnt, sz = dir_size(p)
                cat_size += sz
                cat_files += cnt
                if cnt > 0:
                    details.append(f"{rel}/ ({cnt} 文件, {_fmt(sz)})")
        if cat_size > 0 or args.json:
            results.append(
                {
                    "label": label,
                    "size_bytes": int(cat_size),
                    "size": _fmt(cat_size),
                    "files": cat_files,
                    "details": details,
                }
            )
            total_size += cat_size
            total_files += cat_files

    if args.json:
        import json

        print(
            json.dumps(
                {"total_size": _fmt(total_size), "total_files": total_files, "categories": results},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"项目存储总计: {_fmt(total_size)} ({total_files} 文件)")
        print("-" * 50)
        for r in results:
            if r["size_bytes"] == 0:
                continue
            marker = " [!]" if r["files"] > 1000 or r["size_bytes"] > 100 * 1024 * 1024 else ""
            print(f"  {r['label']:12s} | {r['size']:>10s} | {r['files']:>5d} 文件{marker}")
            for d in r["details"]:
                print(f"    - {d}")
        print("-" * 50)
        print("可清理项: logs/、tmp/、cache/、Python 缓存")
        print("禁止删除: data/trading_system.db、.env")


def _fmt(size: float) -> str:
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.1f} GB"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size:.0f} B"


if __name__ == "__main__":
    main()
