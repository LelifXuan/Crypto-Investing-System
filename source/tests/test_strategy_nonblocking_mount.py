"""Regression guard: cold AI strategy calculation must not block SPA exits."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "static" / "pages" / "strategy" / "index.js").read_text(encoding="utf-8")


def test_strategy_mount_does_not_await_the_cold_scan() -> None:
    controller = SOURCE[SOURCE.index("return {", SOURCE.index("export async function renderStrategy")):]
    mount = controller[controller.index("mount: async"):controller.index("unmount: async")]
    assert "await scanPromise" not in mount
    assert "void scanPromise" in mount


def test_strategy_unmount_aborts_scan_and_detail_requests() -> None:
    controller = SOURCE[SOURCE.index("return {", SOURCE.index("export async function renderStrategy")):]
    unmount = controller[controller.index("unmount: async"):controller.index("pause: async")]
    assert "mounted = false" in unmount
    assert "activeController?.abort()" in unmount
    assert "detailLoadController?.abort()" in unmount
