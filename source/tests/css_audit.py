"""
CSS Audit — dead code detection, token coverage, hardcoded color scan.

Capability: P0-B (CSS Audit)
Analyzes styles.css for:
  1. Dead CSS rules — selectors declared but never referenced in JS/HTML
  2. Unused custom properties — :root variables never referenced via var()
  3. Orphan class references — classes used in JS/HTML but not defined in CSS
  4. Hardcoded colors — #hex / rgb() / hsl() values that bypass design tokens
  5. Token coverage — which :root variables are actually consumed

Incremental dead-code gate (baseline mode):
  The repo carries a large *known* dead-selector debt from past page
  refactors (2026-08-11 audit: ~484 classes, verified accurate by DOM
  sampling). A plain ratio gate therefore FAILs permanently and becomes
  noise. Baseline mode records the current dead set in
  tests/css_audit_baseline.json and only FAILs when NEW dead selectors
  appear. Rebase after each cleanup batch to lower the debt:
      python tests/css_audit.py --rebase

Usage:
  python tests/css_audit.py                          # full audit (incremental gate)
  python tests/css_audit.py --show-dead              # print dead selector list
  python tests/css_audit.py --show-hardcoded         # print hardcoded colors
  python tests/css_audit.py --rebase                 # record current dead set as baseline
  python tests/css_audit.py --threshold-dead 0.30    # absolute ratio fail threshold (no-baseline fallback)
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import tinycss2

REPO_ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = REPO_ROOT / "app" / "static" / "styles.css"
STATIC_DIR = REPO_ROOT / "app" / "static"
TEMPLATES_DIR = REPO_ROOT / "app" / "templates"
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
# 增量门禁基线：记录"已知存量死类"，只对新增死类 FAIL（见模块 docstring）
BASELINE_FILE = REPO_ROOT / "tests" / "css_audit_baseline.json"


def load_baseline() -> set[str] | None:
    """Return the recorded dead-selector baseline set, or None if absent."""
    if not BASELINE_FILE.exists():
        return None
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return set(data.get("dead_selectors", []))


def save_baseline(dead: set[str], ratio: float, total: int) -> None:
    """Persist the current dead set as the new baseline (after a cleanup batch)."""
    payload = {
        "recorded_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "dead_selectors": sorted(dead),
        "dead_count": len(dead),
        "dead_ratio": round(ratio, 4),
        "total_selectors": total,
        "note": "增量门禁基线：只对超过此集合的新增死类 FAIL。清理完一批后运行 --rebase 下调。",
    }
    BASELINE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_css_rules(css_text: str) -> dict:
    """
    Parse CSS with tinycss2.
    Returns:
      - selectors: set of all selector class names (e.g., '.card', '.btn-primary')
      - custom_props: dict of {prop_name: value} from :root
      - var_references: set of all var(--xxx) references
      - hardcoded_colors: list of (line_context, color_value) for non-token colors
      - total_rules: number of qualified rules
    """
    selectors: set[str] = set()
    custom_props: dict[str, str] = {}
    var_references: set[str] = set()
    hardcoded_colors: list[tuple[str, str]] = []
    total_rules = 0

    # Color patterns that indicate hardcoded values (not inside var() or token defs)
    hex_color_re = re.compile(r'#([0-9a-fA-F]{3,8})\b')
    rgb_color_re = re.compile(r'rgba?\([^)]+\)')
    hsl_color_re = re.compile(r'hsla?\([^)]+\)')

    # Parse stylesheet
    stylesheet = tinycss2.parse_stylesheet(css_text, skip_comments=True)

    in_root_block = False
    for rule in stylesheet:
        # Track :root block for custom properties
        if rule.type == "qualified-rule":
            # Check if this is inside :root (heuristic: look at prelude)
            prelude_str = tinycss2.serialize(rule.prelude)
            if ":root" in prelude_str:
                in_root_block = True
                total_rules += 1
                # Extract custom properties from declarations
                declarations = tinycss2.parse_declaration_list(rule.content)
                for decl in declarations:
                    if decl.type == "declaration" and decl.name.startswith("--"):
                        custom_props[decl.name] = tinycss2.serialize(decl.value).strip()
                continue
            else:
                in_root_block = False

            total_rules += 1

            # Extract class selectors from prelude
            prelude_str = tinycss2.serialize(rule.prelude)
            # Find all .class-name selectors
            class_matches = re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', prelude_str)
            for cls in class_matches:
                selectors.add(f".{cls}")

            # Extract var() references from declarations
            if rule.content:
                decl_str = tinycss2.serialize(rule.content)
                var_matches = re.findall(r'var\((--[a-zA-Z0-9_-]+)', decl_str)
                var_references.update(var_matches)

                # Detect hardcoded colors (only outside :root)
                if not in_root_block:
                    for m in hex_color_re.finditer(decl_str):
                        ctx_start = max(0, m.start() - 40)
                        ctx = decl_str[ctx_start:m.end()]
                        hardcoded_colors.append((ctx, m.group(0)))
                    for m in rgb_color_re.finditer(decl_str):
                        ctx_start = max(0, m.start() - 40)
                        ctx = decl_str[ctx_start:m.end()]
                        hardcoded_colors.append((ctx, m.group(0)))
                    for m in hsl_color_re.finditer(decl_str):
                        ctx_start = max(0, m.start() - 40)
                        ctx = decl_str[ctx_start:m.end()]
                        hardcoded_colors.append((ctx, m.group(0)))

        elif rule.type == "at-rule":
            # Handle @media blocks — extract nested rules
            if rule.content:
                nested_css = tinycss2.serialize(rule.content)
                # Recursively extract var refs and colors from nested blocks
                var_matches = re.findall(r'var\((--[a-zA-Z0-9_-]+)', nested_css)
                var_references.update(var_matches)

    return {
        "selectors": selectors,
        "custom_props": custom_props,
        "var_references": var_references,
        "hardcoded_colors": hardcoded_colors,
        "total_rules": total_rules,
    }


def scan_js_html_references() -> tuple[set[str], set[str]]:
    """
    Scan all JS and HTML files for class name references.
    Returns (referenced_classes, referenced_vars).
    """
    referenced_classes: set[str] = set()
    referenced_vars: set[str] = set()

    # Patterns to find class references in JS/HTML
    class_patterns = [
        re.compile(r'class\s*=\s*["\']([^"\']+)["\']'),  # class="..."
        re.compile(r'className\s*=\s*["\']([^"\']+)["\']'),  # className="..."
        re.compile(r'classList\.(?:add|remove|toggle)\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'querySelector(?:All)?\(\s*["\']\.([a-zA-Z][a-zA-Z0-9_-]+)'),
        re.compile(r'getElementsByClassName\(\s*["\']([^"\']+)["\']'),
        re.compile(r'class_name\s*=\s*["\']([^"\']+)["\']'),
    ]

    var_pattern = re.compile(r'var\((--[a-zA-Z0-9_-]+)')

    files_to_scan = []
    # JS files in static
    for ext in ["*.js"]:
        files_to_scan.extend(STATIC_DIR.rglob(ext))
    # HTML templates
    for ext in ["*.html"]:
        files_to_scan.extend(TEMPLATES_DIR.rglob(ext))

    for fpath in files_to_scan:
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        # Find class references
        for pat in class_patterns:
            for m in pat.finditer(text):
                # Some patterns capture space-separated class lists
                classes = m.group(1).split()
                for cls in classes:
                    if cls.startswith("."):
                        cls = cls[1:]
                    if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', cls):
                        referenced_classes.add(f".{cls}")

        # Find var() references
        for m in var_pattern.finditer(text):
            referenced_vars.add(m.group(1))

    return referenced_classes, referenced_vars


def run_audit(
    show_dead: bool = False,
    show_hardcoded: bool = False,
    threshold_dead_ratio: float = 0.30,
) -> dict:
    """Run the full CSS audit and return a report dict."""
    css_text = CSS_FILE.read_text(encoding="utf-8")

    # Parse CSS
    css_data = parse_css_rules(css_text)

    # Scan JS/HTML references
    ref_classes, ref_vars = scan_js_html_references()

    # 1. Dead CSS: selectors in CSS but not referenced in JS/HTML
    # Note: this is conservative — some selectors may be used dynamically
    # or via concatenation. We report them but mark as "suspected-dead".
    css_selectors = css_data["selectors"]
    dead_selectors = css_selectors - ref_classes
    # Filter out pseudo-elements and common dynamic patterns
    dead_filtered = set()
    for sel in dead_selectors:
        # Keep selectors that are likely used (contain common patterns)
        cls_name = sel.lstrip(".")
        # Skip if it's a state class (is-, has-, data-, js-, etc.)
        if cls_name.startswith(("is-", "has-", "js-", "data-")):
            continue
        dead_filtered.add(sel)

    dead_ratio = len(dead_filtered) / max(len(css_selectors), 1)

    # 增量门禁：存在基线时，存量死类是"已知债务"，只对新增死类 FAIL；
    # 无基线时回退到绝对比例阈值（旧行为）。
    baseline = load_baseline()
    if baseline is not None:
        new_dead = dead_filtered - baseline
        dead_verdict = "FAIL" if new_dead else "PASS"
        dead_report = {
            "count": len(dead_filtered),
            "ratio": round(dead_ratio, 3),
            "baseline_count": len(baseline),
            "new_dead_count": len(new_dead),
            "new_dead_samples": sorted(new_dead)[:50],
            "verdict": dead_verdict,
            "mode": "incremental",
        }
    else:
        dead_verdict = (
            "FAIL"
            if dead_ratio > threshold_dead_ratio
            else "WARN"
            if dead_ratio > threshold_dead_ratio * 0.7
            else "PASS"
        )
        dead_report = {
            "count": len(dead_filtered),
            "ratio": round(dead_ratio, 3),
            "verdict": dead_verdict,
            "samples": sorted(list(dead_filtered))[:50],
            "mode": "absolute",
        }

    # 2. Unused custom properties
    all_custom_props = set(css_data["custom_props"].keys())
    css_var_refs = css_data["var_references"]
    all_var_refs = css_var_refs | ref_vars
    unused_props = all_custom_props - all_var_refs

    # 3. Orphan references: classes in JS/HTML but not in CSS
    orphan_classes = ref_classes - css_selectors
    # Filter out likely framework/utility classes
    orphan_filtered = set()
    for cls in orphan_classes:
        cls_name = cls.lstrip(".")
        # Skip common non-project prefixes
        if cls_name.startswith(("cd-", "js-", "wp-", "fb-")):
            continue
        orphan_filtered.add(cls)

    # 4. Hardcoded colors
    hardcoded = css_data["hardcoded_colors"]
    # Deduplicate by color value
    unique_colors = {}
    for ctx, color in hardcoded:
        if color not in unique_colors:
            unique_colors[color] = ctx

    # Build report
    report = {
        "css_file": str(CSS_FILE.relative_to(REPO_ROOT)),
        "css_size_kb": round(len(css_text.encode("utf-8")) / 1024, 1),
        "total_rules": css_data["total_rules"],
        "total_selectors": len(css_selectors),
        "total_custom_props": len(all_custom_props),
        "dead_selectors": dead_report,
        "unused_custom_props": {
            "count": len(unused_props),
            "samples": sorted(list(unused_props))[:30],
        },
        "orphan_class_refs": {
            "count": len(orphan_filtered),
            "samples": sorted(list(orphan_filtered))[:30],
        },
        "hardcoded_colors": {
            "count": len(unique_colors),
            "unique_values": sorted(list(unique_colors.keys()))[:40],
            "verdict": "WARN" if len(unique_colors) > 20 else "PASS",
        },
        "token_coverage": {
            "total": len(all_custom_props),
            "referenced_in_css": len(css_var_refs & all_custom_props),
            "referenced_in_js_html": len(ref_vars & all_custom_props),
            "total_referenced": len(all_var_refs & all_custom_props),
            "coverage_ratio": round(
                len(all_var_refs & all_custom_props) / max(len(all_custom_props), 1), 3
            ),
        },
    }

    # Print summary
    print("=" * 60)
    print("CSS AUDIT REPORT")
    print("=" * 60)
    print(f"File: {report['css_file']} ({report['css_size_kb']} KB)")
    print(f"Total rules: {report['total_rules']}")
    print(f"Total selectors: {report['total_selectors']}")
    print(f"Total custom properties: {report['total_custom_props']}")
    print()
    ds = report["dead_selectors"]
    if ds["mode"] == "incremental":
        print(f"[Dead Selectors] {ds['count']} total ({ds['ratio']*100:.1f}%) — "
              f"{ds['baseline_count']} known debt, {ds['new_dead_count']} NEW — {ds['verdict']}")
    else:
        print(f"[Dead Selectors] {ds['count']} suspected-dead "
              f"({ds['ratio']*100:.1f}%) — {ds['verdict']}")
    print(f"[Unused Props]   {report['unused_custom_props']['count']} unused")
    print(f"[Orphan Refs]    {report['orphan_class_refs']['count']} classes in JS/HTML not in CSS")
    print(f"[Hardcoded Colors] {report['hardcoded_colors']['count']} unique values — {report['hardcoded_colors']['verdict']}")
    print(f"[Token Coverage] {report['token_coverage']['coverage_ratio']*100:.1f}% "
          f"({report['token_coverage']['total_referenced']}/{report['token_coverage']['total']})")
    print("=" * 60)

    if show_dead:
        ds = report["dead_selectors"]
        shown = ds.get("new_dead_samples") if ds["mode"] == "incremental" else ds.get("samples", [])
        label = "New Dead Selectors (first 50)" if ds["mode"] == "incremental" else "Suspected Dead Selectors (first 50)"
        if shown:
            print(f"\n--- {label} ---")
            for sel in shown:
                print(f"  {sel}")

    if show_hardcoded and unique_colors:
        print("\n--- Hardcoded Colors (first 40) ---")
        for color in sorted(list(unique_colors.keys()))[:40]:
            print(f"  {color}")

    return report


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="CSS Audit — dead code, token coverage, hardcoded colors")
    p.add_argument("--show-dead", action="store_true", help="print dead selector list")
    p.add_argument("--show-hardcoded", action="store_true", help="print hardcoded color list")
    p.add_argument(
        "--rebase",
        action="store_true",
        help="record the current dead-selector set as the new baseline (call after a cleanup batch)",
    )
    p.add_argument(
        "--threshold-dead",
        type=float,
        default=0.30,
        help="Dead selector ratio fail threshold when no baseline exists (default: 0.30)",
    )
    args = p.parse_args(argv)

    if args.rebase:
        # 单独跑 rebase：只重算 dead 集合并固化为新基线，不参与增量 FAIL。
        css_text = CSS_FILE.read_text(encoding="utf-8")
        data = parse_css_rules(css_text)
        ref_classes, _ = scan_js_html_references()
        dead = set()
        for sel in data["selectors"] - ref_classes:
            if not sel.lstrip(".").startswith(("is-", "has-", "js-", "data-")):
                dead.add(sel)
        ratio = len(dead) / max(len(data["selectors"]), 1)
        save_baseline(dead, ratio, len(data["selectors"]))
        print(f"baseline rebased: {len(dead)} dead selectors recorded -> {BASELINE_FILE.relative_to(REPO_ROOT)}")
        return 0

    report = run_audit(
        show_dead=args.show_dead,
        show_hardcoded=args.show_hardcoded,
        threshold_dead_ratio=args.threshold_dead,
    )

    # Save report
    out_log = SCREENSHOT_DIR / "css_audit_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport saved: {out_log.relative_to(REPO_ROOT)}")

    # Exit code based on verdict (incremental mode FAILs only on NEW dead selectors)
    dead_verdict = report["dead_selectors"]["verdict"]
    if dead_verdict == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
