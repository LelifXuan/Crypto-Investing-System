"""
Motion verification — motion token coverage, reduced-motion compliance, duration ladder.

Capability: P2-B (Motion Verification)
Analyzes CSS motion system for:
  1. Motion token usage coverage (which --dur-* / --ease-* variables are consumed)
  2. prefers-reduced-motion media query completeness
  3. Duration ladder correctness (dur-press < dur-hover < dur-elevate < dur-drawer)
  4. Infinite animations that must be disabled under reduced-motion
  5. Transition presence on interactive elements (button, card, link)
  6. All animations use tokenized timing (no hardcoded durations)

Usage:
  python tests/motion_verify.py                          # full verification
  python tests/motion_verify.py --show-unused-tokens     # print unused motion tokens
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import tinycss2

REPO_ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = REPO_ROOT / "app" / "static" / "styles.css"
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"

# Expected motion tokens
DUR_TOKENS = ["--dur-press", "--dur-hover", "--dur-elevate", "--dur-drawer"]
EASE_TOKENS = ["--ease-out", "--ease-in-out", "--ease-drawer"]
MOTION_ALIASES = ["--motion-fast", "--motion-hover"]
ALL_MOTION_TOKENS = DUR_TOKENS + EASE_TOKENS + MOTION_ALIASES

# Expected duration ladder ordering (values in ms)
DUR_LADDER_EXPECTED = {
    "--dur-press": 120,
    "--dur-hover": 180,
    "--dur-elevate": 240,
    "--dur-drawer": 320,
}


def parse_motion_tokens(css_text: str) -> dict:
    """
    Parse CSS for motion token definitions, usage, and reduced-motion handling.
    """
    # Extract :root block for token definitions
    root_block_match = re.search(r':root\s*\{([^}]+)\}', css_text, re.DOTALL)
    root_block = root_block_match.group(1) if root_block_match else ""

    # Extract all token definitions from :root
    token_defs = {}
    for m in re.finditer(r'(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);', root_block):
        token_defs[m.group(1)] = m.group(2).strip()

    # Extract var() references from full CSS
    var_refs = set(re.findall(r'var\((--[a-zA-Z0-9-]+)', css_text))

    # Extract transition/animation declarations
    transition_decls = re.findall(
        r'(?:transition|animation)\s*:\s*([^;]+);', css_text
    )

    # Find @media prefers-reduced-motion block
    reduced_motion_block = ""
    rm_match = re.search(
        r'@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
        css_text,
        re.DOTALL,
    )
    if rm_match:
        reduced_motion_block = rm_match.group(1)

    return {
        "token_defs": token_defs,
        "var_refs": var_refs,
        "transition_decls": transition_decls,
        "reduced_motion_block": reduced_motion_block,
    }


def verify_motion_system(css_text: str) -> dict:
    """Run all motion verification checks."""
    findings: list[dict] = []
    data = parse_motion_tokens(css_text)

    # 1. Motion token usage coverage
    motion_used = {}
    for token in ALL_MOTION_TOKENS:
        is_used = token in data["var_refs"]
        motion_used[token] = is_used
        if not is_used:
            # Check if it's defined in :root
            is_defined = token in data["token_defs"]
            if is_defined:
                findings.append({
                    "check": "unused-motion-token",
                    "severity": "WARN",
                    "detail": f"{token} is defined but never referenced",
                })

    used_count = sum(1 for v in motion_used.values() if v)
    total_motion = len(ALL_MOTION_TOKENS)

    # 2. Duration ladder verification
    dur_values = {}
    for token, expected_ms in DUR_LADDER_EXPECTED.items():
        defn = data["token_defs"].get(token, "")
        # Extract ms value
        ms_match = re.search(r'(\d+)ms', defn)
        if ms_match:
            dur_values[token] = int(ms_match.group(1))
        else:
            findings.append({
                "check": "duration-ladder",
                "severity": "WARN",
                "detail": f"{token} has no recognizable ms value: '{defn}'",
            })

    # Verify ordering: dur-press < dur-hover < dur-elevate < dur-drawer
    ladder_order = ["--dur-press", "--dur-hover", "--dur-elevate", "--dur-drawer"]
    for i in range(len(ladder_order) - 1):
        t1, t2 = ladder_order[i], ladder_order[i + 1]
        v1, v2 = dur_values.get(t1), dur_values.get(t2)
        if v1 and v2 and v1 >= v2:
            findings.append({
                "check": "duration-ladder",
                "severity": "FAIL",
                "detail": f"{t1} ({v1}ms) should be < {t2} ({v2}ms)",
            })

    # 3. prefers-reduced-motion completeness
    rm_block = data["reduced_motion_block"]
    if not rm_block:
        findings.append({
            "check": "reduced-motion",
            "severity": "FAIL",
            "detail": "No @media (prefers-reduced-motion: reduce) block found",
        })
    else:
        # Check if animations are disabled
        has_animation_disable = "animation" in rm_block and (
            "0.01ms" in rm_block or "none" in rm_block
        )
        has_transition_disable = "transition" in rm_block and (
            "0.01ms" in rm_block or "none" in rm_block
        )
        if not has_animation_disable:
            findings.append({
                "check": "reduced-motion",
                "severity": "WARN",
                "detail": "reduced-motion block may not disable all animations",
            })
        if not has_transition_disable:
            findings.append({
                "check": "reduced-motion",
                "severity": "WARN",
                "detail": "reduced-motion block may not disable all transitions",
            })

    # 4. Infinite animations check
    infinite_selectors = []
    # Find animation declarations with infinite
    for m in re.finditer(
        r'([^{}]*)\{[^}]*animation[^}]*iteration-count\s*:\s*infinite[^}]*\}',
        css_text,
    ):
        selector = m.group(1).strip()
        # Skip if it's inside the reduced-motion block
        if "prefers-reduced-motion" not in selector:
            infinite_selectors.append(selector[:60])

    if infinite_selectors:
        # Check if reduced-motion block disables them
        rm_disables_infinite = "iteration-count: none" in rm_block or "animation: none" in rm_block
        if not rm_disables_infinite:
            findings.append({
                "check": "infinite-animation",
                "severity": "WARN",
                "detail": f"{len(infinite_selectors)} infinite animations found; "
                          f"ensure reduced-motion disables them",
            })

    # 5. Hardcoded durations (not using tokens)
    hardcoded_durations = []
    for decl in data["transition_decls"]:
        # Check for hardcoded timing like "200ms" or "0.3s" without var()
        if re.search(r'\d+m?s', decl) and "var(" not in decl:
            hardcoded_durations.append(decl.strip()[:50])

    if hardcoded_durations:
        findings.append({
            "check": "hardcoded-duration",
            "severity": "WARN",
            "detail": f"{len(hardcoded_durations)} transitions use hardcoded timing",
        })

    # 6. Interactive element transitions
    interactive_selectors = ["button", "a", ".card", ".btn"]
    has_interactive_transition = False
    for sel in interactive_selectors:
        # Check if there's a transition on these selectors
        pattern = rf'{re.escape(sel)}\s*\{{[^}}]*transition'
        if re.search(pattern, css_text):
            has_interactive_transition = True
            break

    if not has_interactive_transition:
        findings.append({
            "check": "interactive-transition",
            "severity": "WARN",
            "detail": "No transitions found on interactive elements (button/a/card)",
        })

    # Summarize
    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")

    return {
        "motion_token_coverage": {
            "used": used_count,
            "total": total_motion,
            "ratio": round(used_count / total_motion, 2) if total_motion else 0,
            "details": motion_used,
        },
        "duration_ladder": {
            token: dur_values.get(token) for token in ladder_order
        },
        "reduced_motion_block_exists": bool(rm_block),
        "infinite_animation_count": len(infinite_selectors),
        "hardcoded_duration_count": len(hardcoded_durations),
        "findings": findings,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "verdict": "FAIL" if fail_count > 0 else "WARN" if warn_count > 0 else "PASS",
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Motion verification — token coverage, reduced-motion, duration ladder")
    p.add_argument("--show-unused-tokens", action="store_true", help="print unused motion tokens")
    args = p.parse_args(argv)

    css_text = CSS_FILE.read_text(encoding="utf-8")
    report = verify_motion_system(css_text)

    # Print summary
    print("=" * 60)
    print("MOTION VERIFICATION REPORT")
    print("=" * 60)

    cov = report["motion_token_coverage"]
    print(f"[Token Coverage] {cov['used']}/{cov['total']} motion tokens used ({cov['ratio']*100:.0f}%)")
    if args.show_unused_tokens:
        for token, used in cov["details"].items():
            if not used:
                print(f"  UNUSED: {token}")

    ladder = report["duration_ladder"]
    print(f"[Duration Ladder] " + " < ".join(
        f"{t}={v}ms" for t, v in ladder.items() if v
    ))

    print(f"[Reduced Motion]  {'present' if report['reduced_motion_block_exists'] else 'MISSING'}")
    print(f"[Infinite Anims]  {report['infinite_animation_count']}")
    print(f"[Hardcoded Dur]   {report['hardcoded_duration_count']}")
    print()

    if report["findings"]:
        print("Findings:")
        for f in report["findings"]:
            print(f"  [{f['severity']}] {f['check']}: {f['detail']}")
    else:
        print("No findings — motion system is clean.")

    print("=" * 60)
    print(f"verdict: {report['verdict']}")

    # Save report
    out_log = SCREENSHOT_DIR / "motion_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
