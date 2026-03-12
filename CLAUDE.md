# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Farz** — a personal intelligence layer for working professionals. Captures and synthesizes context from meetings (starting with Google Meet/Calendar), surfacing topical search, cross-meeting connections, pre-meeting briefings, and a personal context dashboard.

**Current stage:** Phases 1–5 are complete (frontend web app, topic arcs/commitment tracker, connection graph, calendar sync + recurring briefs, personal context dashboard). `Insightful Dashboard` visual refresh and read-path performance improvements are also deployed. Current execution target is MVP topic-intelligence cleanup and pilot-critical data-quality hardening before broader rollout.

---

## Reference Documents

Read these before writing any code — they are the source of truth for all decisions:

| File | Purpose | When to read |
|---|---|---|
| `DOCS.md` | Documentation index — what each file is, conflict resolution hierarchy, change protocol | Read first |
| `farz-prd.md` | Product requirements — Sections 3 and 5 are mandatory before any code | Always |
| `farz-tech-requirements-mvp.md` | Technical decisions with rationale (MVP scope, Phases 0a–2) | Before architecture/infra work |
| `farz-ui-spec.md` | UI object model, screen specs, component patterns, API contracts | Before any frontend work |
| `.interface-design/system.md` | Design tokens: colors, typography, depth strategy | Before any styling |
| `spikes/PHASE_0A_SUMMARY.md` | QA summary of all 5 spikes — go/no-go decisions, bugs found and fixed | Before Phase 0 build |
| `agent_docs/CODEX_BRIEF.md` | Live Codex/Claude integration contract for frontend-facing API shape | Before API contract changes |
| `PROGRESS.md` | Shared execution log for completed work waves | Update after each completed task |
| `POST_MVP_HARDENING_PLAN.md` | Post-MVP pilot hardening milestones and execution rules | Before post-MVP implementation |
| `docs/later-stages/farz-tech-requirements-full.md` | Full architecture for Phase 3+ (AWS, Electron, compliance) | Phase 3+ only |
| `competitive-analysis.md` | Competitor profiles (Granola, Otter, Fireflies, Notion, Mem0) | Background reading |

---

## Confirmed Tech Stack

| Category | Choice |
|---|---|
| Backend | Python 3.13 + FastAPI + Pydantic v2 (already in `.venv`) |
| Frontend | Next.js 15 + TypeScript + Tailwind CSS |
| Database | Supabase PostgreSQL 16 + pgvector |
| Auth | Supabase Auth + Google OAuth 2.0 |
| Cache | Upstash Redis (serverless) |
| Async jobs | Celery + Redis broker |
| Transcription | Deepgram Nova-3 |
| LLM (extraction) | `claude-sonnet-4-6` via `instructor` + Pydantic |
| LLM (briefs) | `claude-opus-4-6` — used sparingly |
| Object storage | Supabase Storage (transcripts only; no audio stored) |
| Hosting | Render.com (~$25/month) |

**Desktop app (Electron):** Phase 3 only — not in scope for MVP.

---

## Environment

```bash
source .venv/bin/activate   # Python 3.13 venv with FastAPI, Pydantic v2, uvicorn, anyio
```

Core source layout:
```
src/api/        FastAPI routes and middleware
src/workers/    Celery task definitions
src/models/     Pydantic models for all 9 entities
migrations/     Supabase SQL migrations
tests/
frontend/       Next.js 15 web app
```

---

## Non-Negotiable Architectural Constraints

These override every other decision. They must be enforced in code, not just policy.

### 1. Per-user index isolation — enforced at 6 layers simultaneously
- **Postgres:** `FORCE ROW LEVEL SECURITY` on every user-owned table (not just ENABLE — FORCE applies even to table owner). Policy: `USING (user_id = auth.uid())`
- **Storage:** Path prefix `/users/{user_id}/...` — no cross-user paths
- **Redis:** Key namespace `user:{user_id}:...` — no cross-user keys
- **pgvector:** `WHERE user_id = $1` applied before any ANN similarity search
- **LLM calls:** Transcript text is always single-user scoped — never batched across users
- **Celery:** Job payload includes `user_id`; worker validates ownership before any read/write

**Critical:** The `service_role` key bypasses RLS entirely. Celery workers must receive the user's JWT as part of the job payload and use it for all DB operations — never `service_role` for data reads.

### 2. No training on user data
Anthropic's standard API does not use data for model training — sufficient for Phase 1 internal testing. A formal DPA is required before any external user onboards.

### 3. Hard-delete only — no soft-delete ever
No `deleted_at` column on any table. Deletion cascades immediately across Postgres rows, pgvector embeddings, Redis cache keys, and Supabase Storage paths.

### 4. Audio files are transient
Uploaded audio: stored temporarily → transcribed → **hard-deleted immediately** on success, or after 1-hour timeout on failure. Only the text transcript is retained.

### 5. All LLM calls through a single module
Route all LLM calls through `src/llm_client.py`. No direct SDK calls scattered across the codebase. Transcript content must never appear in application logs.

### 6. Startup validation
The server must not start if `ANTHROPIC_API_KEY` (or other required provider config) is absent — validate at boot in `src/config.py`.

---

## Data Model (9 core entities)

`TranscriptSegment` was added by engineering review — build it from Phase 0. Every derived entity links back to one or more `TranscriptSegment`s for citations.

```
Index (per user)
├── Conversations [1..N]
│   └── contains → TranscriptSegments [1..N]
│       ├── extracted → Commitments [0..N]
│       └── references → Entities [0..N]
├── Topics [0..N]
│   └── linked to → Conversations + TranscriptSegments [1..N]
├── Topic Arcs [0..N]  (timeline view over Topics × Conversations)
└── Connections [0..N]
    └── links → Conversations or Topics [2..N]

Brief
└── composed from → Topic Arcs + Commitments + Connections + Calendar event
```

---

## Phase 0a Spikes — Status

All 5 spikes are CONDITIONAL GO. See `spikes/PHASE_0A_SUMMARY.md` for full details. Human-action blockers remaining:

| Spike | Blocker | Action |
|---|---|---|
| Spike 1 (Electron audio) | FAR-45 | Live Google Meet audio test — install app, grant Screen Recording, verify WAV output |
| Spike 2 (Deepgram) | FAR-52/FAR-6 | Provide Deepgram API key + 3 real meeting recordings in `spikes/spike2_deepgram/recordings/` |
| Spike 3 (LLM extraction) | FAR-53 | Provide `ANTHROPIC_API_KEY` + 5 real transcripts in `spikes/spike3_llm_extraction/transcripts/` |
| Spike 4 (Supabase RLS) | FAR-60 | Provision Supabase project, run migration, populate `.env` |
| Spike 5 (Celery/Redis) | FAR-67 | Provision Upstash Redis, add `UPSTASH_REDIS_URL` to `.env` |

### Running spike tests

```bash
# Spike 1 (Electron)
cd spikes/spike1_electron_audio && npm install && npm start

# Spike 2 (Deepgram) — needs DEEPGRAM_API_KEY in .env and recordings present
cd spikes/spike2_deepgram && pip install -r requirements.txt
python test_deepgram.py && python evaluate_accuracy.py && python evaluate_diarization.py

# Spike 3 (LLM extraction) — needs ANTHROPIC_API_KEY in .env
cd spikes/spike3_llm_extraction && pip install -r requirements.txt
python runner.py && python evaluate.py

# Spike 4 (Supabase RLS) — needs Supabase credentials in .env
cd spikes/spike4_supabase_rls && pip install -r requirements.txt
python setup_test_users.py && pytest test_rls_isolation.py -v

# Spike 5 (Celery) — unit tests run without Redis; integration needs UPSTASH_REDIS_URL
cd spikes/spike5_celery_redis && pip install -r requirements.txt
pytest tests/ -v -m unit                     # no credentials needed
pytest tests/ -v --timeout=30 -m integration # needs Upstash
```

---

## UI Design System

Direction: **"Insightful Dashboard"** — light mint workspace, crisp white cards, dark saturated navigation rail, deep navy text, vivid green accent. Clear hierarchy, soft depth, no decorative noise.

Key tokens (full list in `.interface-design/system.md`):
- Background: `#F3F8FF` / light gradient canvas
- Primary text: `#041021` (deep navy)
- Accent (actions, active nav, highlights): `#00C27A` (bright green)
- Typography: Inter (UI) + JetBrains Mono (data/transcripts)
- Depth: soft card shadows + generous radii

---

## CI Requirement

Isolation tests must run on every PR: verify User A's JWT cannot read User B's rows in any user-owned table. (Test harness exists in `spikes/spike4_supabase_rls/` — promote to `tests/` in Phase 0.)

## Milestone Documentation Rule

After every completed milestone, update docs in the same session:
- `PROGRESS.md` (append milestone entry with validation results)
- `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/PROJECT.md`
- `CLAUDE.md` if stage/status instructions changed
