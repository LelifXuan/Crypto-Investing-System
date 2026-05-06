from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    repo_root: Path
    bundle_root: Path
    distribution_mode: str
    runtime_root: Path
    config_dir: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path
    tmp_dir: Path
    templates_dir: Path
    static_dir: Path
    portable_env_path: Path
    database_path: Path

    @property
    def default_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"


def _detect_distribution_mode() -> str:
    mode = str(os.getenv("APP_DISTRIBUTION_MODE", "source")).strip().lower()
    if mode not in {"source", "portable"}:
        mode = "source"
    return mode


def resolve_app_paths() -> AppPaths:
    repo_root = Path(__file__).resolve().parents[2]
    distribution_mode = _detect_distribution_mode()
    bundle_root = Path(os.getenv("APP_BUNDLE_ROOT") or repo_root).resolve()
    runtime_root = (
        Path(os.getenv("APP_RUNTIME_ROOT")).resolve()
        if os.getenv("APP_RUNTIME_ROOT")
        else (bundle_root / "runtime" if distribution_mode == "portable" else bundle_root)
    )
    config_dir = runtime_root / "config"
    data_dir = runtime_root / "data"
    log_dir = runtime_root / "logs"
    cache_dir = runtime_root / "cache"
    tmp_dir = runtime_root / "tmp"
    return AppPaths(
        repo_root=repo_root,
        bundle_root=bundle_root,
        distribution_mode=distribution_mode,
        runtime_root=runtime_root,
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        cache_dir=cache_dir,
        tmp_dir=tmp_dir,
        templates_dir=repo_root / "app" / "templates",
        static_dir=repo_root / "app" / "static",
        portable_env_path=config_dir / "portable.env",
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

    if app_paths.distribution_mode == "portable" and not app_paths.portable_env_path.exists():
        secret = secrets.token_urlsafe(48)
        admin_password = secrets.token_urlsafe(18)
        app_paths.portable_env_path.write_text(
            "\n".join(
                [
                    "APP_DISTRIBUTION_MODE=portable",
                    "APP_HOST=127.0.0.1",
                    "APP_PORT=8000",
                    "APP_DEBUG=false",
                    "LOCAL_ONLY_ENFORCED=true",
                    "ENABLE_DOCS=false",
                    "ENABLE_OPENAPI=false",
                    "WORKER_PROFILE=desktop_light",
                    "MARKET_EVENTS_TRANSLATE_ENABLED=false",
                    "MARKET_EVENTS_TRANSLATION_WORKER_ENABLED=false",
                    f"DATABASE_URL={app_paths.default_database_url}",
                    f"JWT_SECRET_KEY={secret}",
                    "BOOTSTRAP_ADMIN_USERNAME=localadmin",
                    f"BOOTSTRAP_ADMIN_PASSWORD={admin_password}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    diagnostics_path = app_paths.log_dir / "portable_startup_diagnostics.log"
    try:
        diagnostics_path.write_text(
            "\n".join(
                [
                    f"distribution_mode={app_paths.distribution_mode}",
                    f"bundle_root={app_paths.bundle_root}",
                    f"runtime_root={app_paths.runtime_root}",
                    f"database_path={app_paths.database_path}",
                    f"portable_env_path={app_paths.portable_env_path}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return app_paths
