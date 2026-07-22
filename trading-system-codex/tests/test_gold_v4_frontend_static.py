"""Static assertions for gold V4 frontend module."""
from pathlib import Path

_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "gold_v4.js"

def _read(): return _JS.read_text(encoding="utf-8")

class TestGoldV4Exports:
    def test_exports_renderGoldV4(self):
        assert "export async function renderGoldV4" in _read()
    def test_exports_unmount(self):
        assert "unmount" in _read()

class TestGoldV4Structure:
    def test_uses_card_class(self): assert 'class="card' in _read()
    def test_uses_eyebrow_class(self): assert 'eyebrow' in _read()
    def test_uses_chip_class(self): assert 'chip' in _read()
    def test_uses_hero_card(self): assert 'hero-card' in _read()
    def test_no_emoji(self):
        src = _read()
        for emoji in ['🟢','🔴','🟡','⚪','✅','❌']:
            assert emoji not in src, f"emoji {emoji} found"
    def test_no_goldhub_reference(self):
        src = _read().lower()
        assert 'goldhub' not in src
        assert 'wgc' not in src
    def test_no_module_cards(self):
        assert 'module_cards' not in _read()
    def test_no_v3_namespace(self):
        assert 'gold-v3-' not in _read()
