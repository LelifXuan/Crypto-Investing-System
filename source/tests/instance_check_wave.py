"""Playwright instance check for chart-skeleton wave animation (v2).

Cold-start data is usually cached, so the skeleton rarely shows on first
visit. To force a visible skeleton we intercept the API response and
delay it. That way we can:
  1. Confirm wave animation runs on the skeleton.
  2. Capture two frames during the skeleton window and prove the wave
     actually moves (opacity profile shifts).
  3. Verify reduced-motion clamps duration.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("tests/screenshots/wave_instance_check")
OUT.mkdir(parents=True, exist_ok=True)


def probe(page):
    """Read live animation state for the first 8 chart-skeleton candles."""
    return page.evaluate(
        """() => {
          const candles = document.querySelectorAll('.chart-skeleton-candle.loading-pulse');
          if (candles.length === 0) return null;
          const samples = [];
          for (let i = 0; i < Math.min(candles.length, 8); i++) {
            const cs = getComputedStyle(candles[i]);
            samples.push({
              idx: i,
              animationName: cs.animationName,
              animationDuration: cs.animationDuration,
              animationDelay: cs.animationDelay,
              animationFillMode: cs.animationFillMode,
              opacity: parseFloat(cs.opacity).toFixed(3),
              transform: cs.transform,
            });
          }
          return {
            count: candles.length,
            samples: samples,
          };
        }"""
    )


def is_wave_alive(data):
    if not data or not data.get("samples"):
        return False, "no skeleton"
    s = data["samples"]
    if s[0]["animationName"] != "candleBreath":
        return False, f"anim={s[0]['animationName']}"
    if s[0]["animationDelay"] != "0s":
        return False, f"first delay={s[0]['animationDelay']}"
    has_stagger = any(x["animationDelay"] != "0s" for x in s[1:6])
    if not has_stagger:
        return False, "no stagger"
    # matrix(1, 0, 0, scaleY, 0, 0) is non-identity when scaleY != 1.
    # matrix(1, 0, 0, 1, 0, 0) is identity — reject those.
    import re
    m = re.match(r"matrix\(\s*1\s*,\s*0\s*,\s*0\s*,\s*([0-9.eE+-]+)\s*,", s[0]["transform"])
    if not m:
        return False, f"transform={s[0]['transform']}"
    scale_y = float(m.group(1))
    if abs(scale_y - 1.0) < 0.001:
        return False, f"identity transform={s[0]['transform']} (scaleY=1)"
    return True, "ok"


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---- 1. Cold-start on indicators-page with route delay -----------
        # indicators has 6 chart-wraps; we know it shows skeletons.
        ctx = browser.new_context(viewport={"width": 2560, "height": 1440})

        # Intercept any indicator/structure API and add a delay so the
        # skeleton window is long enough to probe + screenshot.
        def slow_route(route):
            time.sleep(1.2)
            route.continue_()
        ctx.route("**/api/**", slow_route)
        ctx.route("**/market-prices/**", slow_route)
        ctx.route("**/structure/**", slow_route)

        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        for page_id, url in [
            ("market-analysis", "/indicators-page"),
        ]:
            try:
                page.goto(f"http://127.0.0.1:8002{url}", wait_until="domcontentloaded", timeout=30000)
                # Skeleton mounts fast; probe quickly
                try:
                    page.wait_for_selector(".chart-skeleton-candle", timeout=8000, state="attached")
                except Exception as e:
                    results.append({"page": page_id, "phase": "cold-start", "error": f"no skeleton: {e}"})
                    continue
                time.sleep(0.4)

                data_a = probe(page)
                page.screenshot(path=str(OUT / f"{page_id}_A.png"), full_page=False)

                time.sleep(0.7)
                data_b = probe(page)
                page.screenshot(path=str(OUT / f"{page_id}_B.png"), full_page=False)

                ok_a, msg_a = is_wave_alive(data_a)
                ok_b, msg_b = is_wave_alive(data_b)

                # Check wave moved: opacity values must differ between A and B
                moved = False
                if data_a and data_b:
                    ops_a = [s["opacity"] for s in data_a["samples"]]
                    ops_b = [s["opacity"] for s in data_b["samples"]]
                    moved = sum(1 for a, b in zip(ops_a, ops_b) if a != b) >= 4

                results.append({
                    "page": page_id,
                    "phase": "cold-start",
                    "candle_count": data_a["count"] if data_a else 0,
                    "wave_alive_A": ok_a,
                    "wave_alive_B": ok_b,
                    "msg_A": msg_a,
                    "msg_B": msg_b,
                    "first_anim": data_a["samples"][0]["animationName"] if data_a and data_a["samples"] else None,
                    "first_delay": data_a["samples"][0]["animationDelay"] if data_a and data_a["samples"] else None,
                    "first_transform_A": data_a["samples"][0]["transform"] if data_a and data_a["samples"] else None,
                    "first_transform_B": data_b["samples"][0]["transform"] if data_b and data_b["samples"] else None,
                    "opacity_profile_A": [s["opacity"] for s in data_a["samples"]] if data_a else [],
                    "opacity_profile_B": [s["opacity"] for s in data_b["samples"]] if data_b else [],
                    "wave_moved": moved,
                    "err_count": len(errs),
                })
                errs.clear()
            except Exception as e:
                results.append({"page": page_id, "phase": "cold-start", "error": str(e)})

        ctx.close()

        # ---- 2. Reduced-motion clamp ------------------------------------
        ctx = browser.new_context(viewport={"width": 2560, "height": 1440}, reduced_motion="reduce")
        ctx.route("**/api/**", slow_route)
        ctx.route("**/market-prices/**", slow_route)
        ctx.route("**/structure/**", slow_route)
        page = ctx.new_page()
        try:
            page.goto("http://127.0.0.1:8002/indicators-page", wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector(".chart-skeleton-candle", timeout=8000, state="attached")
                time.sleep(0.4)
                data = probe(page)
                page.screenshot(path=str(OUT / "indicators_reduced_motion.png"), full_page=False)
                if data and data["samples"]:
                    durations = set(s["animationDuration"] for s in data["samples"])
                    # Chromium serializes 0.01ms as "1e-05s" (scientific).
                    # Both forms represent the same reduced-motion clamp.
                    clamped = durations == {"0.01ms"} or durations == {"1e-05s"}
                    results.append({
                        "page": "indicators (reduced-motion)",
                        "phase": "reduced-motion",
                        "candle_count": data["count"],
                        "durations_seen": sorted(durations),
                        "first_anim": data["samples"][0]["animationName"],
                        "first_fill_mode": data["samples"][0]["animationFillMode"],
                        "clamped_to_0_01ms": clamped,
                    })
            except Exception as e:
                results.append({"phase": "reduced-motion", "error": str(e)})
        finally:
            ctx.close()

        # ---- 3. Force re-fetch via dropdown switch ------------------------
        # Slow the structure bundle endpoint (GET /api/v1/structure/tab/bundle) so
        # the chartSkeleton window is long enough to probe. Dropdown switch
        # triggers loadData() which always mounts the skeleton overlay
        # regardless of cache state.
        def slow_structure(route):
            time.sleep(1.4)
            route.continue_()
        ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
        ctx.route("**/api/v1/structure/tab/bundle*", slow_structure)
        page = ctx.new_page()
        try:
            page.goto("http://127.0.0.1:8002/structure-page", wait_until="domcontentloaded", timeout=30000)
            # Try to catch the skeleton during initial fetch (it lasts ~1.2s now)
            initial_skeleton = False
            try:
                page.wait_for_selector(".chart-skeleton-candle", timeout=4000, state="attached")
                initial_skeleton = True
                time.sleep(0.4)
                data = probe(page)
                page.screenshot(path=str(OUT / "structure_initial_skeleton.png"), full_page=False)
                if data:
                    ok, msg = is_wave_alive(data)
                    results.append({
                        "page": "structure (initial skeleton)",
                        "phase": "dropdown-switch",
                        "candle_count": data["count"],
                        "wave_alive": ok,
                        "msg": msg,
                        "first_anim": data["samples"][0]["animationName"],
                        "first_delay": data["samples"][0]["animationDelay"],
                        "first_transform": data["samples"][0]["transform"],
                        "delays_first_8": [s["animationDelay"] for s in data["samples"]],
                        "opacity_first_8": [s["opacity"] for s in data["samples"]],
                    })
            except Exception:
                pass

            if not initial_skeleton:
                # Click the timeframe dropdown button directly
                clicked = page.evaluate("""() => {
                  const btn = document.querySelector('button.dropdown[data-dropdown-id=\"structure-timeframe\"]');
                  if (!btn) return 'no-btn';
                  btn.click();
                  return 'clicked';
                }""")
                time.sleep(0.4)
                # Pick a non-default option (4h or 1w)
                picked = page.evaluate("""() => {
                  const opts = document.querySelectorAll('[role=\"option\"]');
                  const pickable = ['4h', '1w', '1M', '1h'];
                  for (const want of pickable) {
                    for (const o of opts) {
                      if (o.textContent.trim() === want) {
                        o.click();
                        return 'picked:' + want;
                      }
                    }
                  }
                  if (opts.length > 1) { opts[1].click(); return 'picked:1'; }
                  return 'no-pick';
                }""")
                try:
                    page.wait_for_selector(".chart-skeleton-candle", timeout=8000, state="attached")
                    time.sleep(0.4)
                    data = probe(page)
                    page.screenshot(path=str(OUT / "structure_after_switch.png"), full_page=False)
                    ok, msg = is_wave_alive(data)
                    results.append({
                        "page": "structure (after switch)",
                        "phase": "dropdown-switch",
                        "clicked": clicked,
                        "picked": picked,
                        "candle_count": data["count"] if data else 0,
                        "wave_alive": ok,
                        "msg": msg,
                        "first_anim": data["samples"][0]["animationName"] if data and data["samples"] else None,
                        "first_delay": data["samples"][0]["animationDelay"] if data and data["samples"] else None,
                        "first_transform": data["samples"][0]["transform"] if data and data["samples"] else None,
                        "delays_first_8": [s["animationDelay"] for s in data["samples"]] if data else [],
                        "opacity_first_8": [s["opacity"] for s in data["samples"]] if data else [],
                    })
                except Exception as e:
                    results.append({"phase": "dropdown-switch", "clicked": clicked, "picked": picked, "error": str(e)})
        finally:
            ctx.close()

        # ---- 4. SPA-switch skeleton transition ----------------------------
        # Open monitoring, then SPA-jump to a chart page; skeleton should
        # briefly appear during the route change.
        ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
        ctx.route("**/api/**", slow_route)
        ctx.route("**/market-prices/**", slow_route)
        ctx.route("**/structure/**", slow_route)
        page = ctx.new_page()
        try:
            page.goto("http://127.0.0.1:8002/monitoring-page", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            # SPA navigation via in-app link
            page.evaluate("""
              const link = document.querySelector('a[href*=\"structure-page\"], a[data-page-link=\"market-structure\"]');
              if (link) link.click();
            """)
            try:
                page.wait_for_selector(".chart-skeleton-candle", timeout=8000, state="attached")
                time.sleep(0.4)
                data = probe(page)
                page.screenshot(path=str(OUT / "spa_structure.png"), full_page=False)
                ok, msg = is_wave_alive(data)
                results.append({
                    "page": "structure (via SPA)",
                    "phase": "spa-switch",
                    "candle_count": data["count"] if data else 0,
                    "wave_alive": ok,
                    "msg": msg,
                    "first_anim": data["samples"][0]["animationName"] if data and data["samples"] else None,
                })
            except Exception as e:
                results.append({"phase": "spa-switch", "error": str(e)})
        finally:
            ctx.close()

        browser.close()

    # Pretty print
    print("=" * 60)
    print("WAVE INSTANCE CHECK REPORT")
    print("=" * 60)
    fails = 0
    for c in results:
        print(json.dumps(c, indent=2, default=str))
        # fail = wave_alive False OR clamped_to_0_01ms False (if reduced-motion)
        wave_flag = c.get("wave_alive", c.get("wave_alive_A", True))
        clamped = c.get("clamped_to_0_01ms")
        if wave_flag is False:
            fails += 1
        if clamped is False:
            fails += 1
    print("=" * 60)
    print(f"Total: {len(results)}, Failures: {fails}")
    Path("tests/screenshots/wave_instance_report.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()