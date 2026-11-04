#!/usr/bin/env python3
"""Runs every few minutes: spots clips that have gone live, submits them to Content Rewards, and says when anything goes wrong."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import notify
import state as st
import tiktok

SITE = "https://contentrewards.com"
WINDOW = 29 * 60            # Content Rewards takes clips posted in the last 30 minutes; allow a minute to get there
IGNORE_AFTER = 6 * 3600     # older than this was already here before the helper looked, so say nothing


class NotSignedIn(Exception):
    pass


def _tag(c):
    tags = [str(t) for t in (c.get("hashtags") or []) if str(t).strip()]
    return tags[0] if tags else "#" + re.sub(r"[^a-z0-9]", "", str(c.get("name", "")).lower())


def match_campaign(caption, campaigns):
    """The campaign whose hashtag is in this caption."""
    words = {w.lower() for w in re.findall(r"#\w+", caption or "")}
    return next((c for c in campaigns if _tag(c).lower() in words), None)


def decide(video, campaign, now, state):
    """submit, too_late, no_campaign or done."""
    age = now - video["created"]
    if video["id"] in state["submitted"] or age > IGNORE_AFTER:
        return "done"
    if campaign is None:
        return "no_campaign"
    return "submit" if age <= WINDOW else "too_late"


def _once(key, text, state, alert):
    if key not in state["alerted"]:
        state["alerted"].append(key)
        alert(text)


def handle(video, campaigns, now, state, submit, alert, dry_run=False):
    """Does whatever this video needs. `submit(campaign, link)` returns (ok, message)."""
    camp = match_campaign(video["caption"], campaigns)
    action = decide(video, camp, now, state)
    vid, link = video["id"], video["url"]
    if action == "too_late":
        _once("late-" + vid, f"Too late to submit automatically: more than 30 minutes have passed. Try it by hand: {link}", state, alert)
    elif action == "no_campaign":
        _once("nocamp-" + vid, f"A new video has no campaign hashtag, so I didn't submit it: {link}", state, alert)
    elif action == "submit" and dry_run:
        _once("dry-" + vid, f"Would submit to {camp['name']}: {link}", state, alert)
    elif action == "submit":
        try:
            ok, msg = submit(camp, link)
        except NotSignedIn:
            _once("signed-out", "Content Rewards has signed me out. Sign in on the laptop and tell Claude to refresh the helper.", state, alert)
            _once("hand-" + vid, f"Submit this by hand within 30 minutes ({camp['name']}): {link}", state, alert)
            return
        if ok or "already" in msg.lower():
            state["submitted"].append(vid)
            if ok:
                alert(f"Submitted to {camp['name']}: {link}")
        else:
            _once("refused-" + vid, f"{msg}. Clip: {link}", state, alert)


_SUBMIT_JS = """async ([campaignId, url]) => {
  const r = await fetch('/api/submission/submissions', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({campaignId, url})});
  let body = null;
  try { body = await r.json(); } catch (e) {}
  return Object.assign({status: r.status}, body || {success: r.ok});
}"""


def _reason(res):
    err = res.get("error")
    if isinstance(err, dict):
        err = err.get("message") or err.get("code")
    return str(res.get("message") or err or res.get("code") or f"it answered {res.get('status', '?')}")


def browser_submit(campaign, link):
    """Sends one link from a signed-in page, the same request the site makes. Installs the browser only when a clip needs it."""
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True, capture_output=True)
    from playwright.sync_api import sync_playwright
    m = re.search(r"/campaigns/([0-9a-f-]{36})", str(campaign.get("submit_url", "")))
    if not m:
        return False, f"{campaign.get('name')} has no Content Rewards link saved"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(os.environ["CR_STATE"])
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_context(storage_state=f.name, viewport={"width": 1100, "height": 800}).new_page()
            page.goto(SITE + "/c/home", wait_until="load", timeout=60000)
            page.wait_for_timeout(4000)
            if "/login" in page.url or page.evaluate("() => !!document.querySelector('a[href^=\"/login\"]')"):
                raise NotSignedIn()
            res = page.evaluate(_SUBMIT_JS, [m.group(1), link]) or {}
            br.close()
    finally:
        os.unlink(f.name)
    return (True, "submitted") if res.get("success") else (False, "Content Rewards said no: " + _reason(res))


def main():
    key = os.environ["STATE_KEY"]
    dry = os.environ.get("DRY_RUN", "") == "1"
    data = st.load(key)
    data.setdefault("submitted", [])
    data.setdefault("alerted", [])
    keys = (os.environ.get("TIKTOK_CLIENT_KEY", ""), os.environ.get("TIKTOK_CLIENT_SECRET", ""))
    now = time.time()
    for account in data.get("accounts", []):
        try:
            videos = tiktok.live_videos(account, now, keys)
        except Exception as e:
            _once(f"tiktok-{account.get('name')}-{time.strftime('%Y%m%d')}", f"Couldn't check {account.get('name')} on TikTok today ({e}). Clips may need submitting by hand.", data, notify.send)
            continue
        for v in videos:
            handle(v, data.get("campaigns", []), now, data, browser_submit, notify.send, dry_run=dry)
    data["submitted"] = data["submitted"][-500:]
    data["alerted"] = data["alerted"][-500:]
    st.save(data, key)
    print(json.dumps({"accounts": len(data.get("accounts", [])), "submitted_total": len(data["submitted"]), "dry_run": dry}))


if __name__ == "__main__":
    main()
