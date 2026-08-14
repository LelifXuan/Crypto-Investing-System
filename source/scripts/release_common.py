from __future__ import annotations

import json
import re
from dataclasses import dataclass
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

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(secret|password|passwd|token|api[_-]?key|access[_-]?key|private[_-]?key|jwt)"
)
SAFE_SECRET_VALUES = {"", "changeme", "change-me", "example", "your-value-here", "replace-me"}
NON_SECRET_KEYS = {
    "JWT_ALGORITHM",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "JWT_REFRESH_TOKEN_EXPIRE_MINUTES",
}


@dataclass(frozen=True)
class SecretFinding:
    path: Path
    key: str
    line_number: int


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


def scan_secret_like_content(paths: list[Path] | tuple[Path, ...]) -> list[SecretFinding]:
    """Find non-empty secret-like key/value pairs in text files.

    This intentionally reports keys only, never values, so verifier output does
    not become the next leak vector.
    """

    findings: list[SecretFinding] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        if path.name.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".7z")):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for key, line_number in scan_secret_text(text):
            findings.append(SecretFinding(path=path, key=key, line_number=line_number))
    return findings


def scan_secret_text(text: str) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if "==" in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().strip('"').strip("'")
        value = value.strip().strip('"').strip("'")
        if key in NON_SECRET_KEYS:
            continue
        if not key.upper() == key:
            continue
        if not SECRET_KEY_PATTERN.search(key):
            continue
        if value.lower() in SAFE_SECRET_VALUES:
            continue
        findings.append((key, line_number))
    return findings


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


