from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class PortableSyncReport:
    status: str
    destination: str
    preserved: list[str]
    cleared: list[str]
    backup: str | None
    completed_at: str


def _copy_contents(
    source: Path,
    destination: Path,
    *,
    excluded_names: set[str] | None = None,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if excluded_names and item.name in excluded_names:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _rewrite_portable_runtime_paths(env_path: Path, destination: Path) -> None:
    if not env_path.exists():
        return
    replacements = {
        "APP_DISTRIBUTION_MODE": "portable",
        "DATABASE_URL": (
            "sqlite+aiosqlite:///"
            f"{(destination / 'runtime' / 'data' / 'trading_system.db').as_posix()}"
        ),
    }
    lines = env_path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")
    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def sync_portable_tree(
    bundle: Path,
    destination: Path,
    *,
    reset_runtime: bool = False,
    keep_backup: bool = False,
    report_path: Path | None = None,
) -> PortableSyncReport:
    bundle = Path(bundle).resolve()
    destination = Path(destination).resolve()
    if not (bundle / "runtime_env" / "python" / "python.exe").exists():
        raise RuntimeError(f"embedded Python is missing: {bundle}")
    staging = destination.with_name(f"{destination.name}.staging")
    backup = destination.with_name(f"{destination.name}.backup")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(bundle, staging)
    preserved: list[str] = []
    cleared = ["runtime/cache", "runtime/tmp"]
    if destination.exists() and not reset_runtime:
        old_runtime = destination / "runtime"
        for relative in ("config", "data"):
            source = old_runtime / relative
            if source.exists():
                _copy_contents(source, staging / "runtime" / relative)
                preserved.append(f"runtime/{relative}")
        for name in ("user_exports", "imports"):
            source = destination / name
            if source.exists():
                _copy_contents(source, staging / name)
                preserved.append(name)
        log_root = old_runtime / "logs"
        if log_root.exists():
            archive_root = staging / "runtime" / "logs" / "archive"
            _copy_contents(log_root, archive_root, excluded_names={"archive"})
            preserved.append("runtime/logs/archive")
    _rewrite_portable_runtime_paths(
        staging / "runtime" / "config" / "portable.env",
        destination,
    )
    for relative in ("cache", "tmp"):
        shutil.rmtree(staging / "runtime" / relative, ignore_errors=True)
        (staging / "runtime" / relative).mkdir(parents=True, exist_ok=True)
    try:
        if destination.exists():
            destination.replace(backup)
        staging.replace(destination)
        if not keep_backup:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        if backup.exists():
            backup.replace(destination)
        raise
    report = PortableSyncReport(
        status="success",
        destination=str(destination),
        preserved=preserved,
        cleared=cleared,
        backup=str(backup) if keep_backup and backup.exists() else None,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def finalize_sync(destination: Path) -> None:
    destination = Path(destination).resolve()
    backup = destination.with_name(f"{destination.name}.backup")
    shutil.rmtree(backup, ignore_errors=True)


def rollback_sync(destination: Path) -> None:
    destination = Path(destination).resolve()
    backup = destination.with_name(f"{destination.name}.backup")
    if not backup.exists():
        return
    failed = destination.with_name(f"{destination.name}.failed")
    shutil.rmtree(failed, ignore_errors=True)
    if destination.exists():
        destination.replace(failed)
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            backup.replace(destination)
            last_error = None
            break
        except OSError as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    shutil.rmtree(failed, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely sync a built portable tree.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--reset-runtime", action="store_true")
    parser.add_argument("--keep-backup", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize_sync(args.destination)
        return 0
    if args.rollback:
        rollback_sync(args.destination)
        return 0
    report = sync_portable_tree(
        args.bundle,
        args.destination,
        reset_runtime=args.reset_runtime,
        keep_backup=args.keep_backup,
        report_path=args.report,
    )
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
