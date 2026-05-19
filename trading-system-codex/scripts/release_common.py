from __future__ import annotations

from pathlib import Path

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


def should_skip(path: Path, *, root: Path = PROJECT_ROOT) -> bool:
    relative = path.relative_to(root)
    parts = set(relative.parts)
    top_level = relative.parts[0] if relative.parts else ""
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
