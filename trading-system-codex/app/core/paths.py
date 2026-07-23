from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    repo_root: Path
    bundle_root: Path
    runtime_root: Path
    release_root: Path
    resource_root: Path
    immutable_runtime_root: Path
    embedded_python_dir: Path
    config_dir: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path
    tmp_dir: Path
    templates_dir: Path
    static_dir: Path
    database_path: Path

    @property
    def default_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"


def resolve_app_paths() -> AppPaths:
    repo_root = Path(__file__).resolve().parents[2]
    bundle_root = Path(os.getenv("APP_BUNDLE_ROOT") or repo_root).resolve()
    release_root = Path(os.getenv("APP_RELEASE_ROOT") or bundle_root).resolve()
    resource_root = Path(os.getenv("APP_RESOURCE_ROOT") or repo_root).resolve()
    runtime_root = Path(os.getenv("APP_RUNTIME_ROOT") or (repo_root / "runtime")).resolve()
    config_dir = runtime_root / "config"
    data_dir = runtime_root / "data"
    log_dir = runtime_root / "logs"
    cache_dir = runtime_root / "cache"
    tmp_dir = runtime_root / "tmp"
    immutable_runtime_root = release_root
    embedded_python_dir = release_root / "python"
    return AppPaths(
        repo_root=repo_root,
        bundle_root=bundle_root,
        runtime_root=runtime_root,
        release_root=release_root,
        resource_root=resource_root,
        immutable_runtime_root=immutable_runtime_root,
        embedded_python_dir=embedded_python_dir,
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        cache_dir=cache_dir,
        tmp_dir=tmp_dir,
        templates_dir=repo_root / "app" / "templates",
        static_dir=repo_root / "app" / "static",
        database_path=data_dir / "trading_system.db",
    )


app_paths = resolve_app_paths()


def bootstrap_runtime_environment() -> AppPaths:
    for path in (
        app_paths.runtime_root,
        app_paths.config_dir,
        app_paths.data_dir,
        app_paths.log_dir,
        app_paths.cache_dir,
        app_paths.tmp_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    manifest_path = app_paths.runtime_root / "storage_manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(
                {
                    "app_version": "1.8.0",
                    "bundle_root": app_paths.bundle_root.as_posix(),
                    "runtime_root": app_paths.runtime_root.as_posix(),
                    "release_root": app_paths.release_root.as_posix(),
                    "resource_root": app_paths.resource_root.as_posix(),
                    "immutable_runtime_root": app_paths.immutable_runtime_root.as_posix(),
                    "embedded_python_dir": app_paths.embedded_python_dir.as_posix(),
                    "database_path": app_paths.database_path.as_posix(),
                    "config_dir": app_paths.config_dir.as_posix(),
                    "data_dir": app_paths.data_dir.as_posix(),
                    "cache_dir": app_paths.cache_dir.as_posix(),
                    "log_dir": app_paths.log_dir.as_posix(),
                    "tmp_dir": app_paths.tmp_dir.as_posix(),
                    "long_term": [
                        "market_candles",
                        "mark_prices",
                        "strategy_decision",
                        "signal_outcome",
                        "translation_text_cache",
                        "derivatives_archive",
                    ],
                    "ttl_cache": ["page_snapshot_cache", "computed_dataset_cache"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return app_paths
