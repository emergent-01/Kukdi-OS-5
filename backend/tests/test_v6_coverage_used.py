"""V6 Story Bank additive tests: coverage, mark-used, match regression, story CRUD."""
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

EXPECTED_COMPETENCIES = [
    "Leadership", "Ambiguity", "Failure", "Conflict", "Influence",
    "Execution", "Analytical Thinking", "Customer Focus",
]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(client, created_ids):
    yield
    for sid in created_ids:
        client.delete(f"{API}/stories/{sid}", timeout=30)


# ----- COVERAGE -----
class TestCoverage:
    def test_coverage_shape(self, client):
        r = client.get(f"{API}/stories/coverage", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["competencies"] == EXPECTED_COMPETENCIES
        assert set(d["counts"].keys()) == set(EXPECTED_COMPETENCIES)
        assert all(isinstance(v, int) for v in d["counts"].values())
        # missing/thin consistent with counts
        assert d["missing"] == [c for c in EXPECTED_COMPETENCIES if d["counts"][c] == 0]
        assert d["thin"] == [c for c in EXPECTED_COMPETENCIES if d["counts"][c] == 1]

    def test_coverage_reacts_to_new_story(self, client, created_ids):
        before = client.get(f"{API}/stories/coverage", timeout=30).json()
        # pick a competency currently missing, else fall back to Ambiguity
        target = before["missing"][0] if before["missing"] else "Ambiguity"
        r = client.post(f"{API}/stories", json={
            "title": "TEST_coverage_probe", "situation": "s", "themes": [target.lower()],
        }, timeout=30)
        assert r.status_code == 200, r.text
        created_ids.append(r.json()["id"])
        after = client.get(f"{API}/stories/coverage", timeout=30).json()
        assert after["counts"][target] == before["counts"][target] + 1
        assert target not in after["missing"]

    def test_coverage_substring_theme_match(self, client, created_ids):
        before = client.get(f"{API}/stories/coverage", timeout=30).json()
        r = client.post(f"{API}/stories", json={
            "title": "TEST_substring_probe", "themes": ["analytical"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        created_ids.append(r.json()["id"])
        after = client.get(f"{API}/stories/coverage", timeout=30).json()
        assert after["counts"]["Analytical Thinking"] == before["counts"]["Analytical Thinking"] + 1

    def test_coverage_not_stored(self, client):
        """Coverage is computed live: deleting a probe story reverts counts."""
        before = client.get(f"{API}/stories/coverage", timeout=30).json()
        r = client.post(f"{API}/stories", json={"title": "TEST_live_probe", "themes": ["Conflict"]}, timeout=30)
        sid = r.json()["id"]
        mid = client.get(f"{API}/stories/coverage", timeout=30).json()
        assert mid["counts"]["Conflict"] == before["counts"]["Conflict"] + 1
        client.delete(f"{API}/stories/{sid}", timeout=30)
        after = client.get(f"{API}/stories/coverage", timeout=30).json()
        assert after["counts"]["Conflict"] == before["counts"]["Conflict"]


# ----- MARK AS USED -----
class TestMarkUsed:
    @pytest.fixture(scope="class")
    def story_id(self, client, created_ids):
        r = client.post(f"{API}/stories", json={
            "title": "TEST_mark_used_story", "situation": "sit", "themes": ["leadership"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        assert r.json()["companies_used"] == []
        created_ids.append(sid)
        return sid

    def test_mark_with_round(self, client, story_id):
        r = client.post(f"{API}/stories/{story_id}/used",
                        json={"company": "Microsoft", "round": "Onsite"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "Microsoft (Onsite)" in d["companies_used"]
        assert "_id" not in d
        # persisted
        g = client.get(f"{API}/stories", timeout=30).json()["stories"]
        s = next(x for x in g if x["id"] == story_id)
        assert "Microsoft (Onsite)" in s["companies_used"]

    def test_mark_dedup(self, client, story_id):
        r = client.post(f"{API}/stories/{story_id}/used",
                        json={"company": "Microsoft", "round": "Onsite"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["companies_used"].count("Microsoft (Onsite)") == 1

    def test_mark_without_round(self, client, story_id):
        r = client.post(f"{API}/stories/{story_id}/used", json={"company": "Adobe"}, timeout=30)
        assert r.status_code == 200, r.text
        used = r.json()["companies_used"]
        assert "Adobe" in used
        assert "Microsoft (Onsite)" in used

    def test_mark_bad_story_404(self, client):
        r = client.post(f"{API}/stories/does-not-exist/used", json={"company": "Google"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_mark_empty_company_400(self, client, story_id):
        r = client.post(f"{API}/stories/{story_id}/used", json={"company": "   "}, timeout=30)
        assert r.status_code == 400, r.text

    def test_mark_missing_company_422(self, client, story_id):
        r = client.post(f"{API}/stories/{story_id}/used", json={}, timeout=30)
        assert r.status_code in (400, 422), r.text


# ----- MATCH -----
class TestMatch:
    def test_match_existing_body_shape(self, client):
        r = client.post(f"{API}/stories/match",
                        json={"question": "a time you influenced without authority"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "results" in d and isinstance(d["results"], list)
        assert d["query"] == "a time you influenced without authority"
        assert len(d["results"]) > 0, "expected at least one matched story"
        for item in d["results"]:
            assert "id" in item and "title" in item
            assert item["fit"] in ("strong", "good", "stretch")
            assert isinstance(item["reason"], str)
            assert "_id" not in item

    def test_match_with_interviewing_at(self, client):
        r = client.post(f"{API}/stories/match",
                        json={"question": "tell me about a failure", "interviewing_at": "Google"},
                        timeout=120)
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["results"], list)

    def test_match_missing_question_422(self, client):
        r = client.post(f"{API}/stories/match", json={}, timeout=30)
        assert r.status_code == 422


# ----- EXISTING STORY CRUD REGRESSION -----
class TestStoryCrudRegression:
    def test_list_stories(self, client):
        r = client.get(f"{API}/stories", timeout=30)
        assert r.status_code == 200
        stories = r.json()["stories"]
        assert isinstance(stories, list)
        assert all("_id" not in s for s in stories)

    def test_create_patch_delete(self, client):
        r = client.post(f"{API}/stories", json={
            "title": "TEST_crud", "situation": "s1", "task": "t1", "action": "a1",
            "result": "r1", "themes": ["execution"], "tags": ["star"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        assert r.json()["status"] == "draft"

        p = client.patch(f"{API}/stories/{sid}", json={
            "situation": "edited situation", "result": "edited result",
        }, timeout=30)
        assert p.status_code == 200, p.text
        assert p.json()["situation"] == "edited situation"
        assert p.json()["task"] == "t1"

        lst = client.get(f"{API}/stories", timeout=30).json()["stories"]
        s = next(x for x in lst if x["id"] == sid)
        assert s["result"] == "edited result"

        d = client.delete(f"{API}/stories/{sid}", timeout=30)
        assert d.status_code == 200
        lst2 = client.get(f"{API}/stories", timeout=30).json()["stories"]
        assert all(x["id"] != sid for x in lst2)

    def test_patch_bad_id_404(self, client):
        r = client.patch(f"{API}/stories/nope", json={"title": "x"}, timeout=30)
        assert r.status_code == 404

    def test_patch_no_changes_400(self, client):
        r = client.patch(f"{API}/stories/whatever", json={}, timeout=30)
        assert r.status_code == 400

    def test_polish_story(self, client):
        r = client.post(f"{API}/stories", json={
            "title": "TEST_polish", "situation": "We had messy onboarding at ISB club.",
            "task": "I had to fix it.", "action": "I talked to people and made a plan.",
            "result": "It got better.", "themes": ["execution"],
        }, timeout=30)
        sid = r.json()["id"]
        try:
            p = client.post(f"{API}/stories/{sid}/polish", timeout=180)
            assert p.status_code == 200, p.text
            d = p.json()
            assert d["status"] == "polished"
            assert d["feedback"], "expected coaching feedback"
            assert all(d[k] for k in ("situation", "task", "action", "result"))
        finally:
            client.delete(f"{API}/stories/{sid}", timeout=30)

    def test_polish_bad_id_404(self, client):
        r = client.post(f"{API}/stories/nope/polish", timeout=30)
        assert r.status_code == 404
