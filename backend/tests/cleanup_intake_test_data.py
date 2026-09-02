import os
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
P = "ZZ_TEST_"

evs = [e for e in requests.get(f"{BASE}/api/calendar").json()["events"] if e["title"].startswith(P)]
for e in evs:
    print("del event", e["title"], requests.delete(f"{BASE}/api/calendar/{e['id']}").status_code)

sts = [s for s in requests.get(f"{BASE}/api/stories").json()["stories"] if s["title"].startswith(P)]
for s in sts:
    print("del story", s["title"], requests.delete(f"{BASE}/api/stories/{s['id']}").status_code)

ov = requests.get(f"{BASE}/api/dream/overview").json()
prep = [p for items in ov["prep_by_category"].values() for p in items if p["title"].startswith(P)]
for p in prep:
    print("del prep", p["title"], requests.delete(f"{BASE}/api/dream/prep/{p['id']}").status_code)

ppl = requests.get(f"{BASE}/api/people").json()["people"]
for p in ppl:
    if p["name"].startswith(P):
        print("del person", p["name"], requests.delete(f"{BASE}/api/people/{p['id']}").status_code)

resets = [p["id"] for p in ppl if p.get("prep_group")]
if resets:
    r = requests.post(f"{BASE}/api/intake/commit", json={"people_updates": [
        {"id": i, "prep_group": False, "strengths": [], "strength_note": ""} for i in resets]})
    print("reset", len(resets), r.status_code, r.json())

print("status:", requests.get(f"{BASE}/api/intake/status").json())
ppl2 = requests.get(f"{BASE}/api/people").json()["people"]
print("people:", len(ppl2), "candidates:", len([p for p in ppl2 if p.get("prep_candidate")]),
      "mentors:", len([p for p in ppl2 if p.get("relation") == "Mentor"]))
print("companies:", len(requests.get(f"{BASE}/api/dream/overview").json()["companies"]))
print("events:", len(requests.get(f"{BASE}/api/calendar").json()["events"]),
      "stories:", len(requests.get(f"{BASE}/api/stories").json()["stories"]))
