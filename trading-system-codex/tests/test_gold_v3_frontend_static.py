"""Static assertions for gold V3 frontend module."""
from pathlib import Path

_GOLD_V3_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "gold_v3.js"


def _read() -> str:
    return _GOLD_V3_JS.read_text(encoding="utf-8")


class TestGoldV3ModuleExports:
    def test_module_exports_render_gold_v3(self):
        source = _read()
        assert "export async function renderGoldV3" in source or \
               "export function renderGoldV3" in source

    def test_module_exports_unmount(self):
        source = _read()
        assert "unmount" in source

    def test_uses_v3_api_methods(self):
        source = _read()
        assert "getGoldV3Allocation" in source


class TestGoldV3PageStructure:
    def test_renders_macro_panel(self):
        source = _read()
        assert "gold-v3-macro" in source

    def test_renders_spot_dca_section(self):
        source = _read()
        assert "gold-v3-spot" in source

    def test_renders_contract_section(self):
        source = _read()
        assert "gold-v3-contract" in source

    def test_renders_three_signal_lights(self):
        source = _read()
        assert "TIPS" in source or "实际利率" in source
        assert "DXY" in source or "美元" in source
        assert "VIX" in source or "波动" in source

    def test_renders_add_position_gate(self):
        source = _read()
        assert "macro_gate" in source or "宏观门禁" in source

    def test_renders_xaut_technicals(self):
        source = _read()
        assert "MA50" in source or "MA200" in source

    def test_renders_liquidity_shock_warning(self):
        source = _read()
        assert "liquidity_shock" in source or "流动性冲击" in source

    def test_does_not_reference_goldhub(self):
        source = _read()
        assert "goldhub" not in source.lower()
        assert "wgc" not in source.lower()
        assert "world_gold_council" not in source.lower()

    def test_does_not_reference_module_cards(self):
        source = _read()
        assert "module_cards" not in source
        assert "moduleCards" not in source
