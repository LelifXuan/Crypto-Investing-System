#!/usr/bin/env python3
"""Strict verifier for the V1.3 Windows true-portable release.

Copy this file to:
    scripts/verify_portable_release.py

Typical usage:
    python scripts/verify_portable_release.py \
        --repo . \
        --portable-root dist/portable_bundle \
        --zip dist/portable_bundle.zip \
        --strict \
        --json-out reports/verify_portable_release.json

This script intentionally performs static checks first, so it can run on non-Windows
CI to catch release hygiene and stub-runtime mistakes. If --smoke is passed and the
host can execute the bundled interpreter, it also runs import smoke tests.
"""

from __future__ import annotations

# ruff: noqa: E501,I001

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_common import (  # noqa: E402
    PROJECT_ROOT,
    dump_portable_excludes,
    load_portable_excludes,
)

REQUIRED_ROOT_FILES = [
    "start_portable.bat",
    "README_PORTABLE.md",
    "portable.env.example",
    "portable_runtime.lock.json",
    "requirements-portable.txt",
    "release_manifest.json",
    "runtime_env/python/portable_runtime.json",
]

REQUIRED_PYTHON_FILES = [
    "runtime_env/python/python.exe",
    "runtime_env/python/python311.dll",
    "runtime_env/python/python311.zip",
    "runtime_env/python/python311._pth",
]

SMOKE_IMPORTS = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "aiosqlite",
    "pydantic",
    "starlette",
    "alembic",
    "jinja2",
    "httpx",
    "websockets",
]


def _load_required_site_packages() -> list[str]:
    """Parse requirements-portable.txt for the canonical site-packages
    list. ``portable_modules.parse_requirements`` is the single source of
    truth so this list and the preflight check cannot drift.
    """

    from portable_modules import parse_requirements

    requirements = PROJECT_ROOT / "requirements-portable.txt"
    if not requirements.exists():
        return SMOKE_IMPORTS
    return parse_requirements(requirements)


# Required site-packages. Populated at audit time by
# ``_load_required_site_packages`` so changes to the requirements file
# flow through without script edits.
REQUIRED_SITE_PACKAGES: list[str] = []

ABSOLUTE_PATH_PATTERNS = [
    r"[A-Za-z]:\\",
    r"/home/",
    r"/mnt/",
    r"/Users/",
]


# Each finding code maps to a short remediation hint aimed at the
# engineer reading the JSON report. New findings should add an entry
# here so the report is self-explanatory.
REMEDIATION_MAP: dict[str, str] = {
    "missing_required_file": "Restore the file from the source tree; portable bundle must include it.",
    "launcher_missing": "Build TradingSystemLauncher.exe via dotnet publish tools/launcher or accept start_portable.bat as the official fallback in the release notes.",
    "invalid_text_encoding": "Save the file as UTF-8 (no BOM). The bundle verifier requires UTF-8 throughout.",
    "invalid_json": "Fix the JSON syntax; portable bundle release manifest must be valid JSON.",
    "invalid_json_type": "The file must contain a JSON object, not a list or scalar.",
    "runtime_schema_invalid": "Regenerate the embedded runtime via scripts/build_embedded_python_runtime.py so portable_runtime.json has the expected schema_version.",
    "runtime_platform_invalid": "The lock file must declare platform=win-x64. Update portable_runtime.lock.json.",
    "runtime_python_version_invalid": "portable_runtime.lock.json must pin python_version to a 3.11.x release. Edit the lock and rebuild.",
    "stub_runtime_enabled": "Official releases must set PORTABLE_RUNTIME_STUB=0 (or unset) and rebuild the runtime. Fast-test stubs are not allowed for release builds.",
    "manifest_release_type_invalid": "release_manifest.json release_type must be 'embedded_runtime_portable'. Regenerate via build_portable_bundle.py.",
    "manifest_python_embedded_invalid": "release_manifest.json must set python_embedded=true. Regenerate via build_portable_bundle.py.",
    "manifest_platform_invalid": "release_manifest.json must declare platform=win-x64.",
    "manifest_runtime_path_invalid": "python_runtime_path must be 'runtime_env/python/python.exe' (forward slashes).",
    "manifest_stub_runtime": "release_manifest.json must record runtime.stub_runtime=false for official releases.",
    "manifest_absolute_path": "release_manifest.json must not contain local absolute paths. The build process should normalise such references.",
    "manifest_file_count_mismatch": "file_count in the manifest must equal the number of files in the files list. Rebuild via build_portable_bundle.py.",
    "manifest_missing_required_file": "Add the missing file to the bundle source tree; portable release must include it.",
    "lock_python_embedded_invalid": "portable_runtime.lock.json must set python_embedded=true.",
    "lock_platform_invalid": "portable_runtime.lock.json must target win-x64.",
    "lock_python_version_invalid": "portable_runtime.lock.json should pin python_version to a 3.11.x release.",
    "python_exe_not_pe": "runtime_env/python/python.exe is not a Windows PE binary. The embedded runtime did not install correctly; rebuild via build_embedded_python_runtime.py.",
    "python_exe_too_small": "runtime_env/python/python.exe is suspiciously small; the embedded runtime is likely a stub. Rebuild via build_embedded_python_runtime.py.",
    "python_dll_not_pe": "runtime_env/python/python311.dll is not a valid Windows DLL. Rebuild the embedded runtime.",
    "python_dll_too_small": "runtime_env/python/python311.dll is suspiciously small; rebuild the embedded runtime.",
    "python_zip_too_small": "runtime_env/python/python311.zip is missing the standard library; rebuild the embedded runtime.",
    "pth_missing_site_packages": "Add 'Lib\\\\site-packages' to runtime_env/python/python311._pth.",
    "pth_missing_import_site": "Add 'import site' to runtime_env/python/python311._pth.",
    "pth_parent_path": "Remove any '..' references from python311._pth; portable runtime must not depend on parent directories.",
    "site_package_missing": "Re-run pip install -r requirements-portable.txt in the embedded runtime. The bundle's site-packages directory is missing the listed package.",
    "bat_not_using_embedded_python": "start_portable.bat must invoke runtime_env\\\\python\\\\python.exe; it must not fall back to system Python.",
    "bat_may_use_system_python": "start_portable.bat may be falling back to system Python. Verify only embedded python.exe is referenced.",
    "bat_missing_app_python_exe": "start_portable.bat should set APP_PYTHON_EXE for logging and preflight. Update the bat.",
    "sh_not_using_embedded_python": "start_portable.sh should reference runtime_env/python/python or clearly state it is Windows-only.",
    "forbidden_artifacts_present": "Update release_common.EXCLUDED_* to also cover these paths and rebuild the bundle.",
    "source_local_artifact_present": "Remove this file from the source tree or extend the gitignore so it never reaches the portable bundle.",
    "launcher_csproj_not_self_contained": "tools/launcher/TradingSystemLauncher.csproj must set PublishSingleFile=true, SelfContained=true, and RuntimeIdentifier=win-x64.",
    "launcher_csproj_missing": "Add tools/launcher/TradingSystemLauncher.csproj or document start_portable.bat as the official fallback.",
    "smoke_skipped_non_windows": "Run the smoke test on a Windows host with the bundled python.exe.",
    "smoke_python_missing": "Rebuild the embedded runtime; the bundled python.exe is missing.",
    "smoke_exception": "Check the embedded runtime; the smoke import test could not start.",
    "smoke_import_failed": "Check embedded runtime site-packages; the smoke import test failed. Last 1000 chars of stderr are attached.",
    "bundle_missing": "Run build_portable_bundle.py to produce dist/portable_bundle before running the verifier.",
}


def _load_excludes() -> dict[str, set[str]]:
    """Load portable exclusion rules, generating the JSON on demand.

    The verifier and the PowerShell sync script must agree on what is
    forbidden. ``release_common.dump_portable_excludes`` is the single
    source of truth; we ensure the file exists before reading.
    """

    dump_portable_excludes()
    payload = load_portable_excludes()
    any_dirs = set(payload.get("excluded_any_dirs") or [])
    top_level_dirs = set(payload.get("excluded_top_level_dirs") or [])
    if not any_dirs and not top_level_dirs:
        any_dirs = set(payload.get("excluded_dirs", []))
    return {
        "exact": set(payload.get("excluded_files", [])),
        "parts": any_dirs,
        "top_level_dirs": top_level_dirs,
        "suffixes": set(payload.get("excluded_suffixes", [])),
    }


class BundleReader(Protocol):
    source_label: str

    def exists(self, name: str) -> bool: ...

    def list_files(self) -> list[str]: ...

    def read_bytes(self, name: str, limit: int | None = None) -> bytes: ...

    def size(self, name: str) -> int | None: ...


class DirBundleReader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.source_label = str(self.root)

    def _path(self, name: str) -> Path:
        return self.root / name

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def list_files(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            str(path.relative_to(self.root)).replace("\\", "/")
            for path in self.root.rglob("*")
            if path.is_file()
        )

    def read_bytes(self, name: str, limit: int | None = None) -> bytes:
        path = self._path(name)
        with path.open("rb") as handle:
            return handle.read() if limit is None else handle.read(limit)

    def size(self, name: str) -> int | None:
        path = self._path(name)
        return path.stat().st_size if path.exists() else None


class ZipBundleReader:
    def __init__(self, archive_path: Path):
        self.archive_path = archive_path.resolve()
        self.source_label = str(self.archive_path)
        with zipfile.ZipFile(self.archive_path) as archive:
            raw_names = [n.replace("\\", "/") for n in archive.namelist() if not n.endswith("/")]
        self._prefix = self._detect_prefix(raw_names)
        self._names = sorted(self._strip_prefix(n) for n in raw_names)

    @staticmethod
    def _detect_prefix(names: list[str]) -> str:
        if "release_manifest.json" in names:
            return ""
        candidates = [n.split("/", 1)[0] + "/" for n in names if "/" in n]
        for prefix in sorted(set(candidates)):
            if prefix + "release_manifest.json" in names:
                return prefix
        return ""

    def _strip_prefix(self, name: str) -> str:
        if self._prefix and name.startswith(self._prefix):
            return name[len(self._prefix) :]
        return name

    def _actual_name(self, name: str) -> str:
        return f"{self._prefix}{name}" if self._prefix else name

    def exists(self, name: str) -> bool:
        return name in self._names

    def list_files(self) -> list[str]:
        return self._names

    def read_bytes(self, name: str, limit: int | None = None) -> bytes:
        with zipfile.ZipFile(self.archive_path) as archive:
            with archive.open(self._actual_name(name)) as handle:
                return handle.read() if limit is None else handle.read(limit)

    def size(self, name: str) -> int | None:
        actual = self._actual_name(name)
        with zipfile.ZipFile(self.archive_path) as archive:
            try:
                return archive.getinfo(actual).file_size
            except KeyError:
                return None


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    remediation: str | None = None


@dataclass
class Report:
    status: str
    strict: bool
    source: str
    total_findings: int
    counts: dict[str, int]
    findings: list[dict[str, str | None]]
    summary: dict[str, object]
    summary_text: str = ""


class Auditor:
    def __init__(self, reader: BundleReader, *, strict: bool = False, smoke: bool = False):
        self.reader = reader
        self.strict = strict
        self.smoke = smoke
        self.findings: list[Finding] = []
        self.summary: dict[str, object] = {}

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        path: str | None = None,
        *,
        remediation: str | None = None,
    ) -> None:
        if remediation is None:
            remediation = REMEDIATION_MAP.get(code)
        self.findings.append(
            Finding(severity=severity, code=code, message=message, path=path, remediation=remediation)
        )

    def require_exists(self, path: str, severity: str = "critical") -> bool:
        if not self.reader.exists(path):
            self.add(severity, "missing_required_file", f"required file is missing: {path}", path)
            return False
        return True

    def read_text(self, path: str) -> str | None:
        if not self.reader.exists(path):
            return None
        try:
            return self.reader.read_bytes(path).decode("utf-8")
        except UnicodeDecodeError:
            self.add("high", "invalid_text_encoding", f"file is not valid UTF-8: {path}", path)
            return None

    def read_json(self, path: str) -> dict[str, object] | None:
        text = self.read_text(path)
        if text is None:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            self.add("critical", "invalid_json", f"invalid JSON: {exc}", path)
            return None
        if not isinstance(payload, dict):
            self.add("critical", "invalid_json_type", "expected JSON object", path)
            return None
        return payload

    def check_required_files(self) -> None:
        for path in REQUIRED_ROOT_FILES + REQUIRED_PYTHON_FILES:
            self.require_exists(path)
        launcher_exists = self.reader.exists("TradingSystemLauncher.exe")
        self.summary["launcher_present"] = launcher_exists
        if not launcher_exists:
            self.add(
                "medium",
                "launcher_missing",
                "TradingSystemLauncher.exe is missing; start_portable.bat must remain the official fallback.",
                "TradingSystemLauncher.exe",
            )

    def check_runtime_metadata(self) -> None:
        runtime = self.read_json("runtime_env/python/portable_runtime.json")
        manifest = self.read_json("release_manifest.json")
        lock = self.read_json("portable_runtime.lock.json")
        self.summary["runtime_metadata"] = runtime or {}

        if runtime:
            if runtime.get("schema_version") != "embedded-python-runtime-v1":
                self.add(
                    "high",
                    "runtime_schema_invalid",
                    "unexpected portable runtime schema",
                    "runtime_env/python/portable_runtime.json",
                )
            if runtime.get("platform") != "win-x64":
                self.add(
                    "critical",
                    "runtime_platform_invalid",
                    "portable runtime platform must be win-x64",
                    "runtime_env/python/portable_runtime.json",
                )
            version = str(runtime.get("python_version", ""))
            if not version.startswith("3.11."):
                self.add(
                    "critical",
                    "runtime_python_version_invalid",
                    f"expected Python 3.11.x, got {version}",
                    "runtime_env/python/portable_runtime.json",
                )
            if runtime.get("stub_runtime") is not False:
                self.add(
                    "critical",
                    "stub_runtime_enabled",
                    "portable runtime is still a stub; official V1.3 portable release must have stub_runtime=false",
                    "runtime_env/python/portable_runtime.json",
                )

        if manifest:
            self.summary["release_type"] = manifest.get("release_type")
            if manifest.get("release_type") != "embedded_runtime_portable":
                self.add(
                    "critical",
                    "manifest_release_type_invalid",
                    "release_type must be embedded_runtime_portable",
                    "release_manifest.json",
                )
            if manifest.get("python_embedded") is not True:
                self.add(
                    "critical",
                    "manifest_python_embedded_invalid",
                    "python_embedded must be true",
                    "release_manifest.json",
                )
            if manifest.get("platform") != "win-x64":
                self.add(
                    "critical",
                    "manifest_platform_invalid",
                    "platform must be win-x64",
                    "release_manifest.json",
                )
            if manifest.get("python_runtime_path") != "runtime_env/python/python.exe":
                self.add(
                    "high",
                    "manifest_runtime_path_invalid",
                    "python_runtime_path must be runtime_env/python/python.exe",
                    "release_manifest.json",
                )
            embedded_runtime = manifest.get("runtime")
            if (
                isinstance(embedded_runtime, dict)
                and embedded_runtime.get("stub_runtime") is not False
            ):
                self.add(
                    "critical",
                    "manifest_stub_runtime",
                    "release_manifest.json still records runtime.stub_runtime=true",
                    "release_manifest.json",
                )
            manifest_text = json.dumps(manifest, ensure_ascii=False)
            for pattern in ABSOLUTE_PATH_PATTERNS:
                if re.search(pattern, manifest_text):
                    self.add(
                        "high",
                        "manifest_absolute_path",
                        f"manifest appears to contain local absolute path pattern: {pattern}",
                        "release_manifest.json",
                    )
            files = manifest.get("files")
            if isinstance(files, list):
                if manifest.get("file_count") != len(files):
                    self.add(
                        "medium",
                        "manifest_file_count_mismatch",
                        "manifest file_count does not match files length",
                        "release_manifest.json",
                    )
                for required in REQUIRED_ROOT_FILES + REQUIRED_PYTHON_FILES:
                    if required not in files:
                        self.add(
                            "high",
                            "manifest_missing_required_file",
                            f"manifest files list does not include {required}",
                            "release_manifest.json",
                        )

        if lock:
            if lock.get("python_embedded") is not True:
                self.add(
                    "high",
                    "lock_python_embedded_invalid",
                    "portable_runtime.lock.json should set python_embedded=true",
                    "portable_runtime.lock.json",
                )
            if lock.get("platform") != "win-x64":
                self.add(
                    "high",
                    "lock_platform_invalid",
                    "portable_runtime.lock.json should target win-x64",
                    "portable_runtime.lock.json",
                )
            version = str(lock.get("python_version", ""))
            if not version.startswith("3.11."):
                self.add(
                    "high",
                    "lock_python_version_invalid",
                    f"portable lock should use Python 3.11.x, got {version}",
                    "portable_runtime.lock.json",
                )

    def check_python_binaries(self) -> None:
        exe = "runtime_env/python/python.exe"
        if self.reader.exists(exe):
            head = self.reader.read_bytes(exe, limit=2)
            size = self.reader.size(exe) or 0
            self.summary["python_exe_size"] = size
            if head != b"MZ":
                self.add(
                    "critical",
                    "python_exe_not_pe",
                    "python.exe is not a Windows PE executable; likely a text stub",
                    exe,
                )
            if size < 64 * 1024:
                self.add(
                    "critical",
                    "python_exe_too_small",
                    f"python.exe size is suspiciously small: {size} bytes",
                    exe,
                )

        dll = "runtime_env/python/python311.dll"
        if self.reader.exists(dll):
            head = self.reader.read_bytes(dll, limit=2)
            size = self.reader.size(dll) or 0
            self.summary["python_dll_size"] = size
            if head != b"MZ":
                self.add(
                    "critical", "python_dll_not_pe", "python311.dll is not a Windows PE binary", dll
                )
            if size < 1024 * 1024:
                self.add(
                    "high",
                    "python_dll_too_small",
                    f"python311.dll size is suspiciously small: {size} bytes",
                    dll,
                )

        pyzip = "runtime_env/python/python311.zip"
        if self.reader.exists(pyzip):
            size = self.reader.size(pyzip) or 0
            self.summary["python_stdlib_zip_size"] = size
            if size < 2 * 1024 * 1024:
                self.add(
                    "high",
                    "python_zip_too_small",
                    f"python311.zip size is suspiciously small: {size} bytes",
                    pyzip,
                )

    def check_pth_and_site_packages(self) -> None:
        required_packages = _load_required_site_packages()
        pth = "runtime_env/python/python311._pth"
        text = self.read_text(pth)
        if text is not None:
            normalized = text.replace("/", "\\")
            if "Lib\\site-packages" not in normalized:
                self.add(
                    "critical",
                    "pth_missing_site_packages",
                    "python311._pth must include Lib\\site-packages",
                    pth,
                )
            if "import site" not in text:
                self.add(
                    "critical",
                    "pth_missing_import_site",
                    "python311._pth must include import site",
                    pth,
                )
            if ".." in text:
                self.add(
                    "medium",
                    "pth_parent_path",
                    "python311._pth should not reference parent directories",
                    pth,
                )

        names = set(self.reader.list_files())
        package_presence: dict[str, bool] = {}
        for package in required_packages:
            package_path = f"runtime_env/python/Lib/site-packages/{package}/__init__.py"
            alt_prefix = f"runtime_env/python/Lib/site-packages/{package}/"
            module_file = f"runtime_env/python/Lib/site-packages/{package}.py"
            present = (
                package_path in names
                or module_file in names
                or any(name.startswith(alt_prefix) for name in names)
            )
            package_presence[package] = present
            if not present:
                self.add(
                    "critical",
                    "site_package_missing",
                    f"required dependency package is missing: {package}",
                    alt_prefix,
                )
        self.summary["required_site_packages"] = package_presence

    def check_start_scripts(self) -> None:
        bat = self.read_text("start_portable.bat")
        if bat is not None:
            lower = bat.lower()
            required = r"runtime_env\python\python.exe"
            if required not in lower:
                self.add(
                    "critical",
                    "bat_not_using_embedded_python",
                    "start_portable.bat must call runtime_env\\python\\python.exe",
                    "start_portable.bat",
                )
            forbidden_tokens = ["where python", " py ", " py.exe", "python -m uvicorn"]
            for token in forbidden_tokens:
                if token in lower and "%app_python_exe%" not in lower:
                    self.add(
                        "high",
                        "bat_may_use_system_python",
                        f"start script may fall back to system Python: {token}",
                        "start_portable.bat",
                    )
            if "%APP_PYTHON_EXE%" not in bat and "%app_python_exe%" not in lower:
                self.add(
                    "medium",
                    "bat_missing_app_python_exe",
                    "start script should expose APP_PYTHON_EXE for logging and preflight",
                    "start_portable.bat",
                )

        sh = self.read_text("start_portable.sh")
        if sh is not None:
            if "runtime_env/python/python" not in sh:
                self.add(
                    "medium",
                    "sh_not_using_embedded_python",
                    "start_portable.sh should reference runtime_env/python/python or clearly state Windows-only",
                    "start_portable.sh",
                )

    def check_forbidden_artifacts(self) -> None:
        excludes = _load_excludes()
        exact = excludes["exact"]
        parts_forbidden = excludes["parts"]
        top_level_forbidden = excludes["top_level_dirs"]
        suffixes_forbidden = excludes["suffixes"]
        forbidden: list[str] = []
        for name in self.reader.list_files():
            norm = name.replace("\\", "/").lstrip("/")
            if norm.startswith("runtime_env/"):
                continue
            parts = set(norm.split("/"))
            top_level = norm.split("/", 1)[0] if norm else ""
            if norm in exact:
                forbidden.append(norm)
                continue
            if top_level in top_level_forbidden:
                forbidden.append(norm)
                continue
            if parts.intersection(parts_forbidden):
                forbidden.append(norm)
                continue
            if norm.endswith(tuple(suffixes_forbidden)):
                forbidden.append(norm)
                continue
        self.summary["forbidden_artifact_count"] = len(forbidden)
        if forbidden:
            sample = ", ".join(forbidden[:20])
            self.add(
                "critical",
                "forbidden_artifacts_present",
                f"portable bundle contains forbidden artifacts: {sample}",
            )

    def check_repo_hygiene(self, repo: Path | None) -> None:
        if repo is None:
            return
        repo = repo.resolve()
        source_findings: list[str] = []
        checks = [
            repo / ".env",
            repo / ".venv",
            repo / "data" / "trading_system.db",
            repo / "data" / "trading_system.db-wal",
            repo / "data" / "trading_system.db-shm",
            repo / ".pytest_cache",
            repo / ".ruff_cache",
        ]
        for path in checks:
            if path.exists():
                source_findings.append(str(path.relative_to(repo)))
        self.summary["source_hygiene_findings"] = source_findings
        for item in source_findings:
            self.add(
                "medium",
                "source_local_artifact_present",
                f"source tree contains local artifact; keep it out of release: {item}",
                item,
            )

        csproj = repo / "tools" / "launcher" / "TradingSystemLauncher.csproj"
        if csproj.exists():
            text = csproj.read_text(encoding="utf-8", errors="ignore")
            required_pairs = {
                "PublishSingleFile": "true",
                "SelfContained": "true",
                "RuntimeIdentifier": "win-x64",
            }
            for key, expected in required_pairs.items():
                pattern = rf"<{key}>\s*{re.escape(expected)}\s*</{key}>"
                if not re.search(pattern, text, flags=re.IGNORECASE):
                    self.add(
                        "high",
                        "launcher_csproj_not_self_contained",
                        f"launcher csproj should contain <{key}>{expected}</{key}>",
                        str(csproj.relative_to(repo)),
                    )
        else:
            self.add(
                "medium",
                "launcher_csproj_missing",
                "launcher csproj missing; keep full launcher source or document start_portable.bat fallback",
                "tools/launcher/TradingSystemLauncher.csproj",
            )

    def run_smoke_if_possible(self, portable_root: Path | None) -> None:
        if not self.smoke or portable_root is None:
            return
        python_exe = portable_root / "runtime_env" / "python" / "python.exe"
        if os.name != "nt":
            self.add(
                "info",
                "smoke_skipped_non_windows",
                "smoke import test skipped because host is not Windows",
                str(python_exe),
            )
            return
        if not python_exe.exists():
            self.add(
                "high",
                "smoke_python_missing",
                "cannot run smoke test because bundled python.exe is missing",
                str(python_exe),
            )
            return
        code = "import " + ", ".join(SMOKE_IMPORTS) + "; print('portable import smoke ok')"
        env = os.environ.copy()
        env["APP_DISTRIBUTION_MODE"] = "portable"
        env["APP_BUNDLE_ROOT"] = str(portable_root)
        env["APP_PYTHON_EXE"] = str(python_exe)
        try:
            proc = subprocess.run(
                [str(python_exe), "-c", code],
                cwd=str(portable_root),
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            self.add(
                "high",
                "smoke_exception",
                f"smoke import test failed to start: {exc}",
                str(python_exe),
            )
            return
        self.summary["smoke_returncode"] = proc.returncode
        if proc.returncode != 0:
            self.add(
                "critical",
                "smoke_import_failed",
                f"import smoke failed: {proc.stderr[-1000:]}",
                str(python_exe),
            )

    def audit(self, *, repo: Path | None = None, portable_root: Path | None = None) -> Report:
        self.summary["file_count"] = len(self.reader.list_files())
        self.check_required_files()
        self.check_runtime_metadata()
        self.check_python_binaries()
        self.check_pth_and_site_packages()
        self.check_start_scripts()
        self.check_forbidden_artifacts()
        self.check_repo_hygiene(repo)
        self.run_smoke_if_possible(portable_root)

        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        failed = counts.get("critical", 0) > 0 or (self.strict and counts.get("high", 0) > 0)
        status = "fail" if failed else "pass"
        launcher = self.summary.get("launcher_present")
        summary_text = (
            f"status={status} | critical={counts.get('critical', 0)} | "
            f"high={counts.get('high', 0)} | medium={counts.get('medium', 0)} | "
            f"low={counts.get('low', 0)} | info={counts.get('info', 0)} | "
            f"launcher={'present' if launcher else 'missing'}"
        )
        return Report(
            status=status,
            strict=self.strict,
            source=self.reader.source_label,
            total_findings=len(self.findings),
            counts=counts,
            findings=[asdict(finding) for finding in self.findings],
            summary=self.summary,
            summary_text=summary_text,
        )


def choose_reader(portable_root: Path | None, zip_path: Path | None) -> BundleReader:
    if zip_path and zip_path.exists():
        return ZipBundleReader(zip_path)
    if portable_root and portable_root.exists():
        return DirBundleReader(portable_root)
    raise FileNotFoundError(
        "No portable bundle found. Provide --portable-root dist/portable_bundle or --zip dist/portable_bundle.zip."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify true-portable Windows release artifacts.")
    parser.add_argument(
        "--repo", type=Path, default=Path("."), help="Repository root for source hygiene checks."
    )
    parser.add_argument(
        "--portable-root",
        type=Path,
        default=Path("dist/portable_bundle"),
        help="Unpacked portable bundle root.",
    )
    parser.add_argument(
        "--zip",
        dest="zip_path",
        type=Path,
        default=None,
        help="Portable zip to verify. If present, zip verification is preferred.",
    )
    parser.add_argument(
        "--json-out", type=Path, default=None, help="Write JSON report to this path."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on critical or high findings. Without strict, only critical fails.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run import smoke test using bundled Python when possible.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        reader = choose_reader(args.portable_root, args.zip_path)
    except FileNotFoundError as exc:
        report = Report(
            status="fail",
            strict=args.strict,
            source="missing",
            total_findings=1,
            counts={"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0},
            findings=[asdict(Finding("critical", "bundle_missing", str(exc), None))],
            summary={},
        )
        payload = asdict(report)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return 1

    portable_root = (
        args.portable_root.resolve() if args.portable_root and args.portable_root.exists() else None
    )
    repo = args.repo.resolve() if args.repo else None
    auditor = Auditor(reader, strict=args.strict, smoke=args.smoke)
    report = auditor.audit(repo=repo, portable_root=portable_root)
    payload = asdict(report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
