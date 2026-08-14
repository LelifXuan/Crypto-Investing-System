from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def repository() -> SimpleNamespace:
    """Placeholder repository stand-in for tests that mock the loader entirely."""
    return SimpleNamespace()


@pytest.fixture
def base_url() -> str:
    """Base URL for the running backend (use existing uvicorn process)."""
    return os.getenv("BASE_URL", "http://127.0.0.1:8002")
