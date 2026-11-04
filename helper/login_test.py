#!/usr/bin/env python3
"""Checks whether Content Rewards accepts a saved sign-in from a cloud server. Sends nothing, and never prints the sign-in."""
import json
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

SITE = "https://contentrewards.com"
CAMPAIGN = os.environ.get("TEST_CAMPAIGN", "").strip()

CHECK_JS = """async (id) => {
  const r = await fetch('/api/submission/submissions/intake?campaignIds=' + id, {credentials: 'include'});
  const body = await r.json().catch(() => null);
  const row = body && body.data && body.data[0];
  return {status: r.status, intake: row ? row.intake : null};
}"""


def main():
    state = os.environ.get("CR_STATE", "")
    if not state:
        print("No saved sign-in was given to this run.")
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(state)
        path = f.name
    try:
        json.loads(state)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(storage_state=path, viewport={"width": 1100, "height": 800}).new_page()
            page.goto(SITE + "/c/home", wait_until="load", timeout=60000)
            page.wait_for_timeout(4000)
            signed_in = "/login" not in page.url and not page.evaluate("() => !!document.querySelector('a[href^=\"/login\"]')")
            print(f"Page title: {page.title()[:80]}")
            print(f"Signed in: {signed_in}")
            if not signed_in:
                return 1
            result = page.evaluate(CHECK_JS, CAMPAIGN)
            print(f"Campaign check: status {result['status']}, intake {result['intake']} (nothing was sent)")
            browser.close()
            return 0 if result["status"] == 200 else 1
    finally:
        os.unlink(path)


if __name__ == "__main__":
    sys.exit(main())
