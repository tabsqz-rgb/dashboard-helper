import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "helper"))

import watch


def sub(status="pending", note=None, name="Marlon"):
    return {"status": status, "name": name, "url": "https://www.tiktok.com/@me/video/1", "note": note}


def snap(subs=None, camps=None):
    return {"submissions": subs or {}, "campaigns": camps or {}}


def camp(paid=100, budget=1000, end=None):
    return {"name": "Marlon", "paid": paid, "budget": budget, "end_date": end}


def test_new_rejection_alerted_with_reason():
    out = watch.changes(snap({"a": sub()}), snap({"a": sub("rejected", "Potential fake engagement.")}))
    assert len(out) == 1
    assert "Rejected" in out[0] and "Potential fake engagement." in out[0] and "/video/1" in out[0]


def test_same_rejection_not_repeated():
    s = snap({"a": sub("rejected", "x")})
    assert watch.changes(s, s) == []


def test_approval_alerted():
    out = watch.changes(snap({"a": sub()}), snap({"a": sub("approved")}))
    assert "Approved" in out[0]


def test_first_look_at_old_results_says_nothing():
    assert watch.changes({}, snap({"a": sub("rejected", "x")}, {"u": camp(paid=900)})) == []


def test_clip_first_seen_already_rejected_is_alerted_once_history_exists():
    assert "Rejected" in watch.changes(snap(), snap({"b": sub("rejected", "x")}))[0]


def test_new_pending_clip_says_nothing():
    assert watch.changes(snap(), snap({"b": sub()})) == []


def test_end_date_appearing_alerted_once():
    old, new = snap(camps={"u": camp()}), snap(camps={"u": camp(end="2026-12-01T00:00:00.000Z")})
    assert "end date" in watch.changes(old, new)[0]
    assert watch.changes(new, new) == []


def test_budget_crossing_70_alerted_once():
    old, new = snap(camps={"u": camp(paid=700)}), snap(camps={"u": camp(paid=701)})
    assert "70%" in watch.changes(old, new)[0]
    assert watch.changes(new, new) == []


def test_read_campaign_finds_budget_and_end_date():
    html = '\\"budget\\":500000,\\"budgetSpentCents\\":351201,\\"endDate\\":\\"2026-12-01T00:00:00.000Z\\"'
    c = watch.read_campaign(html, "Marlon")
    assert (c["budget"], c["paid"], c["end_date"]) == (5000, 3512.01, "2026-12-01T00:00:00.000Z")


def test_read_campaign_unreadable_gives_none():
    assert watch.read_campaign("<html></html>", "Marlon") is None


def test_read_submissions_simplifies_rows():
    rows = [{"id": "a", "status": "rejected", "campaignName": "Marlon", "rejectionNote": "No", "socialMediaPost": {"postUrl": "https://t/1"}},
            {"id": "b", "status": "approved", "campaignName": "X", "socialMediaPost": None}]
    out = watch.read_submissions(rows)
    assert out["a"] == {"status": "rejected", "name": "Marlon", "url": "https://t/1", "note": "No"}
    assert out["b"]["url"] == ""


def test_unreadable_data_gives_read_error_not_all_clear():
    alerts = []
    state = {"alerted": []}

    def broken():
        raise ValueError("page changed")
    assert watch.check(state, broken, [], lambda u: "", alerts.append) is False
    assert "couldn't read" in alerts[0].lower()
    assert state.get("watch") is None


def test_read_error_alerts_once_a_day():
    alerts = []
    state = {"alerted": []}

    def broken():
        raise ValueError("x")
    watch.check(state, broken, [], lambda u: "", alerts.append)
    watch.check(state, broken, [], lambda u: "", alerts.append)
    assert len(alerts) == 1


def test_check_sends_changes_and_remembers():
    alerts = []
    state = {"alerted": [], "watch": snap({"a": sub()})}
    rows = [{"id": "a", "status": "approved", "campaignName": "Marlon", "socialMediaPost": {"postUrl": "https://t/1"}}]
    assert watch.check(state, lambda: rows, [], lambda u: "", alerts.append) is True
    assert "Approved" in alerts[0]
    assert state["watch"]["submissions"]["a"]["status"] == "approved"


def test_one_unreadable_campaign_keeps_its_old_numbers():
    state = {"alerted": [], "watch": snap(camps={"https://x": camp()})}
    watch.check(state, lambda: [], [{"name": "Marlon", "submit_url": "https://x"}], lambda u: "<html></html>", lambda a: None)
    assert state["watch"]["campaigns"]["https://x"] == camp()
