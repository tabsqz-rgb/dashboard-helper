"""Sends a phone notification through ntfy. The topic in NTFY_URL is random and kept secret."""
import os
import urllib.request


def send(text, url=None):
    """Returns True if it went, False (never an exception) if it didn't."""
    url = url or os.environ.get("NTFY_URL", "").strip()
    if not url:
        return False
    req = urllib.request.Request(url, str(text)[:3500].encode("utf-8"), {"Title": "Dashboard", "User-Agent": "dashboard-helper/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception:
        return False
