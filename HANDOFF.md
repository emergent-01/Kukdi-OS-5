# Kukdi — Project Handoff

> Feed this whole document to another LLM (e.g. Claude) so it understands the
> entire project. Then describe the change you want; ask it to return a single,
> precise implementation prompt you can paste back to the Emergent agent (E1)
> building this app. The last section ("How to request changes") tells the LLM
> the constraints its prompt must respect so the change applies cleanly.

---

## 1. What Kukdi is

**Kukdi — "A Personal Operating System."** An intelligent, single-user app whose
purpose is to **reduce cognitive load and solve mental fragmentation**. It is NOT
a chatbot, task manager, or Notion clone. The interface should almost disappear;
**the intelligence is the product**.

**Version One is handcrafted for one user — "Little Miss":** an MBA (PGP) student
at ISB Mohali targeting a **Product Management** role at Google, Microsoft, Adobe,
or MakeMyTrip. She's organised, emotionally driven, a morning person who sleeps
late, sometimes procrastinates, loves planning, gets anxious under stress, is
consistent once committed, and finds running clears her head. Placements begin
around November.

**Core principles:** context over features · memory over notes · conversations
over forms · guidance over dashboards · calm over notifications · quality over
quantity · one amazing experience over fifty mediocre ones.

**Explicit non-goals for V1:** multi-user, authentication (intentionally none),
notification firehoses, KPI/widget dashboards.

---

## 2. Tech stack & runtime conventions

- **Backend:** FastAPI + MongoDB (Motor async driver). Runs on `0.0.0.0:8001`.
- **Frontend:** React (CRA) + Tailwind + shadcn/ui + framer-motion. Runs on `:3000`.
- **AI/integrations** (all via the **Emergent universal LLM key**, `EMERGENT_LLM_KEY`,
  using the `emergentintegrations` library):
  - **Claude Sonnet 4.6** (`anthropic` / `claude-sonnet-4-6`) — all reasoning/text.
  - **OpenAI Whisper** (`whisper-1`) — voice transcription.
  - **Emergent Object Storage** — file/PDF uploads.
- **Process manager:** supervisor (`sudo supervisorctl restart backend|frontend`).
  Hot-reload is on; restart only needed after `.env` or dependency changes.

**Hard platform rules (must never be broken):**
- Every backend route is prefixed with **`/api`** (Kubernetes ingress routes `/api/*`
  to :8001, everything else to :3000).
- Frontend calls the backend **only** via `process.env.REACT_APP_BACKEND_URL`.
  Backend reads Mongo via `MONGO_URL` + `DB_NAME`. **Never hardcode URLs/secrets.**
- Use **yarn**, never npm. Add backend deps then `pip freeze > requirements.txt`.
- `.env` files are protected: `backend/.env` (MONGO_URL, DB_NAME, CORS_ORIGINS,
  EMERGENT_LLM_KEY), `frontend/.env` (REACT_APP_BACKEND_URL). Only add keys, never
  remove existing ones.

---

## 3. Repository structure

```
/app
├── docker-compose.yml            # mongo + backend + frontend (one-command run)
├── README.md
├── HANDOFF.md                    # this file
├── memory/PRD.md                 # running product record (versions V1..V1.4)
├── backend/
│   ├── server.py                 # FastAPI app; mounts all routers under /api/*
│   ├── database.py               # single Mongo client -> `db`
│   ├── models.py                 # fixed vocab lists + Pydantic request models
│   ├── ai_engine.py              # KukdiReasoning — the ONLY module that knows an LLM
│   ├── context.py                # build_context() — DB→reasoning seam
│   ├── speech.py                 # Whisper STT wrapper
│   ├── storage.py                # Emergent Object Storage + pdf/txt text extraction
│   ├── seed.py                   # rich idempotent demo seed (auto-runs if empty)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── routes/
│       ├── home.py               # adaptive Home + daily brief
│       ├── conversation.py       # streaming chat, transcribe, candidate extraction
│       ├── memory.py             # memory CRUD + candidates + relationships
│       ├── dream.py              # companies, prep, interview countdown
│       ├── people.py             # relationship cards
│       ├── calendar.py           # events + natural-language "ask"
│       ├── knowledge.py          # notes/PDF uploads + semantic search
│       ├── reflection.py         # weekly reflection
│       ├── reminders.py          # smart nudges (dismiss/snooze)
│       └── stories.py            # STAR Story Bank (match, coverage, mark-used, polish)
└── frontend/
    ├── package.json, tailwind.config.js, postcss.config.js, Dockerfile
    ├── public/index.html
    └── src/
        ├── App.js                # BrowserRouter + all routes, wrapped in <Layout>
        ├── index.css             # fonts (Cormorant Garamond + Manrope), theme tokens
        ├── App.css
        ├── lib/api.js            # axios client + ALL endpoint helpers + formatters
        ├── components/
        │   ├── Layout.jsx        # left rail (desktop) + bottom nav (mobile)
        │   ├── Modal.jsx         # shared Modal, Field, inputClass, PrimaryButton
        │   └── ui/               # 46 shadcn components (available, sparingly used)
        └── pages/
            ├── Home.jsx  Talk.jsx  DreamOffer.jsx  People.jsx  Memory.jsx
            ├── Calendar.jsx  Knowledge.jsx  Reflection.jsx  Stories.jsx  More.jsx
```

---

## 4. Backend architecture (the important ideas)

**A. Reasoning is a swappable module.** `ai_engine.py` (`class KukdiReasoning`,
singleton `reasoning`) is the ONLY file that imports/knows an LLM. Routes gather
*context* and call verbs on `reasoning`. To swap Claude for another model,
reimplement this one file — nothing else changes. **The UI never depends on a model.**

**B. `context.py` is the DB→reasoning seam.** `build_context()` returns
`{profile, memories (active, top by confidence), events (upcoming)}`. Routes pass
this dict into `reasoning`; the engine itself never touches the database.

**C. Data conventions (follow these for any new collection/model):**
- Every document has a string **`id` = uuid4** (via `models.new_id()`).
- **Mongo `_id` is always projected out** (`{"_id": 0}`) and never returned.
- Datetimes are **ISO-8601 UTC strings** (`models.now_iso()`), stored as strings.
- Request bodies are Pydantic models in `models.py`; stored docs are plain dicts
  assembled in the route.
- "Computed, not stored" pattern: Home state, Dream Offer progress, reminders, and
  story coverage are all derived live on read (not persisted).

**D. Startup:** `seed(force=False)` auto-seeds only if the `memories` collection is
empty; `POST /api/seed` re-seeds (wipe + rebuild). Object storage is initialised on
startup.

---

## 5. Data model (MongoDB collections)

All documents share `id: str (uuid)`, `created`, and usually `updated` (ISO strings).

- **memories** — `type` (see MEMORY_TYPES), `title`, `description`, `confidence`
  (0–1 float), `status` (active|archived), `source` (seed|manual|conversation),
  `relationships` (list of `{kind: person|event|memory, ref_id, label}`), `tags`,
  `usable_for`, `last_confirmed`.
- **candidates** — pending memories from conversation: `type, title, description,
  confidence, tags, usable_for, status (pending|confirmed|dismissed), conversation_id, source`.
- **conversations** — `title, updated`. **messages** — `conversation_id, role
  (user|kukdi), text`.
- **companies** — `name, tier (dream|target|safe), role, stage (see COMPANY_STAGES),
  location, notes, next_action`.
- **prep_items** — `category (see PREP_CATEGORIES), title, content, status
  (todo|doing|done), company_id?`.
- **countdowns** — single active doc `id:"active"`: `company, role, target_date,
  days:[{id, date, focus, tasks:[{id, text, done}]}]`.
- **people** — `name, relation, company, birthday (free text e.g. "March 14" or ISO),
  notes, important (list), tags`.
- **events** — `type (see EVENT_TYPES), title, start (ISO), end?, location, course,
  notes, done`.
- **knowledge** — `kind (note|book|framework|case|document), title, summary, body,
  tags`; uploads also add `file_path, file_url, original_filename, content_type`.
- **stories** — `title, situation, task, action, result, themes (list), tags,
  companies_used (list of strings e.g. "Google" / "Microsoft (Onsite)"), status
  (draft|polished), feedback`.
- **settings** — singleton `id:"singleton"`: `home_state_override, detected_state,
  brief_text/brief_date, reflection_text/reflection_week/reflection_stats,
  dismissed_reminders (list), snoozed_reminders (map id→ISO date)`.

**Fixed vocab lists in `models.py`** (extendable in one place — mirror this pattern
for any new fixed list): `MEMORY_TYPES`, `HOME_STATES`, `COMPANY_STAGES`,
`COMPANY_TIERS`, `PREP_CATEGORIES`, `EVENT_TYPES`, `INTERVIEW_COMPETENCIES`
(Leadership, Ambiguity, Failure, Conflict, Influence, Execution, Analytical Thinking,
Customer Focus).

---

## 6. API reference (all under `/api`)

**Core** — `GET /` (health), `POST /seed` (wipe+reseed).

**Home** (`/api/home`)
- `GET /` → adaptive `{state, override, greeting, heading, subtext, today, upcoming,
  focus, surfaced_memories, pending_candidates, date}`. State derived from events
  (exam/placement proximity, weekend, load) unless overridden.
- `POST /state {state}` → set/clear the manual state override.
- `GET /brief` → `{brief, cached}` (LLM daily brief, cached per day). `POST /brief/refresh`.

**Conversation** (`/api/conversation`)
- `POST /message {text, conversation_id?}` → non-stream `{conversation_id, reply, candidates[], detected_state}`.
- `POST /stream {text, conversation_id?}` → **SSE**: events `meta` → many `token` →
  `candidates` → `done`. (Primary path used by the Talk UI.)
- `POST /transcribe` (multipart `file`) → `{text}` via Whisper (format-whitelisted, ≤25 MB).
- `GET /messages?conversation_id=` → latest thread.

**Memory** (`/api/memory`)
- `GET /?type=&q=` → `{memories, types}`; `POST /`; `PATCH /{id}`; `POST /{id}/confirm`
  (re-confirm); `DELETE /{id}` (archive).
- `GET /{id}` (with resolved `connections`); `POST /{id}/link {kind, ref_id, label}`;
  `POST /{id}/unlink {ref_id}`.
- Candidates: `GET /candidates/pending`; `POST /candidates/{id}/confirm {title?,description?,type?}`;
  `POST /candidates/{id}/dismiss`.

**Dream Offer** (`/api/dream`)
- `GET /overview` → `{companies, prep_by_category, progress, stage_counts, counts}`.
- Companies: `POST /companies`, `PATCH /companies/{id}`, `DELETE /companies/{id}`.
- Prep: `POST /prep`, `PATCH /prep/{id}`, `DELETE /prep/{id}`.
- Countdown: `GET /countdown`; `POST /countdown/generate {company_id?, target_date?}`
  (targets next placement/interview event by default; has an LLM-failure fallback plan);
  `PATCH /countdown/task/{task_id} {done}`.

**People** (`/api/people`) — `GET /`, `POST /`, `PATCH /{id}`, `DELETE /{id}`.

**Calendar** (`/api/calendar`) — `GET /` (`{events, upcoming, past}`), `POST /`,
`PATCH /{id}`, `DELETE /{id}`, `POST /ask {question}` (natural-language answer via LLM).

**Knowledge** (`/api/knowledge`)
- `GET /?q=` (substring); `POST /` (manual item); `DELETE /{id}`.
- `POST /upload` (multipart `file`) → stores to object storage + extracts pdf/txt text.
- `GET /files/{path}` → serves the stored bytes.
- `POST /search {question}` → **semantic** ranking via LLM: `{results:[{...item, reason}]}`.

**Reflection** (`/api/reflection`) — `GET /weekly?refresh=` → `{reflection, stats, cached}`
(cached per ISO week; stats derived from the week's memories/prep/events).

**Reminders** (`/api/reminders`) — `GET /` → `{reminders:[{id, kind, title, detail,
days, priority}]}` derived live from deadlines/exams/placements (≤5 days), birthdays
(≤21 days), and open company next-steps. `POST /dismiss {id}` (permanent);
`POST /snooze {id}` (hidden until tomorrow). Reminder ids are deterministic:
`event:{id}` / `birthday:{personId}` / `action:{companyId}`.

**Stories** (`/api/stories`)
- `POST /match {question, interviewing_at?}` → LLM-ranked `{results:[{...story, fit
  (strong|good|stretch), reason}]}`. The engine sees each story's `companies_used` and
  prefers an unused-at-that-company story when fits are comparable.
- `GET /coverage` → `{competencies, counts, missing[], thin[]}` (live vs INTERVIEW_COMPETENCIES).
- `GET /`, `POST /`, `PATCH /{id}`, `DELETE /{id}`.
- `POST /{id}/polish` → Claude refines the STAR fields + returns a coaching `feedback`, sets status=polished.
- `POST /{id}/used {company, round?}` → appends `Company (Round)` to `companies_used` (deduped).

---

## 7. Reasoning engine (`ai_engine.py`) verbs

`reasoning.converse(history, user_text, context)` · `stream_reply(...)` (async gen)
· `extract_candidates(user_text, reply, context)` · `answer(question, context)` (calendar)
· `daily_brief(context, state, greeting)` · `weekly_reflection(context, stats)`
· `interview_plan(company, role, days_remaining, done_focus, context)`
· `polish_story(story)` · `semantic_rank(query, items)` · `match_stories(query, stories, interviewing_at?)`.

Persona constant `_PERSONA` defines Kukdi's calm, warm, brief, no-emoji, no-lists voice.
JSON-returning verbs use a tolerant `_parse_json` (strips code fences, extracts the object).
Every verb is wrapped so an LLM failure degrades gracefully (empty list / fallback text)
rather than 500-ing.

---

## 8. Frontend architecture & design system

**Routing** (`App.js`, all inside `<Layout>`): `/` Home · `/talk` · `/dream-offer` ·
`/people` · `/memory` · `/calendar` · `/knowledge` · `/reflection` · `/stories` · `/more`.
**Nav** (`Layout.jsx`): desktop **left rail** with primary sections Home / Dream Offer /
People / More (+ a "Talk to Kukdi" affordance); **mobile bottom nav** with the same four.
Secondary pages (Memory, Calendar, Knowledge, Reflection, Stories) are reached from **More**.

**API access:** always through `src/lib/api.js` (a preconfigured axios instance +
one helper per endpoint, plus `formatTime/formatDay/confidenceLabel` and a `BACKEND`
export for file URLs / SSE fetch). Add new endpoints here, never inline `axios` in pages.

**Design language (calm, editorial, warm — Apple/Arc/Kinfolk, NOT SaaS dashboard):**
- Palette (hex used directly in classes): bg `#F7F6F2`, surface `#EFECE7`,
  surfaceHover `#E6E2DC`, ink `#2C2D2B`, ink2 `#5C605A`, muted `#8A8F8C`,
  sage `#9DB0A3`, sageLight `#D4DDD7`, line `#E2DFD8`. (Also mirrored as Tailwind
  `kukdi.*` tokens.) Destructive accent used sparingly: `#a9564a`.
- **Fonts:** headings `font-editorial` = **Cormorant Garamond** (serif); body =
  **Manrope**. Big editorial H1s (`text-5xl md:text-6xl`).
- **Labels/micro-text convention:** `text-xs tracking-[0.18em] uppercase text-[#8A8F8C]`.
  Section eyebrows and quiet status lines all use this. No banners, no alert colors.
- Generous whitespace; minimal borders (`border-[#E2DFD8]`); rounded surfaces
  (`rounded-2xl`/`rounded-[2rem]`); hover-revealed controls (`opacity-0 group-hover:opacity-100`).
- **Motion:** framer-motion; slow, deliberate eases (`[0.22,1,0.36,1]`), staggered fades.
- **Shared primitives** (`components/Modal.jsx`): `Modal`, `Field`, `inputClass`,
  `PrimaryButton` (dark pill). Reuse these for any new form/dialog to stay consistent.
- **shadcn/ui** lives in `components/ui/` (46 components) and may be used, but most
  screens use bespoke minimal markup to hold the aesthetic.

**Test IDs:** every interactive/important element has a kebab-case `data-testid`
(e.g. `story-open-{id}`, `reminder-snooze-{id}`, `matcher-input`). Keep this up for
anything new — the testing agent drives flows through them.

---

## 9. Feature flows (how things connect)

- **Conversation → Memory:** Talk streams a reply (SSE), then a second pass extracts
  *candidate* memories. Nothing is remembered silently — candidates appear as
  confirm/dismiss cards on Talk and on the Memory page. Confirmed candidates become
  active memories, which feed `build_context()` → everything else gets smarter.
- **Home** reads events + memories to pick an adaptive state, a daily brief (LLM),
  smart reminders, "what matters", today's schedule, and surfaced memories.
- **Dream Offer** = company pipeline (cycle stages) + prep roadmap (status dots) +
  an adaptive **Interview Countdown** (LLM day-by-day plan toward the next round).
- **Story Bank** = STAR stories you shape once, **Polish with Kukdi** (LLM), a
  **coverage** micro-line (which competencies lack stories), **Story Matcher** (rank
  by fit for a question/company, preferring unused-at-company), and **mark-as-used**
  (track which company/round each story was told at).
- **Knowledge** = manual notes + iPad uploads (PDF/txt text-extracted) with a
  substring mode and an LLM **semantic** ("by meaning") mode.
- **Reflection** = weekly Sunday recap in Kukdi's voice from real weekly signals.

---

## 10. Seed data (what exists on first run / after POST /api/seed)

~11 memories (profile, PM goal, dream companies, routines, preferences, people),
4 companies (Google interviewing, Microsoft applied, Adobe researching, MakeMyTrip
networking), ~12 prep items, 4 people (Ananya, Rohan Mehta, Prof. Nair, Mom),
~7 events (classes, a marketing case deadline tomorrow, a run, Google APM round ~3
days out, a stats mid-term), 3 knowledge items, and **2 stories** ("Turning around
the ISB Marketing Club", "A decision I'd make differently").

---

## 11. Testing & how changes are verified

- Backend pytest suites live in `backend/tests/` (`backend_test.py`, `test_v4/v5/v6_*`).
  A dedicated testing agent also runs Playwright over the UI via `data-testid`s and
  writes reports to `/app/test_reports/iteration_*.json`.
- Quick manual checks: curl against the **external** `REACT_APP_BACKEND_URL` (not
  localhost) for e2e correctness; screenshots for UI.
- Note: some older test files read `REACT_APP_BACKEND_URL` from the environment only.

---

## 12. Known constraints, gotchas & non-goals

- **No auth** by design (single user). Don't add login unless explicitly requested
  (if requested, it MUST go through the integration playbook process).
- Semantic search / story match / coverage are tuned for **personal-scale** data
  (dozens of items) — they use the LLM directly rather than a vector index.
- Coverage theme→competency matching is case-insensitive with a loose substring
  fallback (fine for one user; could mis-attribute very short themes).
- `companies_used` stores plain strings; "Google" and "Google (Onsite)" are distinct
  entries by design.
- Shared `Modal` has no Escape-to-close handler (X button / backdrop only) — a known
  minor a11y gap affecting all modals.
- **Seeded calendar dates are relative to seed time** (`seed.py` computes offsets from
  "now"). In a long-lived preview DB they age past, so Home focus / reminders can
  quietly go empty. `POST /api/seed` re-anchors all demo dates (wipes conversations).
- LLM/SSE calls take a few seconds; UIs show calm "thinking/searching" states.

---

## 13. How to request changes (instructions for the assisting LLM)

When the human describes a change, produce **one clear, self-contained implementation
prompt** for the Emergent agent (E1). Make that prompt:

1. **State intent + scope explicitly.** If the existing feature must keep working,
   say "additive only — do not restructure existing files/routes/data model, keep
   current flows and design." (This project values additive, minimal-diff changes.)
2. **Name the exact files/functions to touch**, using this document's paths, and
   **respect the layered architecture:** DB access in routes, LLM logic only in
   `ai_engine.py` via a new/existing verb, cross-cutting query assembly in
   `context.py`, request models + fixed lists in `models.py`, frontend network calls
   only in `lib/api.js`, shared UI via `components/Modal.jsx` primitives.
3. **Respect the platform rules:** `/api` prefix on all routes; frontend uses
   `REACT_APP_BACKEND_URL`; backend uses `MONGO_URL`/`DB_NAME`; **no hardcoded
   secrets/URLs**; **yarn not npm**; uuid string ids + ISO datetimes + project out
   `_id`; prefer "computed on read" over stored where it mirrors existing patterns.
4. **Any new third-party integration or ANY auth work MUST be flagged** to go through
   Emergent's `integration_expert` playbook (and use `EMERGENT_LLM_KEY` +
   `emergentintegrations` for Claude/OpenAI/Whisper/Gemini-image/object-storage). Do
   not hand-roll SDK calls.
5. **Preserve the design system:** editorial serif headings, muted palette, uppercase
   micro-labels, generous spacing, framer-motion; no banners/bright alerts; reuse
   `Field`/`inputClass`/`PrimaryButton`.
6. **Require `data-testid`s** on every new interactive/important element, and ask for
   the change to be verified (backend starts, frontend builds, existing flows intact,
   plus a testing-agent pass for new/critical flows).
7. Keep the prompt **specific about acceptance criteria** (what endpoints/return
   shapes, what the UI shows, what must NOT change).

**Template the LLM can emit:**
> "In Kukdi, [additive/refactor] change: [goal]. Backend: [files/functions + exact
> endpoints & JSON shapes, following uuid/ISO/_id conventions and /api prefix; put any
> LLM logic in ai_engine.py]. Frontend: [pages/components + api.js helpers + testids],
> matching the existing editorial design (muted palette, Cormorant headings, uppercase
> micro-labels, Modal primitives). Do NOT change [X]. Verify backend starts, frontend
> builds, existing flows [list] still pass, and run the testing agent on [new flow]."
