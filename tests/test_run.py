import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "helper"))

import notify
import run
import state as st
import tiktok

NOW = 1_800_000_000.0
CAMP = {"name": "Stream House", "hashtags": ["#StreamHouse"], "submit_url": "https://contentrewards.com/c/campaigns/abc"}


def video(age_min=10, caption="so good #StreamHouse #fyp", vid="1"):
    return {"id": vid, "url": f"https://www.tiktok.com/@me/video/{vid}", "created": NOW - age_min * 60, "caption": caption}


def fresh():
    return {"submitted": [], "alerted": []}


def test_decide_submit_inside_window():
    assert run.decide(video(10), CAMP, NOW, fresh()) == "submit"


def test_decide_too_late_after_30_min():
    assert run.decide(video(31), CAMP, NOW, fresh()) == "too_late"


def test_decide_done_when_already_submitted():
    s = fresh()
    s["submitted"].append("1")
    assert run.decide(video(10), CAMP, NOW, s) == "done"


def test_decide_no_campaign():
    assert run.decide(video(10), None, NOW, fresh()) == "no_campaign"


def test_old_videos_from_before_are_ignored():
    assert run.decide(video(60 * 24), CAMP, NOW, fresh()) == "done"


def test_match_campaign_by_hashtag():
    assert run.match_campaign("wow #streamhouse", [CAMP]) == CAMP


def test_match_campaign_by_name_tag_when_none_required():
    c = {"name": "It's Personal Podcast", "hashtags": []}
    assert run.match_campaign("wow #itspersonalpodcast", [c]) == c


def test_match_campaign_needs_a_whole_tag():
    assert run.match_campaign("wow #streamhouses", [CAMP]) is None


def run_one(v, s, submit=None, campaigns=(CAMP,)):
    alerts = []
    run.handle(v, list(campaigns), NOW, s, submit or (lambda c, u: (True, "submitted")), alerts.append)
    return alerts


def test_submit_success_is_recorded_and_alerted():
    s = fresh()
    alerts = run_one(video(), s)
    assert s["submitted"] == ["1"]
    assert "Submitted" in alerts[0]


def test_old_video_not_alerted_twice():
    s = fresh()
    assert len(run_one(video(31), s)) == 1
    assert run_one(video(31), s) == []


def test_too_late_alert_contains_the_link():
    assert "https://www.tiktok.com/@me/video/1" in run_one(video(31), fresh())[0]


def test_duplicate_reply_marks_done():
    s = fresh()
    alerts = run_one(video(), s, submit=lambda c, u: (False, "Content Rewards said no: this link was already submitted"))
    assert s["submitted"] == ["1"]
    assert alerts == []


def test_refused_clip_alerts_with_reason_and_link_once():
    s = fresh()
    refuse = lambda c, u: (False, "Content Rewards said no: account not linked")
    alerts = run_one(video(), s, submit=refuse)
    assert "account not linked" in alerts[0] and "/video/1" in alerts[0]
    assert run_one(video(), s, submit=refuse) == []


def test_expired_login_alerts_once_and_tries_again_later():
    s = fresh()

    def expired(c, u):
        raise run.NotSignedIn()
    a1 = run_one(video(), s, submit=expired)
    a2 = run_one(video(vid="2"), s, submit=expired)
    assert len([a for a in a1 + a2 if "sign in" in a.lower()]) == 1
    assert s["submitted"] == []
    assert "/video/1" in a1[-1] and "/video/2" in a2[-1]


def test_dry_run_sends_nothing(monkeypatch):
    s = fresh()
    called = []
    alerts = []
    run.handle(video(), [CAMP], NOW, s, lambda c, u: called.append(u) or (True, ""), alerts.append, dry_run=True)
    assert called == []
    assert "Would submit" in alerts[0]
    assert s["submitted"] == []


def test_token_rotation_saved():
    acct = {"access_token": "old", "refresh_token": "r1", "expires_at": NOW - 1}
    got = tiktok.token(acct, NOW, ("k", "s"), lambda form: {"access_token": "new", "refresh_token": "r2", "expires_in": 86400})
    assert got == "new"
    assert acct["refresh_token"] == "r2"
    assert acct["expires_at"] > NOW


def test_token_not_refreshed_when_still_good():
    acct = {"access_token": "good", "refresh_token": "r1", "expires_at": NOW + 100}
    assert tiktok.token(acct, NOW, ("k", "s"), None) == "good"


def test_video_rows_read_from_tiktok_answer():
    rows = tiktok.rows({"videos": [{"id": "9", "share_url": "https://www.tiktok.com/@me/video/9?x=1", "create_time": 100, "title": "hi #a"}]})
    assert rows == [{"id": "9", "url": "https://www.tiktok.com/@me/video/9", "created": 100.0, "caption": "hi #a"}]


def test_state_round_trip(tmp_path):
    key = st.new_key()
    p = tmp_path / "state.enc"
    st.save({"a": 1}, key, p)
    assert b'"a"' not in p.read_bytes()
    assert st.load(key, p) == {"a": 1}


def test_state_wrong_key_fails(tmp_path):
    p = tmp_path / "state.enc"
    st.save({"a": 1}, st.new_key(), p)
    with pytest.raises(ValueError):
        st.load(st.new_key(), p)


def test_missing_state_starts_empty(tmp_path):
    assert st.load(st.new_key(), tmp_path / "none.enc") == {}


def test_notify_posts_to_topic(monkeypatch):
    sent = []

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda req, timeout=None: sent.append(req) or R())
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/secret-topic")
    assert notify.send("hello") is True
    assert sent[0].full_url == "https://ntfy.sh/secret-topic"
    assert sent[0].data == b"hello"


def test_notify_without_topic_returns_false(monkeypatch):
    monkeypatch.delenv("NTFY_URL", raising=False)
    assert notify.send("hello") is False


def test_watch_runs_hourly():
    assert run.watch_due({}, NOW) is True
    assert run.watch_due({"watched_at": NOW - 100}, NOW) is False
    assert run.watch_due({"watched_at": NOW - 3600}, NOW) is True
