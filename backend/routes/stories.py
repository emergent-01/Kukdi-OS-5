"""Story Bank — shape a STAR story once, polish it with Kukdi, reuse it across
every company. Structured so a single strong story can be tagged by theme and
mapped to the companies it's been used for.
"""
from fastapi import APIRouter, HTTPException

from ai_engine import reasoning
from database import db
from models import (INTERVIEW_COMPETENCIES, MarkUsedIn, StoryIn, StoryMatchIn,
                    StoryUpdate, new_id, now_iso)

router = APIRouter()


@router.post("/match")
async def match_stories(body: StoryMatchIn):
    stories = await db.stories.find({}, {"_id": 0}).to_list(500)
    catalog = [
        {"id": s["id"], "title": s.get("title", ""), "themes": s.get("themes", []),
         "companies_used": s.get("companies_used", []),
         "snippet": (s.get("situation", "") + " " + s.get("result", ""))[:240]}
        for s in stories
    ]
    ranked = await reasoning.match_stories(body.question, catalog, body.interviewing_at)
    by_id = {s["id"]: s for s in stories}
    results = []
    for r in ranked:
        s = by_id.get(r.get("id"))
        if s:
            results.append({**s, "fit": r.get("fit", "good"), "reason": r.get("reason", "")})
    return {"results": results, "query": body.question}


@router.get("/coverage")
async def coverage():
    """Live competency coverage: which competencies have zero or only one story."""
    stories = await db.stories.find({}, {"_id": 0}).to_list(500)
    lower_map = {c.lower(): c for c in INTERVIEW_COMPETENCIES}
    counts = {c: 0 for c in INTERVIEW_COMPETENCIES}
    for s in stories:
        seen = set()
        for t in (s.get("themes") or []):
            key = (t or "").strip().lower()
            if not key:
                continue
            comp = lower_map.get(key)
            if not comp:
                for lc, orig in lower_map.items():
                    if lc in key or key in lc:
                        comp = orig
                        break
            if comp and comp not in seen:
                counts[comp] += 1
                seen.add(comp)
    missing = [c for c in INTERVIEW_COMPETENCIES if counts[c] == 0]
    thin = [c for c in INTERVIEW_COMPETENCIES if counts[c] == 1]
    return {"competencies": INTERVIEW_COMPETENCIES, "counts": counts, "missing": missing, "thin": thin}


@router.get("")
async def list_stories():
    stories = await db.stories.find({}, {"_id": 0}).sort("updated", -1).to_list(500)
    return {"stories": stories}


@router.post("")
async def create_story(body: StoryIn):
    doc = body.model_dump()
    doc.update({"id": new_id(), "feedback": "", "created": now_iso(), "updated": now_iso()})
    await db.stories.insert_one({k: v for k, v in doc.items()})
    return {k: v for k, v in doc.items() if k != "_id"}


@router.patch("/{story_id}")
async def update_story(story_id: str, body: StoryUpdate):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(400, "No changes")
    changes["updated"] = now_iso()
    res = await db.stories.update_one({"id": story_id}, {"$set": changes})
    if not res.matched_count:
        raise HTTPException(404, "Story not found")
    return await db.stories.find_one({"id": story_id}, {"_id": 0})


@router.post("/{story_id}/polish")
async def polish_story(story_id: str):
    story = await db.stories.find_one({"id": story_id}, {"_id": 0})
    if not story:
        raise HTTPException(404, "Story not found")
    polished = await reasoning.polish_story(story)
    await db.stories.update_one(
        {"id": story_id},
        {"$set": {
            "situation": polished["situation"], "task": polished["task"],
            "action": polished["action"], "result": polished["result"],
            "feedback": polished["feedback"], "status": "polished",
            "updated": now_iso(),
        }},
    )
    return await db.stories.find_one({"id": story_id}, {"_id": 0})


@router.delete("/{story_id}")
async def delete_story(story_id: str):
    await db.stories.delete_one({"id": story_id})
    return {"ok": True}


@router.post("/{story_id}/used")
async def mark_used(story_id: str, body: MarkUsedIn):
    story = await db.stories.find_one({"id": story_id}, {"_id": 0})
    if not story:
        raise HTTPException(404, "Story not found")
    entry = (body.company or "").strip()
    if not entry:
        raise HTTPException(400, "Company is required")
    if body.round and body.round.strip():
        entry = f"{entry} ({body.round.strip()})"
    used = list(story.get("companies_used") or [])
    if entry not in used:
        used.append(entry)
        await db.stories.update_one(
            {"id": story_id}, {"$set": {"companies_used": used, "updated": now_iso()}}
        )
    return await db.stories.find_one({"id": story_id}, {"_id": 0})
