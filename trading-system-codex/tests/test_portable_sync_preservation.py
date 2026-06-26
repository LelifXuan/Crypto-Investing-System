from __future__ import annotations

from pathlib import Path

from scripts.portable_sync import rollback_sync, sync_portable_tree


def test_sync_preserves_config_data_and_user_files_but_rebuilds_cache(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    destination = tmp_path / "TradingSystemPortable"
    (bundle / "app").mkdir(parents=True)
    (bundle / "app" / "version.txt").write_text("1.6.0", encoding="utf-8")
    (bundle / "runtime_env" / "python").mkdir(parents=True)
    (bundle / "runtime_env" / "python" / "python.exe").write_text("", encoding="utf-8")
    (destination / "runtime" / "config").mkdir(parents=True)
    (destination / "runtime" / "data").mkdir(parents=True)
    (destination / "runtime" / "cache").mkdir(parents=True)
    (destination / "runtime" / "config" / "portable.env").write_text(
        "\n".join(
            [
                "JWT_SECRET_KEY=keep-me",
                "DATABASE_URL=sqlite+aiosqlite:///E:/old/source/trading_system.db",
            ]
        ),
        encoding="utf-8",
    )
    (destination / "runtime" / "data" / "trading_system.db").write_text(
        "database",
        encoding="utf-8",
    )
    (destination / "runtime" / "cache" / "stale.json").write_text(
        "stale",
        encoding="utf-8",
    )
    (destination / "user_exports").mkdir(parents=True)
    (destination / "user_exports" / "notes.csv").write_text("keep", encoding="utf-8")

    report = sync_portable_tree(bundle, destination)

    assert report.status == "success"
    assert (destination / "app" / "version.txt").read_text(encoding="utf-8") == "1.6.0"
    assert "keep-me" in (
        destination / "runtime" / "config" / "portable.env"
    ).read_text(encoding="utf-8")
    portable_env = (
        destination / "runtime" / "config" / "portable.env"
    ).read_text(encoding="utf-8")
    assert destination.as_posix() in portable_env
    assert "E:/old/source" not in portable_env
    assert (destination / "runtime" / "data" / "trading_system.db").exists()
    assert not (destination / "runtime" / "cache" / "stale.json").exists()
    assert (destination / "user_exports" / "notes.csv").exists()


def test_powershell_sync_delegates_to_safe_staging_sync() -> None:
    source = Path("scripts/sync_portable_local.ps1").read_text(encoding="utf-8")

    assert "portable_sync.py" in source
    assert "portable_playwright_audit.py" in source
    assert "Remove-Item -LiteralPath $resolvedDestination.Path -Recurse -Force" not in source
    assert 'Join-Path $ScriptPath ".."' in source


def test_sync_can_roll_back_after_post_sync_validation_failure(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    destination = tmp_path / "portable"
    (bundle / "runtime_env" / "python").mkdir(parents=True)
    (bundle / "runtime_env" / "python" / "python.exe").write_text("", encoding="utf-8")
    (bundle / "version.txt").write_text("new", encoding="utf-8")
    destination.mkdir()
    (destination / "version.txt").write_text("old", encoding="utf-8")

    sync_portable_tree(bundle, destination, keep_backup=True)
    rollback_sync(destination)

    assert (destination / "version.txt").read_text(encoding="utf-8") == "old"

    rollback_sync(destination)

    assert (destination / "version.txt").read_text(encoding="utf-8") == "old"
