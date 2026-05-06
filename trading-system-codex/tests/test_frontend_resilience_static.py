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
    assert "状态置信" in source
    assert "盘口执行质量" in source
    assert "交易触发状态" in source
    assert "为什么当前不建议开多合约" not in source
    assert "合约开多条件检查" not in source
    assert "renderFuturesGateChecks" not in source
    assert "alert-chip-primary-card" in source
    assert "alert-chip-score-strip" in source
    assert "alert-chip-position-grid" in source
    assert "localizeExplainText" in source


def test_alert_chip_layout_avoids_sparse_fixed_metric_grid() -> None:
    source = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert ".alert-chip-primary-card" in source
    assert ".alert-chip-score-strip" in source
    assert ".alert-chip-position-grid" in source
    chip_metrics = source.split(".alert-chip-metrics", 1)[1].split("}", 1)[0]
    assert "repeat(6" not in chip_metrics
    assert ".alert-chip-gate-list" not in source
    assert ".alert-chip-gate-row" not in source


def test_structure_price_line_is_visually_subdued() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    expected = 'price: { label: "价格", color: "rgba(22, 35, 43, 0.58)", dash: "", width: 2.45 }'
    assert expected in source


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
  decodePossiblyBrokenText('Bitcoin\\uFFFDs dip and investor\\uFFFDs worries'),
  decodePossiblyBrokenText('Startup\\u25A1s Database'),
  decodePossiblyBrokenText('claims as \\uFFFDwildly conspiratorial\\uFFFD'),
  decodePossiblyBrokenText('Robinhood\\uFFFDs Q1 revenue'),
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
