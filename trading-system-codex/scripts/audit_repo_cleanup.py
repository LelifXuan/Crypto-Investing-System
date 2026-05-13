#!/usr/bin/env python3
"""Repository audit and safe cleanup helper for Crypto Investing System."""

from __future__ import annotations
import argparse, json, shutil, sys, re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

SAFE_GENERATED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SAFE_TOP_RUNTIME_DIRS = {"cache", "logs", "runtime", "tmp"}
NEVER_DELETE = {".git", ".venv", "venv", "env", ".env", ".env.local", "data", "docs", "tests", "app", "alembic", "scripts"}


@dataclass
class Finding:
    severity: str
    category: str
    path: str
    message: str
    recommendation: str
    size_bytes: int = 0
    auto_cleanable: bool = False


def path_size(path: Path) -> int:
    if not path.exists(): return 0
    if path.is_file():
        try: return path.stat().st_size
        except OSError: return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file(): total += p.stat().st_size
        except OSError: pass
    return total


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB": return f"{n:.1f} {unit}"
        n /= 1024


def audit(repo: Path) -> list[Finding]:
    fp: list[Finding] = []
    skip_parts = {".git", ".venv", "venv", "env", "node_modules"}

    for p in repo.rglob("*"):
        if any(part in skip_parts for part in p.relative_to(repo).parts): continue
        rel = str(p.relative_to(repo))
        name = p.name

        if p.is_dir() and name in SAFE_GENERATED_DIRS:
            sz = path_size(p)
            fp.append(Finding("low", "generated_cache", rel, f"Generated cache ({human_size(sz)}).", "Safe to delete.", sz, True))

        if p.is_file() and p.suffix in {".pyc", ".pyo"}:
            sz = path_size(p)
            fp.append(Finding("low", "bytecode", rel, f"Bytecode ({human_size(sz)}).", "Safe to delete.", sz, True))

    for dn in SAFE_TOP_RUNTIME_DIRS:
        p = repo / dn
        if p.exists() and p.is_dir():
            sz = path_size(p)
            fp.append(Finding("medium", "runtime_artifact", dn, f"Runtime dir ({human_size(sz)}).", "Delete for release builds.", sz, True))

    venv = repo / ".venv"
    if venv.exists():
        fp.append(Finding("high", "release_bloat", ".venv", f"Virtual env ({human_size(path_size(venv))}).", "Do not ship. Keep in gitignore.", path_size(venv), False))

    for env_name in [".env"]:
        p = repo / env_name
        if p.exists():
            fp.append(Finding("critical", "secret_risk", env_name, "Env file in package.", "Remove from release.", path_size(p), False))

    for pattern in [re.compile(r".*\.db$"), re.compile(r".*\.db-(shm|wal|journal)$")]:
        for p in repo.rglob("*"):
            if any(part in skip_parts for part in p.relative_to(repo).parts): continue
            if p.is_file() and pattern.match(p.name):
                sz = path_size(p)
                fp.append(Finding("medium", "local_db", str(p.relative_to(repo)), f"Local DB ({human_size(sz)}).", "Do not ship.", sz, False))

    return fp


def safe_clean(repo: Path, findings: Sequence[Finding]) -> list[str]:
    removed = []
    for f in findings:
        if not f.auto_cleanable: continue
        p = repo / f.path
        if not str(p.resolve()).startswith(str(repo.resolve())): continue
        if any(part in NEVER_DELETE for part in p.relative_to(repo).parts): continue
        try:
            if p.is_dir(): shutil.rmtree(p)
            elif p.is_file(): p.unlink()
            removed.append(f.path)
        except Exception as e:
            print(f"[warn] {f.path}: {e}", file=sys.stderr)
    return removed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=".")
    p.add_argument("--json-out", default="")
    p.add_argument("--apply-safe-clean", action="store_true")
    args = p.parse_args()
    repo = Path(args.repo).resolve()
    findings = audit(repo)
    removed = safe_clean(repo, findings) if args.apply_safe_clean else []

    report = {
        "repo": str(repo),
        "apply_safe_clean": args.apply_safe_clean,
        "summary": {"findings": len(findings), "auto_cleanable_human": human_size(sum(f.size_bytes for f in findings if f.auto_cleanable)), "removed": len(removed)},
        "removed": removed,
        "findings": [asdict(f) for f in findings],
    }

    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute(): out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Findings: {report['summary']['findings']} | Auto-cleanable: {report['summary']['auto_cleanable_human']} | Removed: {report['summary']['removed']}")
    for f in findings[:10]:
        print(f"  [{f.severity}] {f.category}: {f.path} - {f.message}")
    if args.json_out: print(f"Report: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
