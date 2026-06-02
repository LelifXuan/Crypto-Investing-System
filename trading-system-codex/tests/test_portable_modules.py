from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _run_parse_requirements(requirements_text: str) -> list[str]:
    """Run portable_modules.parse_requirements as a subprocess so the
    test does not need to import scripts/portable_modules.py directly.

    Writes the input to a temp file and passes the path as an argv so
    the subprocess cannot accidentally fall back to a different file.
    """

    import argparse
    import json
    import sys as _sys
    import tempfile

    input_path = PROJECT_ROOT / "dist" / ".test_requirements_input.txt"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(dedent(requirements_text).lstrip(), encoding="utf-8")

    driver = SCRIPTS_DIR / "_test_parse_requirements_driver.py"
    driver.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, r'{SCRIPTS_DIR}')\n"
        "from pathlib import Path\n"
        "from portable_modules import parse_requirements\n"
        "target = Path(sys.argv[1])\n"
        "print(json.dumps(parse_requirements(target)))\n",
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            [sys.executable, str(driver), str(input_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)},
        )
    finally:
        if driver.exists():
            driver.unlink()
    if completed.returncode != 0:
        raise AssertionError(
            f"parse_requirements failed: stderr={completed.stderr!r} stdout={completed.stdout!r}"
        )
    return json.loads(completed.stdout.strip())


def test_parse_requirements_handles_pin_versions() -> None:
    result = _run_parse_requirements(
        """
        fastapi==0.115.14
        uvicorn==0.34.3
        aiosqlite==0.21.0
        """
    )
    assert result == ["aiosqlite", "fastapi", "uvicorn"]


def test_parse_requirements_strips_extras_and_markers() -> None:
    result = _run_parse_requirements(
        """
        uvicorn[standard]==0.34.3
        greenlet==3.5.0 ; sys_platform == 'win32'
        """
    )
    assert result == ["greenlet", "uvicorn"]


def test_parse_requirements_canonicalises_known_aliases() -> None:
    result = _run_parse_requirements(
        """
        PyYAML==6.0.2
        python-dotenv==1.1.1
        python-multipart==0.0.20
        """
    )
    assert result == ["dotenv", "multipart", "yaml"]


def test_parse_requirements_skips_comments_and_blanks() -> None:
    result = _run_parse_requirements(
        """
        # top comment
        fastapi==0.115.14

        # mid comment
        uvicorn==0.34.3
        """
    )
    assert result == ["fastapi", "uvicorn"]


def test_parse_requirements_skips_urls_and_editable() -> None:
    result = _run_parse_requirements(
        """
        https://example.com/foo.whl
        -e git+https://example.com/repo.git#egg=foo
        fastapi==0.115.14
        """
    )
    assert result == ["fastapi"]


def test_parse_requirements_dedupes() -> None:
    result = _run_parse_requirements(
        """
        fastapi==0.115.14
        fastapi>=0.100
        uvicorn==0.34.3
        """
    )
    assert result == ["fastapi", "uvicorn"]


def test_parse_requirements_matches_actual_requirements_file() -> None:
    """Smoke test: parse the real requirements-portable.txt and check
    that the result covers the core fastapi/uvicorn stack plus has
    reasonable alias mappings.
    """

    result = _run_parse_requirements(
        (PROJECT_ROOT / "requirements-portable.txt").read_text(encoding="utf-8")
    )
    assert "fastapi" in result
    assert "uvicorn" in result
    assert "sqlalchemy" in result
    assert "yaml" in result  # PyYAML alias
    assert "dotenv" in result  # python-dotenv alias
    assert "multipart" in result  # python-multipart alias
