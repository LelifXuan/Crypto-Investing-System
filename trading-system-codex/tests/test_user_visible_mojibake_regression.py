from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAD_TOKENS = ("\u00c3", "\u00c2", "\u00e7\u00b8", "????", "\ufffd")
CHECK_FILES = [
    "app/services/decision/multi_timeframe.py",
    "app/services/portfolio/rotation.py",
    "app/services/chip_structure_decision_policy.py",
    "app/services/divergence.py",
    "app/services/market_data_bundle.py",
    "app/static/pages/alerts.js",
]


def test_user_visible_strings_do_not_contain_mojibake_tokens() -> None:
    offenders = []
    for rel in CHECK_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in BAD_TOKENS:
            if token in text:
                offenders.append(f"{rel}:{token}")
    assert not offenders, f"Mojibake tokens found: {offenders}"
