from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT = DIST_DIR / "trading-system-fastapi-github.zip"
PREFIX = "trading-system-fastapi/"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".local_secrets",
    "dist",
    "prompts",
}

EXCLUDED_FILES = {
    ".env",
    "coverage.xml",
    "AGENTS.md",
}

EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".sqlite3"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if path.name in EXCLUDED_FILES:
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    return False


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if path.is_dir() or should_skip(path):
                continue
            rel = path.relative_to(PROJECT_ROOT)
            zf.write(path, PREFIX + rel.as_posix())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
