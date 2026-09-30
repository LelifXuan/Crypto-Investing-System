"""P0-SEC-001: distribution artifacts must not carry private credentials.

INV-005 — No distributable application archive may contain private
credentials by default. These tests pin the packaging boundary itself
(builder source, filename gate, content-scan gate); the real-archive
verification is run by scripts/verify_portable_package.py at delivery time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_private_portable import (
    ALLOWED_ENV_BASENAMES,
    SecretGateError,
    _runtime_public_artifact,
    collect_secret_violations,
    credential_filename_violation,
    include_source,
    run_secret_gate,
)

BUILDER = Path(__file__).resolve().parents[1] / "scripts" / "build_private_portable.py"


def test_distribution_contains_no_env():
    source = BUILDER.read_text(encoding="utf-8")
    assert "Missing authorized .env" not in source
    assert "--include-authorized-env" not in source
    # Default builds contain no .env: the only assignment is guarded by the
    # owner-authorized opt-in flag and paired with the gate exemption.
    assert 'embed_local_env: bool = False' in source
    assert (
        'if embed_local_env:\n        env_path = root / "source/.env"' in source
    )
    assert 'allowed_names = {"source/.env"} if embed_local_env else None' in source
    assert '"contains_secrets": bool(embed_local_env)' in source
    assert not include_source("source/.env")
    assert not include_source("source/.env.local")
    assert not include_source("source/.env.production")
    for allowed in sorted(ALLOWED_ENV_BASENAMES):
        assert include_source(f"source/{allowed}"), allowed


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
    assert _runtime_public_artifact(
        "source/runtime_python/Lib/site-packages/certifi/cacert.pem"
    )
    assert not _runtime_public_artifact("source/app/services/secrets.py")
    assert not _runtime_public_artifact("source/conf/cacert.pem")
    assert not _runtime_public_artifact("source/runtime_python/Lib/site-packages/pkg/private.pem")
    assert "change[-_]?me" in BUILDER.read_text(encoding="utf-8")


def test_embed_local_env_is_explicit_owner_opt_in():
    """Owner decision 2026-09-30: the operator-created keys may be embedded on
    purpose — but only via the explicit flag, and the exemption is exactly
    source/.env. Default builds stay credential-free."""
    source = BUILDER.read_text(encoding="utf-8")
    assert '"source/.env"} if embed_local_env else None' in source
    assert '"embeds_local_env": bool(embed_local_env)' in source
    assert '"contains_secrets": bool(embed_local_env)' in source
    assert 'embed_local_env: bool = False' in source

    # With the authorization, .env itself passes; every other violation still
    # fires — the escape hatch must not become a blanket exemption.
    authorized = collect_secret_violations(
        ["source/.env", "source/conf/credentials.json"],
        lambda _: "JWT_SECRET_KEY=real-value",
        allowed_names={"source/.env"},
    )
    expected = [
        "source/conf/credentials.json: credential-like filename (credentials.json)"
    ]
    assert authorized == expected
    # Without authorization the same manifest still fails on both counts.
    unauthorized = collect_secret_violations(
        ["source/.env", "source/conf/credentials.json"],
        lambda _: "JWT_SECRET_KEY=real-value",
    )
    assert len(unauthorized) == 2
