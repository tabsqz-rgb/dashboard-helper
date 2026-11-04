"""Reads which videos are live on a linked TikTok account."""
import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://open.tiktokapis.com"


def _token_request(form):
    req = urllib.request.Request(API + "/v2/oauth/token/", urllib.parse.urlencode(form).encode(),
                                 {"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def token(account, now, keys, request=_token_request):
    """A working access token. TikTok can replace the refresh token each time, so `account` is updated for saving."""
    if now < account.get("expires_at", 0):
        return account["access_token"]
    data = request({"client_key": keys[0], "client_secret": keys[1], "grant_type": "refresh_token", "refresh_token": account["refresh_token"]})
    if "access_token" not in data:
        raise RuntimeError(data.get("error_description") or data.get("error") or "TikTok refused the login")
    account.update(access_token=data["access_token"], refresh_token=data.get("refresh_token", account["refresh_token"]),
                   expires_at=now + int(data.get("expires_in", 86000)) - 300)
    return account["access_token"]


def rows(answer):
    """TikTok's video list in the shape the helper uses."""
    return [{"id": str(v["id"]), "url": str(v.get("share_url", "")).split("?")[0], "created": float(v.get("create_time", 0)),
             "caption": v.get("title") or v.get("video_description") or ""} for v in answer.get("videos") or []]


def live_videos(account, now, keys):
    """The account's most recent videos."""
    tok = token(account, now, keys)
    req = urllib.request.Request(API + "/v2/video/list/?fields=id,create_time,title,share_url", json.dumps({"max_count": 20}).encode(),
                                 {"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return rows(json.load(r).get("data") or {})
