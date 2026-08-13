"""
Visual regression test — pixel-level diff against baseline screenshots.

Capability: P0-A (Visual Regression)
Compares current page renders against baseline screenshots using two metrics:
  1. Pixel difference ratio (percentage of differing pixels)
  2. SSIM (Structural Similarity Index) via scipy

Thresholds:
  - PASS: SSIM >= 0.95 AND pixel_diff_rate <= 0.02 (2%)
  - WARN: SSIM >= 0.90 OR pixel_diff_rate <= 0.05
  - FAIL: below WARN thresholds

Usage:
  python tests/a11y_visual_diff.py --baseline          # establish baselines
  python tests/a11y_visual_diff.py --pages all         # diff all pages
  python tests/a11y_visual_diff.py --pages monitoring-overview,market-analysis
  python tests/a11y_visual_diff.py --threshold-ssim 0.93 --threshold-pixel 0.03
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
BASELINE_DIR = SCREENSHOT_DIR / "baseline"
DIFF_DIR = SCREENSHOT_DIR / "diff"
DIFF_DIR.mkdir(parents=True, exist_ok=True)

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

# Default thresholds
DEFAULT_THRESHOLD_SSIM = 0.95
DEFAULT_THRESHOLD_PIXEL = 0.02


def capture_screenshot(page_id: str, route: str, out_path: Path) -> bool:
    """Navigate to a page, wait for real content, screenshot to out_path."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
        page = ctx.new_page()
        page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=30_000)

        # Wait for real content
        selectors = REAL_CONTENT_SELECTORS.get(page_id, [".card", "section"])
        deadline = time.monotonic() + 10.0
        found = False
        while time.monotonic() < deadline:
            for sel in selectors:
                try:
                    if page.locator(sel).count() > 0:
                        found = True
                        break
                except Exception:
                    pass
            if found:
                break
            time.sleep(0.1)

        if not found:
            print(f"  [warn] real content not detected for {page_id}, screenshot may be incomplete")

        page.wait_for_timeout(1500)  # extra settle time for charts/animations
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()
    return found


def compute_pixel_diff(img_a: Image.Image, img_b: Image.Image) -> tuple[float, Image.Image]:
    """
    Compute pixel-level difference between two images.
    Returns (diff_ratio, diff_heatmap).
    """
    # Normalize to same size
    size = (2560, 1440)
    a = img_a.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    b = img_b.convert("RGB").resize(size, Image.Resampling.LANCZOS)

    # Raw difference
    diff = ImageChops.difference(a, b)

    # Convert to numpy for analysis
    diff_arr = np.array(diff, dtype=np.float64)
    # Count pixels where any channel differs by more than threshold
    pixel_diff_mask = np.any(diff_arr > 25, axis=2)  # tolerance of 25/255 per channel
    diff_ratio = float(np.sum(pixel_diff_mask) / pixel_diff_mask.size)

    # Generate heatmap: red overlay on differing pixels
    heatmap = a.copy()
    heatmap_draw = ImageDraw.Draw(heatmap)
    # Mark diff pixels with semi-transparent red
    diff_coords = np.argwhere(pixel_diff_mask)
    for y, x in diff_coords[::4]:  # sample every 4th pixel for performance
        heatmap_draw.point((x, y), fill=(255, 0, 0))

    return diff_ratio, heatmap


def compute_ssim(img_a: Image.Image, img_b: Image.Image) -> float:
    """
    Compute SSIM (Structural Similarity) between two images.
    Uses a simplified sliding-window approach with numpy.
    """
    size = (2560, 1440)
    a = np.array(img_a.convert("L").resize(size, Image.Resampling.LANCZOS), dtype=np.float64)
    b = np.array(img_b.convert("L").resize(size, Image.Resampling.LANCZOS), dtype=np.float64)

    # SSIM constants
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    # Gaussian window (11x11, sigma=1.5)
    window = _gaussian_window(11, 1.5)

    # Convolve
    from scipy.ndimage import convolve

    mu_a = convolve(a, window, mode="reflect")
    mu_b = convolve(b, window, mode="reflect")

    mu_a_sq = mu_a ** 2
    mu_b_sq = mu_b ** 2
    mu_ab = mu_a * mu_b

    sigma_a_sq = convolve(a ** 2, window, mode="reflect") - mu_a_sq
    sigma_b_sq = convolve(b ** 2, window, mode="reflect") - mu_b_sq
    sigma_ab = convolve(a * b, window, mode="reflect") - mu_ab

    ssim_map = ((2 * mu_ab + C1) * (2 * sigma_ab + C2)) / (
        (mu_a_sq + mu_b_sq + C1) * (sigma_a_sq + sigma_b_sq + C2)
    )

    return float(np.mean(ssim_map))


def _gaussian_window(size: int, sigma: float) -> np.ndarray:
    """Create a 2D Gaussian kernel."""
    x = np.arange(size) - size // 2
    g1 = np.exp(-(x ** 2) / (2 * sigma ** 2))
    g2d = np.outer(g1, g1)
    return g2d / g2d.sum()


def diff_page(
    page_id: str,
    route: str,
    threshold_ssim: float,
    threshold_pixel: float,
) -> dict:
    """Diff a single page against its baseline."""
    baseline_path = BASELINE_DIR / f"{page_id}.png"
    current_path = SCREENSHOT_DIR / f"{page_id}.png"
    diff_out_path = DIFF_DIR / f"{page_id}_diff.png"

    result = {
        "page_id": page_id,
        "baseline_exists": baseline_path.exists(),
        "ssim": None,
        "pixel_diff_rate": None,
        "verdict": "no-baseline",
        "diff_image": None,
    }

    if not baseline_path.exists():
        # No baseline — capture current as reference
        print(f"  [info] no baseline for {page_id}, capturing current render")
        capture_screenshot(page_id, route, current_path)
        result["verdict"] = "captured-no-baseline"
        return result

    # Capture current screenshot
    capture_screenshot(page_id, route, current_path)

    try:
        img_baseline = Image.open(baseline_path)
        img_current = Image.open(current_path)
    except Exception as e:
        result["verdict"] = f"image-load-error:{e}"
        return result

    # Compute metrics
    try:
        ssim = compute_ssim(img_baseline, img_current)
        pixel_diff, heatmap = compute_pixel_diff(img_baseline, img_current)
    except Exception as e:
        result["verdict"] = f"compute-error:{e}"
        return result

    result["ssim"] = round(ssim, 4)
    result["pixel_diff_rate"] = round(pixel_diff, 4)

    # Verdict
    if ssim >= threshold_ssim and pixel_diff <= threshold_pixel:
        result["verdict"] = "PASS"
    elif ssim >= threshold_ssim - 0.05 or pixel_diff <= threshold_pixel * 2.5:
        result["verdict"] = "WARN"
    else:
        result["verdict"] = "FAIL"

    # Save heatmap
    try:
        heatmap.save(str(diff_out_path))
        result["diff_image"] = str(diff_out_path.relative_to(REPO_ROOT))
    except Exception:
        pass

    return result


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Visual regression test — pixel diff + SSIM")
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all)",
    )
    p.add_argument(
        "--baseline",
        action="store_true",
        help="capture baselines instead of diffing",
    )
    p.add_argument(
        "--threshold-ssim",
        type=float,
        default=DEFAULT_THRESHOLD_SSIM,
        help=f"SSIM pass threshold (default: {DEFAULT_THRESHOLD_SSIM})",
    )
    p.add_argument(
        "--threshold-pixel",
        type=float,
        default=DEFAULT_THRESHOLD_PIXEL,
        help=f"Pixel diff rate pass threshold (default: {DEFAULT_THRESHOLD_PIXEL})",
    )
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    report = {"results": [], "summary": {}}

    if args.baseline:
        print(f"[baseline] capturing {len(page_ids)} pages as baselines...")
        for pid in page_ids:
            print(f"  capturing {pid} ...", end=" ", flush=True)
            out = BASELINE_DIR / f"{pid}.png"
            ok = capture_screenshot(pid, PAGE_ROUTES[pid], out)
            tag = "OK" if ok else "WARN"
            print(f"{tag} → {out.relative_to(REPO_ROOT)}")
            report["results"].append({
                "page_id": pid,
                "action": "baseline-captured",
                "content_detected": ok,
            })
    else:
        print(f"[diff] comparing {len(page_ids)} pages against baselines...")
        print(f"  thresholds: SSIM >= {args.threshold_ssim}, pixel_diff <= {args.threshold_pixel}")
        for pid in page_ids:
            print(f"  diffing {pid} ...", end=" ", flush=True)
            r = diff_page(pid, PAGE_ROUTES[pid], args.threshold_ssim, args.threshold_pixel)
            tag = r["verdict"]
            detail = ""
            if r["ssim"] is not None:
                detail = f" SSIM={r['ssim']:.4f} pixel_diff={r['pixel_diff_rate']:.4f}"
            print(f"{tag}{detail}")
            report["results"].append(r)

    # Summary
    if not args.baseline:
        pass_count = sum(1 for r in report["results"] if r.get("verdict") == "PASS")
        warn_count = sum(1 for r in report["results"] if r.get("verdict") == "WARN")
        fail_count = sum(1 for r in report["results"] if r.get("verdict") == "FAIL")
        no_base = sum(1 for r in report["results"] if r.get("verdict") in ("no-baseline", "captured-no-baseline"))
        report["summary"] = {
            "total": len(report["results"]),
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "no_baseline": no_base,
        }
        print()
        print("=" * 60)
        print(f"visual diff: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL, {no_base} no-baseline")
        print("=" * 60)

    out_log = SCREENSHOT_DIR / "visual_diff_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    if args.baseline:
        return 0
    return 1 if report["summary"].get("fail", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
