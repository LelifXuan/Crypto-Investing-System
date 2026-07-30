"""Multi-page Playwright smoke check for all 6 affected pages."""
import sys
from playwright.sync_api import sync_playwright

PAGES = [
    ("indicators-page", "analysis-timeframe"),
    ("structure-page", "structure-instrument"),
    ("knowledge-page", "knowledge-page-filter"),
    ("ashare-etf-page", "etf-mode"),
    ("market-events-page", "supply-calendar-filter"),
    ("btc-derivatives-page", "btc-window"),
]

errors_total = []
warnings_total = []


def run_page(p, url, dd_id):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errs = []

    def on_pageerror(err):
        errs.append(f"pageerror: {err}")

    def on_console(msg):
        if msg.type == "error":
            errs.append(f"console.error: {msg.text}")

    page.on("pageerror", on_pageerror)
    page.on("console", on_console)
    page.goto(f"http://127.0.0.1:8002/{url}", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3500)

    count = page.evaluate("() => document.querySelectorAll('.dropdown').length")
    page.screenshot(path=f"tests/screenshots/dropdown-{url.replace('-page','')}-cold.png", full_page=False)
    try:
        page.click(f'.dropdown[data-dropdown-id="{dd_id}"]', timeout=5000)
    except Exception as ex:
        errs.append(f"{url}: click failed: {ex}")
        page.screenshot(path=f"tests/screenshots/dropdown-{url.replace('-page','')}-fail.png", full_page=True)
        browser.close()
        return errs
    page.wait_for_timeout(500)
    popover_visible = page.evaluate("() => !!document.querySelector('.dropdown-popover:not([hidden])')")
    if not popover_visible:
        errs.append(f"{url}: popover did not open")

    page.screenshot(path=f"tests/screenshots/dropdown-{url.replace('-page','')}-open.png", full_page=False)
    print(f"  [{url}] dropdowns={count} popover_ok={popover_visible}")
    browser.close()
    return errs


with sync_playwright() as p:
    for url, dd_id in PAGES:
        try:
            e = run_page(p, url, dd_id)
            errors_total.extend(e)
        except Exception as ex:
            errors_total.append(f"{url}: {ex}")


print(f"\n--- total errors: {len(errors_total)} ---")
for e in errors_total:
    print("  -", e)

sys.exit(1 if errors_total else 0)