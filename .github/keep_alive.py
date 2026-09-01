"""Visits the app with a real browser so Streamlit Cloud counts it as traffic.

A plain HTTP request only fetches the static page shell — Streamlit only
resets its "still active" timer once a browser actually opens a live
connection and renders the UI. This script does that with headless
Chromium, and also handles the "this app has gone to sleep" wake screen
if it shows up.
"""

import sys

from playwright.sync_api import sync_playwright

APP_URL = "https://lmm-chat-f3qmntr5ekqne2pv5zgmox.streamlit.app/"
WAKE_BUTTON_TEXT = "get this app back up"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        print(f"Opening {APP_URL}")
        page.goto(APP_URL, wait_until="load", timeout=60_000)
        page.wait_for_timeout(5_000)

        wake_button = page.get_by_role("button", name=WAKE_BUTTON_TEXT, exact=False)
        if wake_button.count() > 0:
            print("App was asleep, clicking wake-up button")
            wake_button.first.click()
            page.wait_for_timeout(90_000)

        title = page.title()
        print(f"Loaded page, title: {title!r}")
        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
