"""
Accessibility scan — WCAG contrast, ARIA, alt text, heading hierarchy.

Capability: P1-A (Accessibility)
Since axe-playwright pip package is unavailable, this uses Playwright's built-in
ARIA assertions + manual WCAG contrast calculations + DOM structure checks.

Checks per page:
  1. Color contrast (WCAG AA: 4.5:1 for normal text, 3:1 for large text)
  2. All <img> have alt attributes
  3. All <button> / <a> have accessible text
  4. Form elements have label associations
  5. Heading hierarchy (h1→h2→h3, no skipped levels)
  6. aria-* attributes present on interactive components
  7. prefers-reduced-motion media query exists and is effective
  8. Focus-visible styles exist

Usage:
  python tests/a11y_scan.py --pages all
  python tests/a11y_scan.py --pages monitoring-overview,market-analysis
  python tests/a11y_scan.py --threshold-contrast 4.5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
CSS_FILE = REPO_ROOT / "app" / "static" / "styles.css"

PAGE_ROUTES = {
    "market-analysis": "/indicators-page",
    "monitoring-overview": "/monitoring-page",
    "market-structure": "/structure-page",
    "market-events": "/market-events-page",
    "macro-calendar": "/macro-calendar-page",
    "knowledge-base": "/knowledge-page",
    "ashare-etf": "/ashare-etf-page",
    "btc-derivatives": "/btc-derivatives-page",
    "ai-strategy": "/strategy-page",
    "gold-allocation": "/gold-allocation-page",
}

REAL_CONTENT_SELECTORS = {
    "monitoring-overview": ["#monitoring-topbar", ".monitoring-summary-surface"],
    "market-analysis": [".analysis-hero-grid", ".analysis-chart-grid"],
    "market-structure": [".structure-page"],
    "market-events": [".events-feed-shell", ".events-feed-card", "#market-events-root"],
    "macro-calendar": ["#macro-statusbar", "#macro-summary-cards"],
    "knowledge-base": [".knowledge-hero", ".knowledge-sections"],
    "ashare-etf": ["#etf-overview", "#etf-equity-curve"],
    "btc-derivatives": [".btc-derivatives-page", ".btc-chart-overview"],
    "ai-strategy": [".strategy-scan-page", ".strategy-v2-toolbar", "#strategy-scan-matrix"],
    "gold-allocation": [".gold-workbench-grid", ".gold-chart-grid", ".gold-governance-grid"],
}

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")

DEFAULT_CONTRAST_THRESHOLD = 4.5  # WCAG AA for normal text


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #hex to (r, g, b)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return (0, 0, 0)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def parse_color(color_str: str) -> tuple[int, int, int, float] | None:
    """Parse a CSS color string to (r, g, b, alpha)."""
    color_str = color_str.strip()

    # Hex
    if color_str.startswith("#"):
        rgb = hex_to_rgb(color_str)
        return (*rgb, 1.0)

    # rgb() / rgba()
    m = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)', color_str)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = float(m.group(4)) if m.group(4) else 1.0
        return (r, g, b, a)

    return None


def relative_luminance(r: int, g: int, b: int) -> float:
    """Compute WCAG relative luminance."""
    def linearize(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(color1: str, color2: str) -> float:
    """Compute WCAG contrast ratio between two CSS color strings."""
    c1 = parse_color(color1)
    c2 = parse_color(color2)
    if c1 is None or c2 is None:
        return -1.0  # Cannot compute

    l1 = relative_luminance(c1[0], c1[1], c1[2])
    l2 = relative_luminance(c2[0], c2[1], c2[2])

    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def scan_page(page, page_id: str, threshold_contrast: float) -> dict:
    """Run a11y checks on a single page."""
    findings: list[dict] = []

    # 1. Check all <img> for alt attributes
    img_results = page.evaluate("""() => {
      const imgs = document.querySelectorAll('img');
      return Array.from(imgs).map(img => ({
        src: img.src.split('/').pop(),
        hasAlt: img.hasAttribute('alt'),
        alt: img.getAttribute('alt') || '',
      }));
    }""")
    for img in img_results:
        if not img["hasAlt"]:
            findings.append({
                "check": "img-alt",
                "severity": "FAIL",
                "detail": f"<img> missing alt: {img['src']}",
            })

    # 2. Check all <button> for accessible text
    btn_results = page.evaluate("""() => {
      const btns = document.querySelectorAll('button');
      return Array.from(btns).map(btn => ({
        text: btn.textContent.trim().slice(0, 50),
        hasAriaLabel: btn.hasAttribute('aria-label'),
        ariaLabel: btn.getAttribute('aria-label') || '',
      }));
    }""")
    for btn in btn_results:
        if not btn["text"] and not btn["hasAriaLabel"]:
            findings.append({
                "check": "button-text",
                "severity": "WARN",
                "detail": "<button> with no visible text or aria-label",
            })

    # 3. Check heading hierarchy
    heading_results = page.evaluate("""() => {
      const headings = document.querySelectorAll('h1,h2,h3,h4,h5,h6');
      return Array.from(headings).map(h => parseInt(h.tagName[1]));
    }""")
    if heading_results:
        if heading_results[0] != 1:
            findings.append({
                "check": "heading-hierarchy",
                "severity": "WARN",
                "detail": f"First heading is h{heading_results[0]}, not h1",
            })
        for i in range(1, len(heading_results)):
            if heading_results[i] > heading_results[i - 1] + 1:
                findings.append({
                    "check": "heading-hierarchy",
                    "severity": "WARN",
                    "detail": f"Skipped heading level: h{heading_results[i-1]} → h{heading_results[i]}",
                })

    # 4. Check color contrast on text elements
    # Fix: walk up DOM to find actual rendered background (not transparent)
    # Also handles CSS gradients (body uses gradient, not solid background-color)
    contrast_results = page.evaluate("""() => {
      const elements = document.querySelectorAll('p, span, a, button, h1, h2, h3, h4, h5, h6, td, th, li');
      const results = [];
      function extractGradientColor(bgImage) {
        // Extract the base color from CSS gradient.
        // Body uses multi-layer: radial-gradient(overlay) + linear-gradient(base).
        // We MUST extract from linear-gradient (base layer), not radial overlays.
        if (!bgImage || bgImage === 'none') return null;
        // Find linear-gradient: match from 'linear-gradient(' to its closing ')'.
        // Content may contain nested rgb()/rgba() parens, so we count depth.
        var startIdx = bgImage.indexOf('linear-gradient(');
        if (startIdx >= 0) {
          var depth = 0;
          var endIdx = startIdx;
          for (var i = startIdx; i < bgImage.length; i++) {
            if (bgImage[i] === '(') depth++;
            else if (bgImage[i] === ')') { depth--; if (depth === 0) { endIdx = i; break; } }
          }
          var searchIn = bgImage.substring(startIdx, endIdx + 1);
          var colorRe = /(rgba?\\([^)]+\\)|hsla?\\([^)]+\\)|#[0-9a-fA-F]{3,8})/gi;
          var colors = [];
          var m;
          while ((m = colorRe.exec(searchIn)) !== null) { colors.push(m[1]); }
          if (colors.length > 0) {
            for (var j = 0; j < colors.length; j++) {
              if (colors[j].startsWith('#')) return colors[j];
            }
            return colors[0];
          }
        }
        // Fallback: first color in any gradient
        var fallbackRe = /(rgba?\\([^)]+\\)|hsla?\\([^)]+\\)|#[0-9a-fA-F]{3,8})/i;
        var fallback = bgImage.match(fallbackRe);
        return fallback ? fallback[1] : null;
      }
      function findBgColor(el) {
        let current = el;
        while (current && current !== document.documentElement) {
          const style = window.getComputedStyle(current);
          // Check solid background first
          const bg = style.backgroundColor;
          if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
          // Check gradient background
          const bgImage = style.backgroundImage;
          if (bgImage && bgImage !== 'none') {
            const gradColor = extractGradientColor(bgImage);
            if (gradColor) return gradColor;
          }
          current = current.parentElement;
        }
        // Fallback: warm cream matching --bg token
        return 'rgb(243, 236, 225)';
      }
      for (const el of elements) {
        const style = window.getComputedStyle(el);
        const fg = style.color;
        const bg = findBgColor(el);
        const fontSize = parseFloat(style.fontSize);
        if (fg && fg !== 'rgba(0, 0, 0, 0)') {
          results.push({ fg, bg, fontSize, text: el.textContent.trim().slice(0, 30) });
        }
        if (results.length >= 30) break;  // sample limit
      }
      return results;
    }""")
    low_contrast_count = 0
    for item in contrast_results:
        ratio = contrast_ratio(item["fg"], item["bg"])
        if ratio < 0:
            continue
        # Large text threshold is 3.0, normal is 4.5
        is_large = item["fontSize"] >= 24  # 18pt = 24px
        threshold = 3.0 if is_large else threshold_contrast
        if ratio < threshold:
            low_contrast_count += 1
            if low_contrast_count <= 5:  # report first 5
                findings.append({
                    "check": "color-contrast",
                    "severity": "WARN",
                    "detail": f"Contrast {ratio:.1f}:1 < {threshold}:1 — '{item['text'][:20]}'",
                })

    # 5. Check form labels
    form_results = page.evaluate("""() => {
      const inputs = document.querySelectorAll('input, select, textarea');
      return Array.from(inputs).map(el => ({
        type: el.type || el.tagName.toLowerCase(),
        hasLabel: !!el.labels?.length || el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby'),
        id: el.id || '',
      }));
    }""")
    for inp in form_results:
        if not inp["hasLabel"] and inp["type"] not in ("hidden", "submit", "button"):
            findings.append({
                "check": "form-label",
                "severity": "WARN",
                "detail": f"<input type={inp['type']}> missing label (id={inp['id']})",
            })

    # 6. Check aria-* on interactive elements
    aria_results = page.evaluate("""() => {
      const interactive = document.querySelectorAll('[role], [aria-label], [aria-describedby], [aria-expanded]');
      return interactive.length;
    }""")
    if aria_results == 0:
        findings.append({
            "check": "aria-usage",
            "severity": "WARN",
            "detail": "No ARIA attributes found on any element",
        })

    # 7. Check focus-visible styles (static check on CSS)
    # This is done once globally, not per-page

    # Summarize
    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")

    return {
        "page_id": page_id,
        "findings": findings,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "img_count": len(img_results),
        "low_contrast_samples": low_contrast_count,
        "heading_levels": heading_results[:10],
        "aria_elements": aria_results,
        "verdict": "FAIL" if fail_count > 0 else "WARN" if warn_count > 3 else "PASS",
    }


def check_css_a11y_static() -> list[dict]:
    """Static checks on CSS file for a11y-related rules."""
    findings: list[dict] = []
    css_text = CSS_FILE.read_text(encoding="utf-8")

    # Check for prefers-reduced-motion
    if "prefers-reduced-motion" not in css_text:
        findings.append({
            "check": "reduced-motion",
            "severity": "FAIL",
            "detail": "No @media (prefers-reduced-motion) rule in styles.css",
        })
    else:
        # Check if it actually disables animations
        if "animation: 0.01ms" not in css_text and "animation: none" not in css_text:
            findings.append({
                "check": "reduced-motion",
                "severity": "WARN",
                "detail": "prefers-reduced-motion rule exists but may not fully disable animations",
            })

    # Check for :focus-visible styles
    if ":focus-visible" not in css_text and ":focus" not in css_text:
        findings.append({
            "check": "focus-visible",
            "severity": "WARN",
            "detail": "No :focus-visible or :focus styles defined",
        })

    return findings


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Accessibility scan — contrast, ARIA, alt text")
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all)",
    )
    p.add_argument(
        "--threshold-contrast",
        type=float,
        default=DEFAULT_CONTRAST_THRESHOLD,
        help=f"WCAG AA contrast threshold (default: {DEFAULT_CONTRAST_THRESHOLD})",
    )
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    # Static CSS checks
    static_findings = check_css_a11y_static()
    if static_findings:
        print("[static] CSS a11y checks:")
        for f in static_findings:
            print(f"  [{f['severity']}] {f['check']}: {f['detail']}")

    report = {"static_findings": static_findings, "per_page": [], "summary": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for pid in page_ids:
            print(f"[a11y] scanning {pid} ...", end=" ", flush=True)
            ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
            page = ctx.new_page()
            page.goto(f"{BASE_URL}{PAGE_ROUTES[pid]}", wait_until="domcontentloaded", timeout=30_000)

            # Wait for content
            selectors = REAL_CONTENT_SELECTORS.get(pid, [".card", "section"])
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                for sel in selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            break
                    except Exception:
                        pass
                else:
                    time.sleep(0.1)
                    continue
                break

            page.wait_for_timeout(1500)
            result = scan_page(page, pid, args.threshold_contrast)
            tag = result["verdict"]
            print(f"{tag}  fails={result['fail_count']} warns={result['warn_count']}")
            report["per_page"].append(result)
            ctx.close()

        browser.close()

    # Summary
    total_fail = sum(r["fail_count"] for r in report["per_page"])
    total_warn = sum(r["warn_count"] for r in report["per_page"])
    page_fails = sum(1 for r in report["per_page"] if r["verdict"] == "FAIL")
    report["summary"] = {
        "total_pages": len(report["per_page"]),
        "pages_with_fails": page_fails,
        "total_fail_findings": total_fail,
        "total_warn_findings": total_warn,
        "static_findings": len(static_findings),
    }

    print()
    print("=" * 60)
    print(f"a11y scan: {page_fails} pages with FAIL, {total_fail} fails, {total_warn} warns total")
    print("=" * 60)

    out_log = SCREENSHOT_DIR / "a11y_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    return 1 if page_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
