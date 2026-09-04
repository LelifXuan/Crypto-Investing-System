from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser):
    parser.addoption(
        "--acceptance",
        action="store_true",
        default=False,
        help="Require the configured browser backend before collecting release tests.",
    )


def require_acceptance_backend(base_url: str) -> None:
    """Preflight only; the Playwright gates still verify actual rendered pages."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise pytest.UsageError("Acceptance BASE_URL must be an HTTP(S) URL")
    try:
        with socket.create_connection(
            (parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)),
            timeout=2,
        ):
            pass
    except (OSError, ValueError) as error:
        raise pytest.UsageError(
            "Acceptance backend unavailable: start the owned verification instance first"
        ) from error


def pytest_sessionstart(session):
    if session.config.getoption("--acceptance"):
        require_acceptance_backend(os.getenv("BASE_URL", "http://127.0.0.1:8002"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if item.config.getoption("--acceptance") and report.skipped:
        reason = str(report.longrepr).lower()
        if any(
            text in reason
            for text in (
                "backend not running",
                "backend unavailable",
                "backend is not running",
            )
        ):
            report.outcome = "failed"
            report.longrepr = "Acceptance browser backend disappeared; skip is not permitted"


@pytest.fixture
def repository() -> SimpleNamespace:
    """Placeholder repository stand-in for tests that mock the loader entirely."""
    return SimpleNamespace()


@pytest.fixture
def base_url() -> str:
    """Base URL of the caller-owned verification backend."""
    return os.getenv("BASE_URL", "http://127.0.0.1:8002")
