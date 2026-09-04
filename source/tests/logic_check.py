"""Pure Playwright interaction logic check.
2026-09-01. Viewport 2560x1600 per user request.
"""
from playwright.sync_api import sync_playwright
import sys

VIEWPORT = {"width": 2560, "height": 1600}
BASE = "http://127.0.0.1:8002"
results = []
console_errors = []
page_errors = []


def add(name, ok, detail=""):
    results.append({"name": name, "ok": ok, "detail": detail})
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name} :: {detail}")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    print("\n=== CHECK 1: events buttons inside feed-card ===")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.on("pageerror", lambda e: page_errors.append(("events", str(e))))
    page.on("console", lambda m: m.type == "error" and console_errors.append(("events", m.text)))
    page.goto(f"{BASE}/market-events-page", wait_until="domcontentloaded")
    page.wait_for_timeout(6500)

    btn_t = page.locator("#events-translate-toggle")
    btn_r = page.locator("#events-refresh")
    add("1a) #events-translate-toggle exists", btn_t.count() == 1, f"count={btn_t.count()}")
    add("1b) #events-refresh exists", btn_r.count() == 1, f"count={btn_r.count()}")

    in_card_t = btn_t.evaluate("el => !!el.closest('.events-feed-card')")
    in_card_r = btn_r.evaluate("el => !!el.closest('.events-feed-card')")
    add("1c) translate button inside .events-feed-card", in_card_t)
    add("1d) refresh button inside .events-feed-card", in_card_r)

    toolbar_count = page.locator(".events-context-actions").count()
    add("1e) no leftover hero .events-context-actions toolbar",
        toolbar_count == 0, f"count={toolbar_count}")

    add("1f) translate button visible", btn_t.is_visible())
    add("1g) refresh button visible", btn_r.is_visible())

    pre_text = btn_t.text_content()
    btn_t.click()
    try:
        page.wait_for_function(
            f"() => document.getElementById('events-translate-toggle')?.textContent !== {pre_text!r}",
            timeout=3000,
        )
        post_text = page.locator("#events-translate-toggle").text_content()
        add("1h) translate toggle text changes after click",
            pre_text != post_text, f"'{pre_text}' -> '{post_text}'")
    except Exception:
        post_text = page.locator("#events-translate-toggle").text_content()
        add("1h) translate toggle text changes after click",
            False, f"'{pre_text}' -> '{post_text}' (timeout)")

    pre_btn_text = page.locator("#events-refresh").text_content()
    page.locator("#events-refresh").click()
    try:
        page.wait_for_function(
            f"() => {{ const b = document.getElementById('events-refresh'); return b && (b.disabled === true || b.textContent !== {pre_btn_text!r}); }}",
            timeout=3000,
        )
        during_btn_text = page.locator("#events-refresh").text_content()
        during_disabled = page.locator("#events-refresh").is_disabled()
        add("1j) refresh button state changes after click",
            during_disabled or during_btn_text != pre_btn_text,
            f"text '{pre_btn_text}' -> '{during_btn_text}', disabled={during_disabled}")
    except Exception:
        during_btn_text = page.locator("#events-refresh").text_content()
        add("1j) refresh button state changes after click",
            False, f"'{pre_btn_text}' -> '{during_btn_text}' (timeout)")

    page.wait_for_timeout(8000)
    event_card_count = page.locator(".event-card").count()
    add("1k) feed has rendered event-cards after refresh",
        event_card_count > 0, f"count={event_card_count}")
    ctx.close()

    print("\n=== CHECK 2: governance ledger items rendered ===")
    FOOTER_PAGES = {
        "gold-allocation":     ("/gold-allocation-page",  ".governance-ledger--gold"),
        "ashare-etf":          ("/ashare-etf-page",       ".governance-ledger--ashare_etf"),
        "btc-derivatives":     ("/btc-derivatives-page",  ".governance-ledger--btc"),
        "monitoring-overview": ("/monitoring-page",       ".governance-ledger--monitoring"),
    }
    for name, (route, sel) in FOOTER_PAGES.items():
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append((name, str(e))))
        page.on("console", lambda m: m.type == "error" and console_errors.append((name, m.text)))
        page.goto(f"{BASE}{route}", wait_until="domcontentloaded")
        # Monitoring uses diff-update and waits on backend; some pages
        # only render the ledger after the bundle fetch lands. Poll up
        # to 14s for the ledger to appear (cold start can be slow).
        try:
            page.wait_for_selector(sel, timeout=14000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

        ledger = page.locator(sel).first
        exists = ledger.count() == 1
        add(f"2.{name}) ledger {sel} exists", exists, f"count={ledger.count()}")
        if exists:
            items = ledger.locator(".governance-ledger__item")
            n_items = items.count()
            add(f"2.{name}) has >=4 items", n_items >= 4, f"count={n_items}")

            head = ledger.locator(".governance-ledger__head").first
            grid = ledger.locator(".governance-ledger__grid").first
            head_w = head.bounding_box()["width"]
            grid_w = grid.bounding_box()["width"]
            head_ratio = head_w / (head_w + grid_w)
            add(f"2.{name}) head column is narrow (auto)",
                head_ratio < 0.5,
                f"head={head_w:.0f}px grid={grid_w:.0f}px ratio={head_ratio:.2f}")

            head_h = head.bounding_box()["height"]
            first_item_h = items.first.bounding_box()["height"]
            add(f"2.{name}) item height not 2x > head height",
                first_item_h <= head_h * 1.5,
                f"head={head_h:.0f}px item={first_item_h:.0f}px")
        ctx.close()

    print("\n=== CHECK 3: gold footer has spacing from chart card above ===")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.on("pageerror", lambda e: page_errors.append(("gold-margin", str(e))))
    page.goto(f"{BASE}/gold-allocation-page", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    chart_card = page.locator(".gold-chart-grid").first
    footer = page.locator(".governance-ledger--gold").first
    chart_box = chart_card.bounding_box()
    footer_box = footer.bounding_box()
    gap = footer_box["y"] - (chart_box["y"] + chart_box["height"])
    add("3) gold footer has >8px gap above",
        gap > 8,
        f"chart_bottom={chart_box['y']+chart_box['height']:.0f} footer_top={footer_box['y']:.0f} gap={gap:.0f}px")

    footer_margin = footer.evaluate("el => getComputedStyle(el).marginTop")
    add("3b) gold footer computed margin-top > 0",
        footer_margin != "0px", f"margin-top={footer_margin}")
    ctx.close()

    browser.close()

print("\n=== SUMMARY ===")
total_pass = sum(1 for r in results if r["ok"])
total_fail = sum(1 for r in results if not r["ok"])
print(f"  {total_pass} passed, {total_fail} failed")
print(f"  console errors: {len(console_errors)}")
print(f"  page errors: {len(page_errors)}")
if console_errors:
    print("  --- console errors ---")
    for src, msg in console_errors[:10]:
        print(f"    [{src}] {msg[:200]}")
if page_errors:
    print("  --- page errors ---")
    for src, msg in page_errors[:10]:
        print(f"    [{src}] {msg[:200]}")

sys.exit(0 if total_fail == 0 and not page_errors else 1)