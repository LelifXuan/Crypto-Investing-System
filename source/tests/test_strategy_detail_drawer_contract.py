"""Static guards for the strategy detail drawer (ui-audit 2026-09-04 P1#2).

Audit findings being pinned:
- Drawer top:0 sat under the 64px global topbar — the "返回扫描" button
  was invisible (guideline §5.2 topbar avoidance).
- aria-modal="true" but no focus containment (§10 dialog lifecycle).
- Internal scrollWidth (2482px) exceeded clientWidth (1918px) — long
  trigger sentences and audit tables spilled horizontally (§11).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
PANEL = (ROOT / "app/static/pages/strategy/renderDetailPanel.js").read_text(encoding="utf-8")


def test_drawer_starts_below_topbar() -> None:
    idx = STYLES.index(".strategy-detail-panel {")
    block = STYLES[idx:STYLES.index("}", idx)]
    assert "top: var(--topbar-height, 64px)" in block
    assert "calc(100vh - var(--topbar-height, 64px))" in STYLES[idx:idx + 600]


def test_drawer_body_clips_horizontal_overflow() -> None:
    idx = STYLES.index(".strategy-detail-body {")
    tail = STYLES[idx:idx + 900]
    assert "overflow-x: clip" in tail
    assert "overflow-wrap: anywhere" in tail


def test_dialog_implements_focus_lifecycle() -> None:
    assert 'panel.setAttribute("aria-modal", "true")' in PANEL
    assert '(backBtn || panel).focus({ preventScroll: true })' in PANEL
    assert 'if (e.key !== "Tab") return' in PANEL
    assert "document.removeEventListener(\"keydown\", tabHandler)" in PANEL
    assert "focusOrigin?.isConnected" in PANEL


def test_drawer_title_uses_cell_timeframe_direction() -> None:
    """抽屉标题必须报所点格子自身周期的方向，而非全局 4H 决策方向。

    回归：HYPE·1w（SHORT）点开后标题写"做空"，下方却是 4H 计划价位
    （96.90–97.29 → TP 89.86），周线自己的 TP1 59.03 藏在 bundle 里。
    标题与价位来自两个周期却不声明，即使用户看到 TP 也会误以为是
    周线目标 ("96 看到 89 不是搞笑吗")。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "app/static/pages/strategy/renderDetailPanel.js"
    ).read_text(encoding="utf-8")
    assert "timeframe_stack" in src, "标题必须从 timeframe_stack 取本格方向"
    assert "cellNode" in src or "cellDir" in src
    # 格子方向与决策方向不一致时必须有解释（title 属性或等效说明）
    assert "4H" in src and ("title" in src)
