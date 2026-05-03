"""
wardyati.com — Ultra-Fast Shift Booking Automation (v2 — exact selectors)
==========================================================================
Install:
    pip install playwright aiohttp
    playwright install chromium

Run (visible browser — first time):
    python wardyati_shift_booker.py --no-headless

Run (headless — fastest):
    python wardyati_shift_booker.py
"""

import asyncio
import argparse
import logging
import time
from playwright.async_api import async_playwright, Page, BrowserContext, Request, Response

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
EMAIL    = "Rawan-H-Bassiouny@students.kasralainy.edu.eg"
PASSWORD = "Lamy@1477"

LOGIN_URL = "https://wardyati.com/login/"
ROOM_NAME = "Shifa - May"

PRIORITY_DATES = [23, 26, 27]
FALLBACK_DATE  = 21

POLL_INTERVAL = 0.1
MAX_WAIT_SECS = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wardyati")

captured_api: dict = {}


async def intercept_requests(request: Request):
    url = request.url.lower()
    if any(kw in url for kw in ("register", "shift", "booking", "slot", "enroll", "attend")):
        log.info(f"[API] → {request.method} {request.url}")
        try:
            body = request.post_data
            if body:
                log.info(f"       Body: {body}")
                captured_api.update({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "body": body,
                })
        except Exception:
            pass


async def intercept_responses(response: Response):
    url = response.url.lower()
    if any(kw in url for kw in ("register", "shift", "booking", "slot", "enroll", "attend")):
        try:
            body = await response.text()
            log.info(f"[API] ← {response.status} {response.url}  |  {body[:200]}")
        except Exception:
            pass


async def login(page: Page) -> bool:
    log.info("Navigating to login page …")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)

    try:
        # Email field (avoid the honeypot "nickname" field)
        await page.locator(
            'input[type="email"], input[name="email"], input[type="text"]:not([name="nickname"])'
        ).first.fill(EMAIL, timeout=5000)
        log.info("  ✅ Email filled")

        await page.locator('input[type="password"]').first.fill(PASSWORD, timeout=5000)
        log.info("  ✅ Password filled")

        # Keep honeypot empty
        try:
            await page.locator('input[name="nickname"]').first.fill("", timeout=500)
        except Exception:
            pass

        await page.locator('button[type="submit"], button:has-text("تسجيل الدخول")').first.click(timeout=5000)
        log.info("  ✅ Login button clicked")

        await page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
        log.info("✅ Login successful!")
        return True

    except Exception as e:
        log.error(f"❌ Login failed: {e}")
        try:
            await page.screenshot(path="debug_login_fail.png", full_page=True)
        except Exception:
            pass
        return False


async def navigate_to_room(page: Page) -> bool:
    log.info(f"Looking for room: '{ROOM_NAME}' …")
    await page.wait_for_load_state("domcontentloaded")

    for sel in [
        f'text="{ROOM_NAME}"',
        f'[class*="card"]:has-text("{ROOM_NAME}")',
        f'a:has-text("{ROOM_NAME}")',
        f'div:has-text("{ROOM_NAME}")',
        f':has-text("{ROOM_NAME}")',
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=5000)
                await page.wait_for_load_state("domcontentloaded")
                log.info(f"✅ Room clicked.")
                return True
        except Exception:
            continue

    log.error(f"❌ Room '{ROOM_NAME}' not found.")
    try:
        await page.screenshot(path="debug_room_not_found.png", full_page=True)
    except Exception:
        pass
    return False


async def navigate_to_april_2026(page: Page):
    for _ in range(24):
        header_text = ""
        for h_sel in ['.fc-toolbar-title', '[class*="calendar-header"]',
                      '[class*="month-title"]', 'h2', 'h3']:
            try:
                el = page.locator(h_sel).first
                if await el.count() > 0:
                    header_text = (await el.inner_text(timeout=1000)).strip()
                    if header_text:
                        break
            except Exception:
                continue

        log.info(f"  Calendar: '{header_text}'")

        if ("أبريل" in header_text or "April" in header_text) and "2026" in header_text:
            log.info("✅ April 2026 confirmed.")
            return

        go_forward = True
        if "2027" in header_text or "مايو" in header_text or "May" in header_text:
            go_forward = False

        nav_sel = (
            '.fc-next-button, button[aria-label*="next" i], [class*="next"]'
            if go_forward else
            '.fc-prev-button, button[aria-label*="prev" i], [class*="prev"]'
        )
        try:
            await page.locator(nav_sel).first.click(timeout=2000)
            await asyncio.sleep(0.2)
        except Exception:
            break


async def click_shift_for_date(page: Page, day: int) -> bool:
    log.info(f"  Trying day {day} …")

    for sel in [
        f'[data-date="2026-04-{day:02d}"] .fc-event',
        f'[data-date="2026-04-{day:02d}"] [class*="shift"]',
        f'[data-date="2026-04-{day:02d}"] [class*="event"]',
        f'[data-date="2026-04-{day:02d}"]',
        f'td:has([class*="day-number"]:text-is("{day}")) .fc-event',
        f'[class*="day"]:has-text("{day}") [class*="shift"]',
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() == 0:
                continue
            text = await el.inner_text(timeout=800)
            if any(kw in text for kw in ("full", "ممتلئ", "0 slots", "مكتمل")):
                log.info(f"  Day {day} FULL — skip.")
                return False
            await el.click(timeout=3000)
            log.info(f"  ✅ Day {day} clicked.")
            return True
        except Exception:
            continue

    return False


async def confirm_registration(page: Page) -> bool:
    log.info("  Confirming …")
    for sel in [
        'button:has-text("تسجيل")',
        'button:has-text("تأكيد")',
        'button:has-text("Confirm")',
        'button:has-text("Register")',
        'button:has-text("حجز")',
        '[role="dialog"] button:not([class*="cancel"]):not([class*="close"])',
        'button[class*="confirm"]',
        'button[class*="primary"]',
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=3000)
                log.info(f"  ✅ Confirmed.")
                await asyncio.sleep(0.8)
                return True
        except Exception:
            continue

    log.error("  ❌ Confirm button not found.")
    try:
        await page.screenshot(path="debug_confirm_fail.png", full_page=True)
    except Exception:
        pass
    return False


async def book_shift(page: Page) -> bool:
    all_dates = PRIORITY_DATES + [FALLBACK_DATE]
    deadline = time.time() + MAX_WAIT_SECS

    while time.time() < deadline:
        await navigate_to_april_2026(page)

        for day in all_dates:
            if await click_shift_for_date(page, day):
                if await confirm_registration(page):
                    log.info(f"🎉 BOOKED — April {day}, 2026!")
                    if captured_api:
                        log.info(f"  API URL : {captured_api.get('url')}")
                        log.info(f"  API Body: {captured_api.get('body')}")
                    return True

        log.info(f"Retrying in {POLL_INTERVAL}s …")
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(POLL_INTERVAL)

    log.error("⏰ Timed out.")
    return False


async def main(headless: bool):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-extensions", "--disable-background-networking"],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            java_script_enabled=True,
        )

        # Block images/fonts for speed
        await context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,otf}",
            lambda route: route.abort()
        )

        page = await context.new_page()
        page.on("request",  lambda req:  asyncio.ensure_future(intercept_requests(req)))
        page.on("response", lambda resp: asyncio.ensure_future(intercept_responses(resp)))

        if not await login(page):
            await browser.close()
            return

        if not await navigate_to_room(page):
            await browser.close()
            return

        await book_shift(page)
        await browser.close()
        log.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wardyati Shift Booker v2")
    parser.add_argument("--no-headless", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(headless=not args.no_headless))
