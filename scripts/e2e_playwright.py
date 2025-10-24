"""Minimal end-to-end browser test using Playwright.

Usage:
    python scripts/e2e_playwright.py https://your-app.azurecontainerapps.io

Only one argument is accepted: the base URL of the deployed app.
No environment variables or azd lookups are performed.
"""
import sys

from playwright.sync_api import Playwright, sync_playwright


def run_test(pw: Playwright, base_url: str) -> None:
    headless = True
    browser = pw.chromium.launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()

    if not base_url.startswith("http"):
        raise ValueError("Base URL must start with http/https")
    base_url = base_url.rstrip("/")

    url = base_url
    if not url.endswith("/"):
        url += "/"
    print(f"Navigating to {url}")
    page.goto(url, wait_until="domcontentloaded")

    # Search for an image and assert an image is returned
    page.get_by_role("textbox", name="Enter a search term...").click()
    page.get_by_role("textbox", name="Enter a search term...").fill("tree")
    page.get_by_role("button", name="Search button").click()
    page.locator(".ReactGridGallery_tile-viewport > img").first.click()

    # Cleanup
    context.close()
    browser.close()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/e2e_chat_playwright.py <base_url>", file=sys.stderr)
        return 1
    base_url = sys.argv[1]
    try:
        with sync_playwright() as pw:
            run_test(pw, base_url)
        print("Playwright E2E test succeeded.")
        return 0
    except Exception as e:  # broad for CLI convenience
        print(f"Playwright E2E test failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())