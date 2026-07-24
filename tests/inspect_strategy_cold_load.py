"""Cold-load inspection of /strategy-page.

Mimics a real user landing on the AI Strategy page in a fresh browser
context (no other pages visited, no cached fetches). Records:
  - console errors / warnings
  - page errors
  - all network requests (URL, status, timing, body size)
  - DOM mutations on the strategy-scan-status banner
  - how long until the user sees real data (matrix cells / ranked cards)
  - how long until the user sees "warming" / "loading" / "error" copy

Saves screenshot at end. Prints a human-readable summary.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8007/strategy-page"
OUT = Path("tests/screenshots/strategy-cold-load-inspect.png")


def main() -> int:
    events: list[tuple[float, str, str]] = []
    requests: list[dict] = []
    responses: list[dict] = []

    def now() -> float:
        return time.monotonic()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.on("console", lambda m: events.append((now(), "console", f"{m.type}: {m.text[:200]}")))
        page.on("pageerror", lambda e: events.append((now(), "pageerror", str(e)[:300])))
        page.on("request", lambda r: requests.append({
            "t": now(),
            "method": r.method,
            "url": r.url,
        }))
        page.on("response", lambda r: responses.append({
            "t": now(),
            "status": r.status,
            "url": r.url,
        }))

        t_start = now()
        events.append((t_start, "navigate", URL))
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # Snapshot the status banner over time
        snapshots: list[tuple[float, str]] = []
        for _ in range(45):  # ~45 seconds of polling
            try:
                txt = page.locator("#strategy-scan-status").inner_text(timeout=500)
            except Exception:
                txt = "<no status el>"
            snapshots.append((now(), txt[:80]))
            time.sleep(1)

        # How long until we see real opportunities? matrix has 33 cells, ranked has 3 cards.
        try:
            page.locator(".scan-matrix-table").wait_for(state="visible", timeout=120_000)
            t_matrix_visible = now()
        except Exception:
            t_matrix_visible = -1

        try:
            page.locator(".scan-ranked-card").first.wait_for(state="visible", timeout=60_000)
            t_ranked_visible = now()
        except Exception:
            t_ranked_visible = -1

        try:
            # Wait a bit more for any "warming" → real data transition
            page.wait_for_function(
                "() => { const el = document.querySelector('#strategy-scan-status'); return el && el.innerText && !el.innerText.includes('预热') && !el.innerText.includes('扫描失败') && el.innerText.length > 0; }",
                timeout=120_000,
            )
            t_steady_state = now()
        except Exception:
            t_steady_state = -1

        page.screenshot(path=str(OUT), full_page=True)
        events.append((now(), "screenshot", str(OUT)))
        browser.close()

    # Print report
    print("=" * 70)
    print(f"STARTED     t=0.0s")
    print(f"END         t={(now()):.2f}s")
    if t_matrix_visible > 0:
        print(f"matrix .scan-matrix-table visible at t={t_matrix_visible - t_start:.2f}s")
    else:
        print(f"matrix .scan-matrix-table NEVER became visible")
    if t_ranked_visible > 0:
        print(f"ranked .scan-ranked-card visible at t={t_ranked_visible - t_start:.2f}s")
    else:
        print(f"ranked .scan-ranked-card NEVER became visible (no real opportunities?)")
    if t_steady_state > 0:
        print(f"steady-state reached at t={t_steady_state - t_start:.2f}s")
    print()
    print("=== Banner text over time ===")
    for t, txt in snapshots:
        marker = ""
        if "预热" in txt: marker = " [WARMING]"
        elif "扫描失败" in txt: marker = " [ERROR]"
        elif "发现" in txt: marker = " [DATA]"
        elif "无明确" in txt: marker = " [EMPTY]"
        elif "正在" in txt: marker = " [LOADING]"
        print(f"  +{t - t_start:5.2f}s  {txt!r}{marker}")
    print()
    print(f"=== Console / Page errors ({len([e for e in events if e[1] in ('console','pageerror')])} events) ===")
    for t, kind, msg in events:
        if kind in ("console", "pageerror"):
            print(f"  +{t - t_start:5.2f}s  [{kind}] {msg}")
    print()
    print(f"=== Network requests ({len(requests)}) ===")
    for r in requests:
        print(f"  +{r['t'] - t_start:5.2f}s  {r['method']} {r['url'][:120]}")
    print()
    print(f"=== Network responses ({len(responses)}) ===")
    for r in responses:
        print(f"  +{r['t'] - t_start:5.2f}s  {r['status']} {r['url'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())