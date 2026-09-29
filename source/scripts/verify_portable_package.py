"""Verify a built portable package without leaking secrets.

Checks (fail-closed):
1. the archive opens and PACKAGE-MANIFEST.json parses;
2. the secret gate runs over the full archive manifest (credential-like
   filenames + non-placeholder sensitive assignments in config-surface files);
3. structure: start.bat, embedded runtime, app entry, PACKAGE-README exist;
4. optional ``--extract``: unpacks to a temp dir (try/verify/finally), checks
   the key files on disk, and ALWAYS cleans up. Cleanup failure is reported as
   ``sensitive_cleanup_status = "failed"`` instead of being swallowed.

Secret values are never printed. Output: one JSON result on stdout;
exit code 0 only when every check passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_private_portable import (  # noqa: E402
    PREFIX,
    _runtime_public_artifact,
    collect_secret_violations,
    credential_filename_violation,
)

REQUIRED_MEMBERS = (
    "start.bat",
    "source/app/main.py",
    "source/runtime_python/python.exe",
    "PACKAGE-README.md",
    "PACKAGE-MANIFEST.json",
)


def _strip_prefix(name: str) -> str:
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


def verify(archive_path: Path, extract: bool) -> dict:
    result: dict = {
        "archive": str(archive_path),
        "secret_scan": "not_run",
        "violations": [],
        "structure": "not_run",
        "manifest_parse": "not_run",
        "extraction": "skipped",
        "sensitive_cleanup_status": "not_applicable",
        "ok": False,
    }
    if not archive_path.is_file():
        result["structure"] = f"archive missing: {archive_path}"
        return result
    with zipfile.ZipFile(archive_path) as archive:
        members = {name: _strip_prefix(name) for name in archive.namelist()}
        manifest_name = next(
            (name for name in members.values() if name == "PACKAGE-MANIFEST.json"), None
        )
        try:
            json.loads(archive.read(PREFIX + "PACKAGE-MANIFEST.json").decode("utf-8"))
            result["manifest_parse"] = "pass"
        except (KeyError, ValueError) as error:
            result["manifest_parse"] = f"fail: {type(error).__name__}"
            return result

        violations = collect_secret_violations(
            (name for name in members.values() if name != manifest_name),
            lambda name: archive.read(PREFIX + name).decode("utf-8", errors="ignore"),
        )
        result["violations"] = violations
        result["secret_scan"] = "fail" if violations else "pass"
        if violations:
            return result

        present = set(members.values())
        missing = [required for required in REQUIRED_MEMBERS if required not in present]
        result["structure"] = "pass" if not missing else f"fail: missing {missing}"
        if missing:
            return result

        if not extract:
            result["ok"] = True
            return result

        tmp = Path(tempfile.mkdtemp(prefix="cis_portable_verify_"))
        try:
            archive.extractall(tmp)
            flat = {
                path.relative_to(tmp).as_posix()
                for path in tmp.rglob("*")
                if path.is_file()
            }
            credential_files = sorted(
                name
                for name in flat
                if credential_filename_violation(name)
                and not _runtime_public_artifact(name)
            )
            if credential_files:
                result["extraction"] = f"fail: credential files on disk {credential_files[:10]}"
                return result
            bundle_root = tmp / PREFIX.rstrip("/")
            if not (bundle_root / "source/runtime_python/python.exe").is_file():
                result["extraction"] = "fail: embedded runtime missing after extract"
                return result
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            sidecar = archive_path.with_suffix(".zip.sha256")
            if sidecar.is_file():
                expected = sidecar.read_text(encoding="utf-8").split()[0]
                result["sha256_sidecar"] = "pass" if expected == digest else "fail"
            result["extraction"] = "pass"
            result["ok"] = True
        finally:
            try:
                shutil.rmtree(tmp)
                result["sensitive_cleanup_status"] = "clean"
            except OSError:
                result["sensitive_cleanup_status"] = "failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--extract", action="store_true", help="verify on-disk layout")
    args = parser.parse_args()
    result = verify(args.archive, extract=args.extract)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
