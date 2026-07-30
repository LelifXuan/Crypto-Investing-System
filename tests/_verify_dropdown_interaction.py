"""Verify keyboard interaction, selected state, and item click on dropdowns."""
import sys
from playwright.sync_api import sync_playwright

errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))
    page.on("console", lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)

    page.goto("http://127.0.0.1:8002/btc-derivatives-page", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)

    # Open btc-window dropdown
    page.click('.dropdown[data-dropdown-id="btc-window"]')
    page.wait_for_timeout(400)

    items = page.evaluate("""
      () => Array.from(document.querySelectorAll('.dropdown-popover:not([hidden]) .dropdown-item')).map(el => ({
        value: el.dataset.value,
        label: el.textContent.trim(),
        selected: el.getAttribute('aria-selected') === 'true',
      }))
    """)
    print(f"items found: {len(items)}")
    for it in items:
        print(f"  {it}")

    # pick 30D (second item)
    page.click('.dropdown-popover:not([hidden]) .dropdown-item:nth-child(2)')
    page.wait_for_timeout(300)
    label = page.evaluate("() => document.querySelector('.dropdown[data-dropdown-id=\"btc-window\"] .dropdown-label').textContent")
    print(f"after pick, label = {label!r}")
    if "30D" not in label:
        errors.append(f"label did not update to '30D', got {label!r}")

    # Type-ahead: close popover first to clear stale state, then reopen + typeahead
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.click('.dropdown[data-dropdown-id="btc-window"]')
    page.wait_for_timeout(300)
    page.focus('.dropdown[data-dropdown-id="btc-window"]')
    page.keyboard.press("9")
    page.wait_for_timeout(200)
    # Inspect the items for debugging
    debug = page.evaluate("""
      () => Array.from(document.querySelectorAll('.dropdown-popover:not([hidden]) .dropdown-item')).map(el => ({
        label: el.textContent.trim(),
        lower: el.textContent.trim().toLowerCase(),
        active: el.classList.contains('is-active'),
        selected: el.getAttribute('aria-selected'),
      }))
    """)
    print("after '9', items:")
    for d in debug:
        print(f"  {d}")
    active_label = page.evaluate("""
      () => {
        const a = document.querySelector('.dropdown-popover:not([hidden]) .dropdown-item.is-active');
        return a ? a.textContent.trim() : null;
      }
    """)
    print(f"typeahead '9' active = {active_label!r}")
    # mojibake: raw bytes pass through; we only check the suffix ("90D" appears at end).
    if not active_label or "90D" not in active_label:
        errors.append(f"typeahead '9' did not focus '90D*', got {active_label!r}")

    # Esc closes
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    open_after_esc = page.evaluate("() => !!document.querySelector('.dropdown-popover:not([hidden])')")
    if open_after_esc:
        errors.append("popover did not close on Escape")

    page.screenshot(path="tests/screenshots/dropdown-btc-derivatives-final.png", full_page=False)
    browser.close()

print(f"\n--- errors: {len(errors)} ---")
for e in errors:
    print("  -", e)
sys.exit(1 if errors else 0)