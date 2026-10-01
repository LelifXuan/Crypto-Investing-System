"""Private portable bundles require the operator's exact local config.

The exemption covers only source/.env; other credential files still fail.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_private_portable import (
    ALLOWED_ENV_BASENAMES,
    PREFIX,
    SecretGateError,
    _runtime_public_artifact,
    build,
    collect_secret_violations,
    credential_filename_violation,
    include_source,
    run_secret_gate,
)
from scripts.verify_portable_package import verify

BUILDER = Path(__file__).resolve().parents[1] / "scripts" / "build_private_portable.py"


def test_private_portable_requires_embedded_env():
    source = BUILDER.read_text(encoding="utf-8")
    assert 'env_path = root / "source/.env"' in source
    assert 'files["source/.env"] = env_path' in source
    assert 'allowed_names = {"source/.env"}' in source
    assert '"contains_secrets": True' in source
    assert '"embeds_local_env": True' in source
    assert 'assert archive.read(PREFIX + "source/.env") == env_path.read_bytes()' in source
    assert "Missing embedded source\\.env" in source
    assert "NO CREDENTIALS INCLUDED" not in source
    assert not include_source("source/.env")
    assert not include_source("source/.env.local")
    assert not include_source("source/.env.production")
    for allowed in sorted(ALLOWED_ENV_BASENAMES):
        assert include_source(f"source/{allowed}"), allowed


def test_private_portable_missing_env_fails_before_runtime_work(tmp_path: Path):
    with pytest.raises(RuntimeError, match="Missing non-empty source/.env"):
        build(tmp_path, tmp_path / "portable.zip")


def test_distribution_contains_no_private_credentials():
    for name in [
        "source/.env",
        "source/.env.production",
        "conf/credentials.json",
        "conf/secrets.yaml",
        "certs/server.pem",
        "certs/server.key",
        "certs/store.pfx",
        "secrets",
    ]:
        assert credential_filename_violation(name), name
    for name in [
        "source/.env.example",
        "source/.env.template",
        "README.md",
        "source/app/main.py",
        "config/settings.toml",
        "reports/report.json",
        "start.bat",
    ]:
        assert credential_filename_violation(name) is None, name


def test_distribution_secret_scan_gate():
    clean = (
        "FRED_API_KEY=\n"
        "JWT_SECRET_KEY=CHANGE_ME\n"
        "TIINGO_API_KEY=your-key-here\n"
        "GLASSNODE_API_KEY=\n"
    )
    assert collect_secret_violations(["conf/.env.example"], lambda _: clean) == []
    dirty = (
        "FRED_API_KEY=abc123def\n"
        '"TENCENT_TMT_SECRET_ID": "AKIDz8qr"\n'
        "BOOTSTRAP_ADMIN_PASSWORD=Sn7!vortex\n"
    )
    violations = collect_secret_violations(["conf/.env.example"], lambda _: dirty)
    assert len(violations) == 3
    for violation in violations:
        assert "abc123def" not in violation
        assert "AKIDz8qr" not in violation
        assert "Sn7!vortex" not in violation
    with pytest.raises(SecretGateError):
        run_secret_gate(["conf/.env.example"], lambda _: dirty)
    filename_only = collect_secret_violations(["source/.env"], lambda _: "")
    assert any(".env" in violation for violation in filename_only)

    # The gate must run on the staged list AND on the written archive.
    assert BUILDER.read_text(encoding="utf-8").count("run_secret_gate(") >= 2


def test_gate_allowlist_scoped_to_embedded_runtime():
    # Public runtime artifacts are exempt only inside runtime_python/; the same
    # basenames anywhere else (e.g. application source) must stay violations.
    assert _runtime_public_artifact("source/runtime_python/Lib/secrets.py")
    assert _runtime_public_artifact("source/runtime_python/Lib/site-packages/certifi/cacert.pem")
    assert not _runtime_public_artifact("source/app/services/secrets.py")
    assert not _runtime_public_artifact("source/conf/cacert.pem")
    assert not _runtime_public_artifact("source/runtime_python/Lib/site-packages/pkg/private.pem")
    assert "change[-_]?me" in BUILDER.read_text(encoding="utf-8")


def test_embedded_env_exemption_is_exact_path():
    """The operator's config is allowed without exempting other credentials."""
    source = BUILDER.read_text(encoding="utf-8")
    assert 'allowed_names = {"source/.env"}' in source

    # The exact path passes; every other violation still fires.
    authorized = collect_secret_violations(
        ["source/.env", "source/conf/credentials.json"],
        lambda _: "JWT_SECRET_KEY=real-value",
        allowed_names={"source/.env"},
    )
    expected = ["source/conf/credentials.json: credential-like filename (credentials.json)"]
    assert authorized == expected
    # Without the exact exemption the same manifest fails on both counts.
    unauthorized = collect_secret_violations(
        ["source/.env", "source/conf/credentials.json"],
        lambda _: "JWT_SECRET_KEY=real-value",
    )
    assert len(unauthorized) == 2


def _fixture_archive(
    path: Path,
    *,
    include_env: bool = True,
    bad_digest: bool = False,
    extra_credential: bool = False,
) -> None:
    files = {
        "start.bat": b"@echo off\n",
        "source/app/main.py": b"",
        "source/runtime_python/python.exe": b"fixture",
        "PACKAGE-README.md": b"fixture",
    }
    if include_env:
        files["source/.env"] = b"FIXTURE_API_KEY=fixture-only\n"
    if extra_credential:
        files["source/conf/credentials.json"] = b"{}"
    digests = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if bad_digest:
        digests["source/.env"] = "0" * 64
    manifest = {
        "contains_secrets": True,
        "embeds_local_env": True,
        "files": digests,
    }
    with ZipFile(path, "w") as archive:
        for name, value in files.items():
            archive.writestr(PREFIX + name, value)
        archive.writestr(PREFIX + "PACKAGE-MANIFEST.json", json.dumps(manifest))


def test_embedded_env_portable_extract_verification(tmp_path: Path):
    archive = tmp_path / "valid.zip"
    _fixture_archive(archive)
    result = verify(archive, extract=True)
    assert result["ok"] is True
    assert result["secret_scan"] == "pass"
    assert result["extraction"] == "pass"
    assert result["sensitive_cleanup_status"] == "clean"


@pytest.mark.parametrize("case", ["missing", "digest", "extra"])
def test_portable_rejects_incomplete_or_extra_credentials(tmp_path: Path, case: str):
    archive = tmp_path / f"{case}.zip"
    _fixture_archive(
        archive,
        include_env=case != "missing",
        bad_digest=case == "digest",
        extra_credential=case == "extra",
    )
    result = verify(archive, extract=True)
    assert result["ok"] is False
    assert result["structure"] != "pass" or result["secret_scan"] == "fail"
