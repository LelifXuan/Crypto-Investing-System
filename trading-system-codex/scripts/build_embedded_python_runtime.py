from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = PROJECT_ROOT / "portable_runtime.lock.json"
DEFAULT_REQUIREMENTS = PROJECT_ROOT / "requirements-portable.txt"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "dist" / "runtime_downloads"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)


def _ensure_embed_zip(lock: dict[str, Any], cache_dir: Path) -> Path:
    filename = str(lock["python_embed_zip"])
    archive = cache_dir / filename
    if not archive.exists():
        print(f"downloading embedded Python runtime: {lock['python_embed_url']}")
        _download(str(lock["python_embed_url"]), archive)
    actual = _sha256(archive).lower()
    expected = str(lock["python_embed_sha256"]).lower()
    if actual != expected:
        raise RuntimeError(
            f"embedded Python SHA256 mismatch for {archive.name}: expected {expected}, got {actual}"
        )
    return archive


def _patch_pth(runtime_dir: Path, python_version: str) -> None:
    major, minor, *_ = python_version.split(".")
    pth = runtime_dir / f"python{major}{minor}._pth"
    if not pth.exists():
        candidates = sorted(runtime_dir.glob("python*._pth"))
        if not candidates:
            raise RuntimeError(f"cannot find embeddable _pth file in {runtime_dir}")
        pth = candidates[0]
    lines = []
    for raw in pth.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#import site"):
            continue
        lines.append(line)
    required = [f"python{major}{minor}.zip", ".", "Lib\\site-packages", "import site"]
    merged: list[str] = []
    for line in [*lines, *required]:
        if line not in merged:
            merged.append(line)
    pth.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=True)


def _install_dependencies(
    runtime_dir: Path,
    requirements: Path,
    cache_dir: Path,
    *,
    skip_deps: bool,
) -> None:
    if skip_deps:
        print("dependency install skipped by request")
        return
    python_exe = runtime_dir / "python.exe"
    if not python_exe.exists():
        raise RuntimeError(f"embedded python.exe not found: {python_exe}")

    get_pip = cache_dir / "get-pip.py"
    if not get_pip.exists():
        print("downloading get-pip.py for embedded runtime")
        _download("https://bootstrap.pypa.io/get-pip.py", get_pip)

    _run([str(python_exe), str(get_pip), "--no-warn-script-location"], cwd=runtime_dir)
    _run(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--upgrade",
            "-r",
            str(requirements),
            "--target",
            str(runtime_dir / "Lib" / "site-packages"),
        ],
        cwd=runtime_dir,
    )


def _prune_runtime_artifacts(runtime_dir: Path) -> None:
    site_packages = runtime_dir / "Lib" / "site-packages"
    removable_names = {
        "_distutils_hack",
        "pip",
        "pkg_resources",
        "setuptools",
        "wheel",
    }
    for path in sorted(runtime_dir.rglob("*"), reverse=True):
        if path.is_file() and path.suffix.lower() in {".pyc", ".pyo"}:
            path.unlink()
            continue
        if path.is_file() and path.name == "distutils-precedence.pth":
            path.unlink()
            continue
        if path.is_file() and path.suffix.lower() in {".cmd", ".bat"}:
            path.unlink()
            continue
        if path.is_dir() and path.name == "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
            continue
        if path.is_dir() and path.name.lower() in {"tests", "test"}:
            shutil.rmtree(path, ignore_errors=True)
            continue
        if path.parent == site_packages:
            lower_name = path.name.lower()
            if lower_name in removable_names or any(
                lower_name.startswith(f"{name}-") and lower_name.endswith(".dist-info")
                for name in removable_names
            ):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()


def _scrub_runtime_text_examples(runtime_dir: Path) -> None:
    replacements = {
        "C:\\Users": "C:/Users",
        "C:\\Program Files": "C:/Program Files",
        "C:\\ProgramData\\": "C:/ProgramData/",
        "C:\\foo\\": "C:/foo/",
        "/home/": "/portable-home/",
        "/mnt/" + "data/": "/portable-data/",
    }
    text_suffixes = {".cfg", ".ini", ".md", ".py", ".pyi", ".rst", ".txt"}
    for path in runtime_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for needle, replacement in replacements.items():
            updated = updated.replace(needle, replacement)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _write_runtime_metadata(
    runtime_dir: Path,
    lock: dict[str, Any],
    requirements: Path,
    *,
    stub: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": "embedded-python-runtime-v1",
        "platform": lock["platform"],
        "python_version": lock["python_version"],
        "python_embed_sha256": lock["python_embed_sha256"],
        "requirements_file": requirements.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "stub_runtime": stub,
    }
    (runtime_dir / "portable_runtime.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _build_stub_runtime(
    runtime_dir: Path,
    lock: dict[str, Any],
    requirements: Path,
) -> dict[str, Any]:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "python.exe").write_text("portable runtime test stub\n", encoding="utf-8")
    (runtime_dir / "python311._pth").write_text(
        "python311.zip\n.\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )
    (runtime_dir / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    return _write_runtime_metadata(runtime_dir, lock, requirements, stub=True)


def build_runtime(
    target: Path,
    *,
    lock_path: Path = DEFAULT_LOCK,
    requirements: Path = DEFAULT_REQUIREMENTS,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force: bool = True,
    skip_deps: bool = False,
    stub: bool = False,
) -> dict[str, Any]:
    lock = _read_json(lock_path)
    if lock.get("platform") != "win-x64":
        raise RuntimeError(f"unsupported portable runtime platform: {lock.get('platform')}")
    if not str(lock.get("python_version", "")).startswith("3.11."):
        raise RuntimeError("portable runtime must use Python 3.11.x")
    if not requirements.exists():
        raise RuntimeError(f"portable requirements file not found: {requirements}")

    runtime_dir = target.resolve()
    if runtime_dir.exists() and force:
        shutil.rmtree(runtime_dir)
    if stub:
        return _build_stub_runtime(runtime_dir, lock, requirements)

    archive = _ensure_embed_zip(lock, cache_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(runtime_dir)
    _patch_pth(runtime_dir, str(lock["python_version"]))
    _install_dependencies(runtime_dir, requirements, cache_dir, skip_deps=skip_deps)
    _prune_runtime_artifacts(runtime_dir)
    _scrub_runtime_text_examples(runtime_dir)
    return _write_runtime_metadata(runtime_dir, lock, requirements, stub=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Windows embeddable Python runtime.")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--skip-deps", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Create a non-executable runtime skeleton for fast packaging tests only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stub = args.stub or os.getenv("PORTABLE_RUNTIME_STUB") == "1"
    metadata = build_runtime(
        args.target,
        lock_path=args.lock,
        requirements=args.requirements,
        cache_dir=args.cache_dir,
        force=not args.no_force,
        skip_deps=args.skip_deps,
        stub=stub,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
