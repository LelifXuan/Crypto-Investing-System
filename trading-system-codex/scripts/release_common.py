from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"

EXCLUDED_ANY_DIRS = {
    ".git",
    ".github",
    ".venv",
    ".pytest_cache",
    ".playwright-mcp",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".local_secrets",
}

EXCLUDED_TOP_LEVEL_DIRS = {
    "dist",
    "bin",
    "prompts",
    "run",
    "runtime",
    "logs",
    "obj",
    "cache",
    "config",
    "data",
    "tmp",
    "runtime_env",
    "tools",
    "docs",
    "tests",
    "reports",
}

EXCLUDED_DIRS = EXCLUDED_ANY_DIRS | EXCLUDED_TOP_LEVEL_DIRS

EXCLUDED_FILES = {
    ".env",
    "coverage.xml",
    "AGENTS.md",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
    "trading_system.db",
    "trading_system.db-shm",
    "trading_system.db-wal",
    "trading_system.db-journal",
    "double-client.err.log",
    "storage_manifest.json",
}

EXCLUDED_SUFFIXES = {
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
    ".dll",
    ".sqlite3",
}

RESIDUE_DIRS = {
    "run",
    "runtime",
    "dist",
    "bin",
    "logs",
    "obj",
    "cache",
    "tmp",
    "runtime_env",
    "__pycache__",
    ".pytest_cache",
    ".playwright-mcp",
    ".ruff_cache",
    ".mypy_cache",
}

RESIDUE_FILES = {
    ".env",
    "trading_system.db",
    "trading_system.db-shm",
    "trading_system.db-wal",
    "trading_system.db-journal",
    "storage_manifest.json",
}

RESIDUE_SUFFIXES = {
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
    ".dll",
}

# Path used as the single source of portable exclusion rules, consumed by
# both Python (verify_portable_release.py) and PowerShell
# (sync_portable_local.ps1) so all portable tooling agrees on what must
# never ship.
PORTABLE_EXCLUDES_JSON = DIST_DIR / "portable_excludes.json"


def should_skip(path: Path, *, root: Path = PROJECT_ROOT) -> bool:
    relative = path.relative_to(root)
    parts = set(relative.parts)
    top_level = relative.parts[0] if relative.parts else ""
    if path.is_symlink():
        return True
    if parts & EXCLUDED_ANY_DIRS:
        return True
    if top_level in EXCLUDED_TOP_LEVEL_DIRS:
        return True
    if path.name in EXCLUDED_FILES:
        return True
    if any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    return False


def release_residue(root: Path = PROJECT_ROOT) -> list[Path]:
    findings: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root)
        top_level = relative.parts[0] if relative.parts else ""
        parts = set(relative.parts)
        if top_level in RESIDUE_DIRS or "__pycache__" in parts:
            findings.append(path)
            continue
        if path.name in RESIDUE_FILES:
            findings.append(path)
            continue
        if any(path.name.endswith(suffix) for suffix in RESIDUE_SUFFIXES):
            findings.append(path)
            continue
        if path.suffix in RESIDUE_SUFFIXES:
            findings.append(path)
    return findings


def dump_portable_excludes(target: Path = PORTABLE_EXCLUDES_JSON) -> Path:
    """Serialise the portable exclusion tables to JSON.

    Other portable tooling (the strict verifier, the PowerShell sync
    script) reads the same file so the truth lives in exactly one place.
    Returns the path that was written.
    """

    payload: dict[str, Any] = {
        "schema_version": "portable-excludes-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "excluded_any_dirs": sorted(EXCLUDED_ANY_DIRS),
        "excluded_top_level_dirs": sorted(EXCLUDED_TOP_LEVEL_DIRS),
        "excluded_dirs": sorted(EXCLUDED_DIRS),
        "excluded_files": sorted(EXCLUDED_FILES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "residue_dirs": sorted(RESIDUE_DIRS),
        "residue_files": sorted(RESIDUE_FILES),
        "residue_suffixes": sorted(RESIDUE_SUFFIXES),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_portable_excludes(source: Path = PORTABLE_EXCLUDES_JSON) -> dict[str, list[str]]:
    """Read a previously dumped portable_excludes.json.

    Returns the parsed payload. Callers that need to assert existence should
    call :func:`dump_portable_excludes` first to guarantee the file is on
    disk before reading.
    """

    return json.loads(source.read_text(encoding="utf-8"))
