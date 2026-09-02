"""Day One Intake — a calm one-screen setup where the single user confirms her
prep-circle candidates and adds her real dates, mentors, stories, and prep.
Purely additive: writes into the existing collections using existing vocab.
No LLM logic here (DB access only).
"""
from fastapi import APIRouter

from database import db
from models import (EVENT_TYPES, INTERVIEW_COMPETENCIES, PREP_CATEGORIES,
                    IntakeCommitIn, new_id, now_iso)

router = APIRouter()


def _clean_competencies(values):
    valid = {c.lower(): c for c in INTERVIEW_COMPETENCIES}
    out = []
    for v in values or []:
        c = valid.get((v or "").strip().lower())
        if c and c not in out:
            out.append(c)
    return out


@router.post("/commit")
async def commit(body: IntakeCommitIn):
    counts = {"events": 0, "stories": 0, "prep_items": 0, "mentors": 0, "people_updated": 0}

    for e in body.events:
        if not e.title.strip() or not e.start.strip():
            continue
        etype = e.type if e.type in EVENT_TYPES else "event"
        await db.events.insert_one({
            "id": new_id(), "type": etype, "title": e.title.strip(), "start": e.start,
            "end": None, "location": "", "course": "", "notes": e.notes, "done": False,
            "created": now_iso(),
        })
        counts["events"] += 1

    for s in body.stories:
        if not s.title.strip():
            continue
        await db.stories.insert_one({
            "id": new_id(), "title": s.title.strip(), "situation": s.situation,
            "task": s.task, "action": s.action, "result": s.result,
            "themes": [], "tags": [], "companies_used": [], "status": "draft",
            "feedback": "", "created": now_iso(), "updated": now_iso(),
        })
        counts["stories"] += 1

    for p in body.prep_items:
        if not p.title.strip():
            continue
        category = p.category if p.category in PREP_CATEGORIES else "roadmap"
        await db.prep_items.insert_one({
            "id": new_id(), "category": category, "title": p.title.strip(),
            "content": p.content, "status": "todo", "company_id": None,
            "created": now_iso(), "updated": now_iso(),
        })
        counts["prep_items"] += 1

    for m in body.mentors:
        if not m.name.strip():
            continue
        await db.people.insert_one({
            "id": new_id(), "name": m.name.strip(), "relation": "Mentor",
            "company": "", "birthday": "", "notes": "", "important": [], "tags": [],
            "prep_group": False, "prep_candidate": False, "strengths": [],
            "strength_note": "", "created": now_iso(), "updated": now_iso(),
        })
        counts["mentors"] += 1

    for u in body.people_updates:
        changes = {}
        if u.prep_group is not None:
            changes["prep_group"] = u.prep_group
        if u.strengths is not None:
            changes["strengths"] = _clean_competencies(u.strengths)
        if u.strength_note is not None:
            changes["strength_note"] = u.strength_note
        if not changes:
            continue
        changes["updated"] = now_iso()
        res = await db.people.update_one({"id": u.id}, {"$set": changes})
        if res.matched_count:
            counts["people_updated"] += 1

    return {"committed": True, "counts": counts}


@router.get("/status")
async def status():
    events = await db.events.count_documents({})
    stories = await db.stories.count_documents({})
    prep = await db.prep_items.count_documents({})
    confirmed = await db.people.count_documents({"prep_group": True})
    mentors = await db.people.count_documents({"relation": "Mentor"})
    has_real_data = bool(events or stories or prep or confirmed or mentors)
    return {"has_real_data": has_real_data}
