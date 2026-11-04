"""Watches your submissions and joined campaigns for news: approvals, rejections, end dates and budgets passing 70%."""
import re
import time

USED_LIMIT = 0.70


def read_submissions(rows):
    """Content Rewards' submission rows, cut down to what the alerts need."""
    return {r["id"]: {"status": r.get("status"), "name": r.get("campaignName", ""), "url": (r.get("socialMediaPost") or {}).get("postUrl", ""),
                      "note": r.get("rejectionNote")} for r in rows}


def read_campaign(html, name):
    """A campaign's budget, money spent and end date from its page, or None if the page can't be read."""
    raw = html.replace('\\"', '"')
    budget = re.search(r'"budget":(\d+)', raw)
    spent = re.search(r'"budgetSpentCents":(\d+)', raw)
    if not budget or not spent:
        return None
    end = re.search(r'"(?:endDate|endsAt|endAt|expiresAt|deadline)":"([^"]{4,40})"', raw)
    return {"name": name, "budget": int(budget.group(1)) / 100, "paid": int(spent.group(1)) / 100, "end_date": end.group(1) if end else None}


def _used(c):
    return c["paid"] / c["budget"] if c.get("budget") else 0


def changes(old, new):
    """Alerts for what's different since last time. The very first look only takes notes, so old results don't all arrive at once."""
    if not old:
        return []
    out = []
    before = old.get("submissions", {})
    for sid, s in new.get("submissions", {}).items():
        if before.get(sid, {}).get("status") == s["status"]:
            continue
        if s["status"] == "approved":
            out.append(f"Approved on {s['name']}: {s['url']}")
        elif s["status"] == "rejected":
            out.append(f"Rejected on {s['name']}: {s.get('note') or 'no reason given'}\n{s['url']}")
    was = old.get("campaigns", {})
    for url, c in new.get("campaigns", {}).items():
        prev = was.get(url)
        if not prev:
            continue
        if c.get("end_date") and not prev.get("end_date"):
            out.append(f"{c['name']} now has an end date: {c['end_date'][:10]}")
        if _used(c) > USED_LIMIT >= _used(prev):
            out.append(f"{c['name']} has used over 70% of its budget, so it could fill up soon.")
    return out


def check(state, read_rows, campaigns, fetch, alert):
    """Takes a fresh look and sends any news. Returns False if it couldn't read Content Rewards, which is never treated as "nothing new"."""
    try:
        subs = read_submissions(read_rows())
    except Exception as e:
        key = "watch-read-" + time.strftime("%Y%m%d")
        if key not in state["alerted"]:
            state["alerted"].append(key)
            alert(f"I couldn't read your Content Rewards results today ({e}), so check them on the site.")
        return False
    old = state.get("watch") or {}
    known = dict(old.get("campaigns", {}))
    for c in campaigns:
        url = c.get("submit_url")
        if not url:
            continue
        try:
            found = read_campaign(fetch(url), c.get("name", ""))
        except Exception:
            found = None
        if found:
            known[url] = found
    new = {"submissions": subs, "campaigns": known}
    for text in changes(old, new):
        alert(text)
    state["watch"] = new
    return True
