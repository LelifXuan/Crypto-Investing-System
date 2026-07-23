from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_audit_catches_forbidden_text(tmp_path):
    test_file = tmp_path / "test_op_file.py"
    test_file.write_text(
        "print('若综合仍偏多，说明其他系统仍在抵消该负面信号。')",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audit_user_facing_text.py")],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert "FAIL" in output or "failures" in output.lower()


def test_audit_success_on_clean_text(tmp_path):
    test_file = tmp_path / "test_clean.py"
    test_file.write_text(
        "经典图形已跌破下沿，局部结构转弱。系统已将多头执行权限降级为仅观察。",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audit_user_facing_text.py")],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert "FAIL" not in output or "0 failures" in output
