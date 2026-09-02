"""Day One Intake feature tests (POST /api/intake/commit, GET /api/intake/status)
plus propagation into calendar/stories/dream/people. All test-created data is
cleaned up and any confirmed candidate is reset to prep_group=false.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

PREFIX = "ZZ_TEST_"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created(client):
    """Track created ids for teardown: {'events': [], 'stories': [], 'prep': [], 'people': []}"""
    bag = {"events": [], "stories": [], "prep": [], "people": [], "reset_people": []}
    yield bag
    for eid in bag["events"]:
        client.delete(f"{BASE_URL}/api/calendar/{eid}")
    for sid in bag["stories"]:
        client.delete(f"{BASE_URL}/api/stories/{sid}")
    for pid in bag["prep"]:
        client.delete(f"{BASE_URL}/api/dream/prep/{pid}")
    for pid in bag["people"]:
        client.delete(f"{BASE_URL}/api/people/{pid}")
    if bag["reset_people"]:
        client.post(f"{BASE_URL}/api/intake/commit", json={
            "people_updates": [
                {"id": pid, "prep_group": False, "strengths": [], "strength_note": ""}
                for pid in bag["reset_people"]
            ]
        })


def _no_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"_id leaked: {list(obj.keys())}"
        for v in obj.values():
            _no_id(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_id(v)


# ----- baseline / preload ---------------------------------------------------

class TestBaseline:
    def test_status_shape(self, client):
        r = client.get(f"{BASE_URL}/api/intake/status")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("has_real_data"), bool)

    def test_preloaded_candidates_and_companies(self, client):
        r = client.get(f"{BASE_URL}/api/people")
        assert r.status_code == 200
        people = r.json()["people"]
        _no_id(r.json())
        cands = [p for p in people if p.get("prep_candidate")]
        assert len(cands) >= 12, f"expected >=12 prep candidates, got {len(cands)}"
        assert all(p["relation"] == "Peer / prep group" for p in cands)

        r2 = client.get(f"{BASE_URL}/api/dream/overview")
        assert r2.status_code == 200
        assert len(r2.json()["companies"]) >= 14


# ----- commit ---------------------------------------------------------------

class TestCommit:
    def test_empty_commit_succeeds(self, client):
        r = client.post(f"{BASE_URL}/api/intake/commit", json={})
        assert r.status_code == 200
        d = r.json()
        assert d["committed"] is True
        assert d["counts"] == {"events": 0, "stories": 0, "prep_items": 0, "mentors": 0, "people_updated": 0}

    def test_full_commit_and_propagation(self, client, created):
        cands = [p for p in client.get(f"{BASE_URL}/api/people").json()["people"] if p.get("prep_candidate")]
        target = cands[0]
        payload = {
            "events": [
                {"title": f"{PREFIX}Interview", "start": "2026-08-01T10:00:00+00:00", "type": "placement"},
                {"title": f"{PREFIX}BadType", "start": "2026-08-02T10:00:00+00:00", "type": "nonsense"},
                {"title": "   ", "start": "2026-08-03T10:00:00+00:00", "type": "event"},
            ],
            "stories": [
                {"title": f"{PREFIX}Story", "situation": "s"},
                {"title": ""},
            ],
            "prep_items": [
                {"title": f"{PREFIX}Prep", "category": "framework"},
                {"title": f"{PREFIX}PrepBadCat", "category": "zzz"},
                {"title": ""},
            ],
            "mentors": [{"name": f"{PREFIX}Mentor"}, {"name": "  "}],
            "people_updates": [
                {"id": target["id"], "prep_group": True,
                 "strengths": ["Leadership", "bogus"], "strength_note": f"{PREFIX}note"},
                {"id": "does-not-exist-000", "prep_group": True},
            ],
        }
        r = client.post(f"{BASE_URL}/api/intake/commit", json=payload)
        assert r.status_code == 200
        d = r.json()
        _no_id(d)
        assert d["committed"] is True
        assert d["counts"] == {"events": 2, "stories": 1, "prep_items": 2, "mentors": 1, "people_updated": 1}, d["counts"]

        # calendar propagation + event type validation
        cal = client.get(f"{BASE_URL}/api/calendar")
        assert cal.status_code == 200
        _no_id(cal.json())
        evs = [e for e in cal.json()["events"] if e["title"].startswith(PREFIX)]
        created["events"] = [e["id"] for e in evs]
        assert len(evs) == 2
        by_title = {e["title"]: e for e in evs}
        assert by_title[f"{PREFIX}Interview"]["type"] == "placement"
        assert by_title[f"{PREFIX}BadType"]["type"] == "event"

        # stories propagation
        st = client.get(f"{BASE_URL}/api/stories")
        assert st.status_code == 200
        _no_id(st.json())
        mine = [s for s in st.json()["stories"] if s["title"].startswith(PREFIX)]
        created["stories"] = [s["id"] for s in mine]
        assert len(mine) == 1
        assert mine[0]["status"] == "draft"

        # prep propagation + category validation
        ov = client.get(f"{BASE_URL}/api/dream/overview")
        assert ov.status_code == 200
        _no_id(ov.json())
        all_prep = [p for items in ov.json()["prep_by_category"].values() for p in items]
        preps = [p for p in all_prep if p["title"].startswith(PREFIX)]
        created["prep"] = [p["id"] for p in preps]
        assert len(preps) == 2
        cats = {p["title"]: p["category"] for p in preps}
        assert cats[f"{PREFIX}Prep"] == "framework"
        assert cats[f"{PREFIX}PrepBadCat"] == "roadmap"

        # mentors + confirmed candidate
        ppl = client.get(f"{BASE_URL}/api/people").json()["people"]
        mentors = [p for p in ppl if p["name"].startswith(PREFIX)]
        created["people"] = [p["id"] for p in mentors]
        assert len(mentors) == 1
        assert mentors[0]["relation"] == "Mentor"

        confirmed = next(p for p in ppl if p["id"] == target["id"])
        created["reset_people"] = [target["id"]]
        assert confirmed["prep_group"] is True
        assert confirmed["strengths"] == ["Leadership"], confirmed["strengths"]
        assert confirmed["strength_note"] == f"{PREFIX}note"

    def test_status_true_after_commit(self, client, created):
        r = client.get(f"{BASE_URL}/api/intake/status")
        assert r.status_code == 200
        assert r.json()["has_real_data"] is True
