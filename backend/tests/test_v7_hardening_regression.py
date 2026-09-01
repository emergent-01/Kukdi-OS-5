"""V7 regression suite for the behavior-preserving hardening pass.

Covers touched backend areas:
  - ai_engine.converse (`data = {}` default before JSON parse) via /api/conversation/*
  - routes/reminders.py `_days_until_birthday` (`this_year = None` default) via /api/reminders
  - reflection weekly, people, knowledge, stories, dream-offer smoke.
"""
import json
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- health ----------------
class TestHealth:
    def test_root_api(self, client):
        r = client.get(f"{API}/", timeout=30)
        assert r.status_code == 200, r.text


# ---------------- ai_engine.converse regression ----------------
class TestConversation:
    def test_message_returns_contract(self, client):
        r = client.post(
            f"{API}/conversation/message",
            json={"text": "Please remember that I rehearse answers out loud before interviews"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert '"_id"' not in json.dumps(d)
        for k in ("conversation_id", "reply", "candidates", "detected_state"):
            assert k in d, f"missing {k}: {d}"
        assert isinstance(d["conversation_id"], str) and d["conversation_id"]
        reply = d["reply"]
        reply_text = reply["text"] if isinstance(reply, dict) else reply
        assert isinstance(reply_text, str) and len(reply_text.strip()) > 10
        assert isinstance(d["candidates"], list)
        for c in d["candidates"]:
            assert c.get("title")
            assert "type" in c and "confidence" in c
            assert isinstance(c["confidence"], (int, float))
        pytest.candidate_count = len(d["candidates"])

    def test_message_follow_up_same_conversation(self, client):
        first = client.post(
            f"{API}/conversation/message",
            json={"text": "I am preparing for product management interviews."},
            timeout=180,
        )
        assert first.status_code == 200, first.text
        cid = first.json()["conversation_id"]
        second = client.post(
            f"{API}/conversation/message",
            json={"text": "What should I focus on next?", "conversation_id": cid},
            timeout=180,
        )
        assert second.status_code == 200, second.text
        assert second.json()["conversation_id"] == cid
        r2 = second.json()["reply"]
        r2_text = r2["text"] if isinstance(r2, dict) else r2
        assert len(r2_text.strip()) > 5

    def test_stream_sse_events(self, client):
        with client.post(
            f"{API}/conversation/stream",
            json={"text": "Remember that I journal every Sunday evening."},
            stream=True,
            timeout=240,
        ) as r:
            assert r.status_code == 200, r.text
            events = []
            tokens = 0
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                t = obj.get("type")
                events.append(t)
                if t == "token":
                    tokens += 1
                if t == "done":
                    break
        assert "meta" in events, events[:20]
        assert tokens > 0, f"no token events: {events[:20]}"
        assert "candidates" in events, events
        assert "done" in events, events


# ---------------- reminders regression ----------------
class TestReminders:
    def test_list_reminders_shape_and_seeded(self, client):
        r = client.get(f"{API}/reminders", timeout=60)
        assert r.status_code == 200, r.text
        rem = r.json()["reminders"]
        assert isinstance(rem, list) and len(rem) > 0
        for x in rem:
            for k in ("id", "kind", "title", "detail", "days", "priority"):
                assert k in x, f"{k} missing in {x}"
        titles = " | ".join(x["title"] for x in rem)
        assert "Marketing case submission" in titles, titles
        assert "Google APM case round" in titles, titles
        kinds = {x["kind"] for x in rem}
        assert "next-step" in kinds, kinds
        # sorted by (-priority, days)
        keys = [(-x["priority"], x["days"]) for x in rem]
        assert keys == sorted(keys)

    def test_relative_detail_for_deadline(self, client):
        rem = client.get(f"{API}/reminders", timeout=60).json()["reminders"]
        dl = [x for x in rem if "Marketing case submission" in x["title"]][0]
        assert dl["detail"] in ("Today", "Tomorrow") or dl["detail"].startswith("In ")

    def test_snooze_hides_then_dismiss(self, client):
        rem = client.get(f"{API}/reminders", timeout=60).json()["reminders"]
        target = [x for x in rem if x["kind"] == "next-step"]
        if not target:
            pytest.skip("no next-step reminder available")
        rid = target[0]["id"]
        s = client.post(f"{API}/reminders/snooze", json={"id": rid}, timeout=60)
        assert s.status_code == 200, s.text
        after = s.json()["reminders"]
        assert rid not in [x["id"] for x in after], "snoozed id still present"
        # dismiss another one
        rem2 = [x for x in after if x["kind"] == "next-step"]
        if rem2:
            rid2 = rem2[0]["id"]
            d = client.post(f"{API}/reminders/dismiss", json={"id": rid2}, timeout=60)
            assert d.status_code == 200, d.text
            assert rid2 not in [x["id"] for x in d.json()["reminders"]]

    def test_birthday_parsing_month_day_and_iso(self, client):
        """Create people with 'Month Day', ISO 'YYYY-MM-DD' and 'MM-DD' birthdays a
        few days out and assert each yields a birthday reminder; then clean up."""
        from datetime import datetime, timedelta, timezone
        target = (datetime.now(timezone.utc).date() + timedelta(days=4))
        month_name = target.strftime("%B")
        formats = {
            "TEST_MonthDay": f"{month_name} {target.day}",
            "TEST_ISO": target.replace(year=1999).isoformat(),
            "TEST_MMDD": f"{target.month:02d}-{target.day:02d}",
        }
        created = []
        try:
            for name, bday in formats.items():
                c = client.post(f"{API}/people", json={"name": name, "birthday": bday}, timeout=60)
                assert c.status_code in (200, 201), c.text
                created.append(c.json()["id"])
            rem = client.get(f"{API}/reminders", timeout=60).json()["reminders"]
            bmap = {x["title"]: x for x in rem if x["kind"] == "birthday"}
            for name in formats:
                key = f"{name}'s birthday"
                assert key in bmap, f"{name} ({formats[name]}) produced no reminder; got {list(bmap)}"
                assert bmap[key]["detail"] == "In 4 days", bmap[key]
        finally:
            for pid in created:
                client.delete(f"{API}/people/{pid}", timeout=60)
        rem = client.get(f"{API}/reminders", timeout=60).json()["reminders"]
        assert not [x for x in rem if x["title"].startswith("TEST_")]

    def test_birthday_invalid_string_no_crash(self, client):
        c = client.post(f"{API}/people", json={"name": "TEST_BadBday", "birthday": "not-a-date"}, timeout=60)
        assert c.status_code in (200, 201), c.text
        pid = c.json()["id"]
        try:
            r = client.get(f"{API}/reminders", timeout=60)
            assert r.status_code == 200, r.text
            assert not [x for x in r.json()["reminders"] if "TEST_BadBday" in x["title"]]
        finally:
            client.delete(f"{API}/people/{pid}", timeout=60)


# ---------------- reflection ----------------
class TestReflection:
    def test_weekly(self, client):
        r = client.get(f"{API}/reflection/weekly", timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("reflection", "stats", "cached"):
            assert k in d, d
        assert isinstance(d["reflection"], str) and len(d["reflection"].strip()) > 20
        assert isinstance(d["stats"], dict)
        assert isinstance(d["cached"], bool)


# ---------------- people ----------------
class TestPeople:
    def test_seeded_people_with_important(self, client):
        r = client.get(f"{API}/people", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        people = body["people"] if isinstance(body, dict) else body
        names = [p["name"] for p in people]
        for expected in ("Ananya", "Rohan Mehta", "Prof. Nair", "Mom"):
            assert any(expected in n for n in names), names
        assert any(p.get("important") for p in people), "no person has important items"
        assert '"_id"' not in json.dumps(people)

    def test_create_and_delete(self, client):
        c = client.post(
            f"{API}/people",
            json={"name": "TEST_Person", "relation": "friend", "important": ["likes tea"]},
            timeout=60,
        )
        assert c.status_code in (200, 201), c.text
        pid = c.json()["id"]
        body = client.get(f"{API}/people", timeout=60).json()
        people = body["people"] if isinstance(body, dict) else body
        found = [p for p in people if p["id"] == pid]
        assert found and found[0]["important"] == ["likes tea"]
        d = client.delete(f"{API}/people/{pid}", timeout=60)
        assert d.status_code in (200, 204), d.text
        body = client.get(f"{API}/people", timeout=60).json()
        people = body["people"] if isinstance(body, dict) else body
        assert pid not in [p["id"] for p in people]


# ---------------- smoke: dream offer, memory, knowledge, stories ----------------
class TestSmoke:
    def test_dream_offer_overview(self, client):
        r = client.get(f"{API}/dream/overview", timeout=120)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), dict) and r.json()
        c = client.get(f"{API}/dream/countdown", timeout=120)
        assert c.status_code == 200, c.text

    def test_memory_list(self, client):
        r = client.get(f"{API}/memory", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("memories", body.get("items")) if isinstance(body, dict) else body
        assert isinstance(items, list)

    def test_knowledge_list_and_search(self, client):
        r = client.get(f"{API}/knowledge", timeout=60)
        assert r.status_code == 200, r.text
        s = client.post(f"{API}/knowledge/search", json={"question": "interview preparation"}, timeout=180)
        assert s.status_code == 200, s.text
        assert isinstance(s.json(), dict)

    def test_stories_list_coverage_match(self, client):
        r = client.get(f"{API}/stories", timeout=60)
        assert r.status_code == 200, r.text
        cov = client.get(f"{API}/stories/coverage", timeout=60)
        assert cov.status_code == 200, cov.text
        m = client.post(
            f"{API}/stories/match",
            json={"question": "Tell me about a time you led a team through ambiguity"},
            timeout=240,
        )
        assert m.status_code == 200, m.text
        assert isinstance(m.json(), dict)
