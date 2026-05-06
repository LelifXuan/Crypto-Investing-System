from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_structure_entry_uses_versioned_dynamic_import() -> None:
    source = (ROOT / "app/static/pages/structure/index.js").read_text(encoding="utf-8")
    assert 'from "../structure.js"' not in source
    assert "window.__ASSET_VERSION__" in source
    assert "import(`../structure.js${assetVersion}`)" in source


def test_router_asset_version_scans_static_and_templates() -> None:
    source = (ROOT / "app/web/router.py").read_text(encoding="utf-8")
    assert "rglob" in source
    assert '".js", ".css", ".html"' in source
    assert "技术指标" in source


def test_alerts_initial_load_has_fallback_shell() -> None:
    source = (ROOT / "app/static/pages/alerts.js").read_text(encoding="utf-8")
    assert "alerts:initial-load:error" in source
    assert "fallbackChipStructureCard" in source
    assert "告警列表暂不可用" in source


def test_knowledge_catalog_does_not_generate_template_body_text() -> None:
    source = (ROOT / "app/static/core/knowledge.js").read_text(encoding="utf-8")
    assert "常见误区是孤立使用" not in source
    assert "非公式性规则：结合系统上下文" not in source
    assert "readablePages" not in source


def test_market_event_text_normalizes_broken_quotes() -> None:
    module_path = ROOT / "app/static/pages/market_events.js"
    script = f"""
import {{ decodePossiblyBrokenText }} from 'file:///{module_path.as_posix()}';
const samples = [
  decodePossiblyBrokenText('Bitcoin�s dip and investor�s worries'),
  decodePossiblyBrokenText('Startup�s Database'),
  decodePossiblyBrokenText('claims as �wildly conspiratorial�'),
  decodePossiblyBrokenText('Robinhoodâ€™s Q1 revenue'),
];
console.log(JSON.stringify(samples));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(result.stdout) == [
        "Bitcoin’s dip and investor’s worries",
        "Startup’s Database",
        "claims as “wildly conspiratorial”",
        "Robinhood’s Q1 revenue",
    ]


def test_structure_overlay_uses_dynamic_viewport_and_profile_lines() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    assert "VIEWPORT_CONFIG" in source
    assert "calculateViewport" in source
    assert "聚焦形态" in source
    assert "结构背景" in source
    assert "完整快照" in source
    assert "buildLegendMarkup(availability)" in source
    assert "buildMarketProfileMarkup" in source
    assert "市场轮廓：${profileCount ? \"POC/VAH/VAL\" : \"未绘制\"}" in source
    assert 'if (item.system === "profile") return "";' in source
