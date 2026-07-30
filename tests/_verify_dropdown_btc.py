"""Single-page Playwright smoke check for the unified dropdown.
Targets btc-derivatives-page (8 dropdowns: 5 chart toolbar + 3 hedge form).
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8002/btc-derivatives-page"

errors = []
warnings = []
dropdowns_found = []


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def on_console(msg):
    if msg.type == "error":
        errors.append(f"console.error: {msg.text}")


def on_response(resp):
    if resp.status >= 500:
        errors.append(f"5xx: {resp.url} -> {resp.status}")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", on_pageerror)
    page.on("console", on_console)
    page.on("response", on_response)
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    page.screenshot(path="tests/screenshots/dropdown-btc-cold.png", full_page=True)

    # count dropdowns
    count = page.evaluate("document.querySelectorAll('.dropdown').length")
    dropdowns_found.append(("cold", count))

    # open the chart-toolbar "时间窗口" dropdown
    page.click('.dropdown[data-dropdown-id="btc-window"]')
    page.wait_for_timeout(400)
    popover_visible = page.evaluate("() => !!document.querySelector('.dropdown-popover:not([hidden])')")
    if not popover_visible:
        errors.append("popover did not open on click")
    page.screenshot(path="tests/screenshots/dropdown-btc-open.png", full_page=True)

    # pick first item
    page.click(".dropdown-popover:not([hidden]) .dropdown-item:first-child")
    page.wait_for_timeout(400)

    # open and close hedge form dropdown
    page.evaluate("document.querySelector('#btc-hedge-form').scrollIntoView()")
    page.wait_for_timeout(200)
    page.click('.dropdown[data-dropdown-id="btc-hedge-portfolio-type"]')
    page.wait_for_timeout(400)
    popover_visible = page.evaluate("() => !!document.querySelector('.dropdown-popover:not([hidden])')")
    if not popover_visible:
        errors.append("hedge popover did not open")
    page.screenshot(path="tests/screenshots/dropdown-btc-hedge.png", full_page=True)

    browser.close()

print(f"dropdowns found: {dropdowns_found}")
print(f"errors: {len(errors)}")
for e in errors:
    print("  -", e)

sys.exit(1 if errors else 0)