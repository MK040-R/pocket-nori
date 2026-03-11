# Farz

## What This Is

Farz is a personal intelligence layer for working professionals. It captures meeting conversations via Google Meet/Calendar, extracts topics, commitments, and entities with LLM-powered analysis, and surfaces that intelligence through semantic search, topic timelines, connection graphs, and pre-meeting briefings. It's built for the individual professional — a private, per-user memory system that knows what you've discussed, decided, and committed to across all your meetings.

## Core Value

A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.

## Requirements

### Validated

<!-- Already built and working — Phase 0a, 0, and Phase 1 Waves 1–3 -->

- ✓ Google OAuth 2.0 login with Supabase Auth — Phase 0
- ✓ Per-user data isolation enforced at 6 layers (Postgres FORCE RLS, Redis namespace, pgvector filter, LLM scoping, Storage path, Celery JWT) — Phase 0
- ✓ Hard-delete only — no soft-delete on any table — Phase 0
- ✓ All LLM calls routed through `src/llm_client.py` — Phase 0
- ✓ Startup validation — server refuses to start without required env vars — Phase 0
- ✓ Google Drive retro-import pipeline (enumerate past Meet recordings, trigger bulk import) — Phase 1 Wave 1
- ✓ Audio-is-transient: fetched from Drive, streamed to Deepgram, never stored — Phase 1 Wave 1
- ✓ TranscriptSegment storage with speaker_id, start_ms, end_ms, text — Phase 1 Wave 1
- ✓ Auto-detect transcript format (Google Meet vs Gemini Notes) — Phase 1 Wave 1
- ✓ Idempotent ingest via drive_file_id unique index — Phase 1 Wave 1
- ✓ LLM extraction: topics, commitments, entities extracted from each conversation with segment citations — Phase 1 Wave 2
- ✓ pgvector embeddings on transcript_segments (1536-dim, OpenAI text-embedding-3-small) — Phase 1 Wave 2
- ✓ Semantic search: POST /search returns ranked segment results with citations — Phase 1 Wave 3
- ✓ API routes: auth, conversations, topics, commitments, search, onboarding, index_stats, health — Phase 1 Wave 3
- ✓ Cookie-first auth (HttpOnly session cookie) with Bearer fallback — Phase 1 Wave 3
- ✓ Frontend web app routes live (dashboard, onboarding, meetings, topics, search, commitments) — Phase 1 Wave 4
- ✓ Topic Arc backend + API (`GET /topics/{id}/arc`) with citation timeline persistence — Phase 2
- ✓ Commitments tracker hardening (assignee filtering + resolve flow) and UI — Phase 2
- ✓ Connection graph backend + API (`GET /conversations/{id}/connections`) with persisted linked items — Phase 3
- ✓ Connection UI in meeting detail with rationale + shared signals — Phase 3
- ✓ Calendar sync backend: `/calendar/today` reads real Google Calendar events and links conversations to `calendar_event_id` — Phase 4 (04-01)
- ✓ Brief generation worker: `generate_brief` now assembles topic arcs + commitments + connections context and persists briefs/link tables — Phase 4 (04-02)
- ✓ Recurring brief scheduler: `schedule_recurring_briefs` dispatches user-scoped brief generation at T-12 for eligible recurring series with prior indexed sessions — Phase 4 (04-03)
- ✓ Brief API + citation surface: `/briefs/latest` and `/briefs/{id}` plus frontend brief page and meeting deep-link to latest brief — Phase 4 (04-04)
- ✓ Personal context dashboard completion: `/calendar/today` now serves upcoming meetings + open commitments + recent activity + recent connections; `/today` renders all dashboard sections with deep links — Phase 5 (05-01/05-02)
- ✓ Full QA gate green: `ruff check src tests`, `mypy src tests`, `pytest -q` (97 passed, 7 skipped), and frontend `npm run lint` + `npm run build` — 2026-03-11 validation

### Active

<!-- MVP v1 execution requirements complete -->

- [ ] Post-MVP roadmap definition (v2 integrations, infra scaling, evaluation framework)

### Out of Scope

- Electron desktop app — Phase 3 only (system audio capture, no bot)
- Mobile app — explicitly excluded, web-first
- Admin panel with user content visibility — architectural constraint (no admin can read user data)
- Gmail integration — post-MVP (deferred v2 scope)
- AWS infrastructure — Phase 3+ (currently Render.com)
- Deepgram real-time streaming WebSocket — Phase 3 (currently batch file transcription)
- Manual file upload endpoint — retro-import only for MVP
- Bot-based recording (Fireflies/Otter model) — privacy constraint, never
- Soft-delete / deleted_at — architectural constraint, never

## Context

**Current state (March 2026):** Phase 0a spikes complete (all CONDITIONAL GO), Phase 0 foundation complete, and execution Phases 1–5 complete. Full QA gate is green at 97 passed / 7 skipped. Next focus is post-MVP planning.

**Backend is complete through Phase 4.** 17 tables (9 core + 8 junction), all with FORCE RLS. Full Celery pipeline: ingest → extract → embed + recurring brief scheduling/generation. FastAPI includes topic arc, commitment tracker, live connection graph, live calendar sync, and brief retrieval APIs. Current QA gate is fully green (`ruff`, `mypy`, `pytest`, frontend lint/build). Deployed on Render.com.

**Tech environment:** Python 3.13 + FastAPI + Pydantic v2, Supabase PostgreSQL 16 + pgvector, Upstash Redis (Celery broker + cache), Celery 5.4.0, Claude via instructor, OpenAI embeddings, Deepgram Nova-3.

**Known concerns from codebase map:**
- `process_transcript` in `src/workers/tasks.py` remains a legacy placeholder; `generate_brief` is now implemented for Phase 4
- No pagination on list endpoints (acceptable for MVP user count)
- No pgvector ANN index yet (ivfflat/hnsw) — full scan acceptable for MVP

**User:** Murali, non-technical founder. Building for internal testing first (solo + first engineer hire), ~50 meetings indexed, before any external users. No DPA required for MVP phase.

## Constraints

- **Security**: FORCE RLS on all 17 tables — never relax, not even for convenience
- **Privacy**: service_role key for migrations only — never in API routes or Celery workers
- **Data**: Hard-delete only — no deleted_at columns ever, on any table
- **LLM**: All calls through `src/llm_client.py` — no direct SDK imports elsewhere
- **Audio**: Never stored — transient fetch → transcribe → discard
- **Cost**: ~$50/month target for MVP (Render ~$25 + Supabase free + Upstash free)
- **Execution ownership**: Codex handles both backend and frontend delivery
- **Hosting**: Render.com for MVP — AWS migration is Phase 3

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Retro-import over manual upload | Gives user weeks of indexed history on day one vs. per-meeting effort | ✓ Good |
| pgvector over Pinecone | One fewer service, handles MVP volumes (<10M vectors) | — Pending |
| Supabase over raw Postgres | Managed RLS + Auth + Storage in one service for MVP speed | ✓ Good |
| Upstash Redis for both broker + cache | Free tier, serverless, eliminates dedicated Redis instance | ✓ Good |
| OpenAI text-embedding-3-small over Anthropic embeddings | Stability + cost at 1536 dims | — Pending |
| No Electron for MVP | De-risk intelligence layer validation before platform investment | ✓ Good |
| instructor + Pydantic for LLM extraction | Typed output, no hallucinated keys, easy to validate | ✓ Good |
| Google Drive as transcript source (not Google Meet API) | Meet API lacks diarization; Drive has full recordings | ✓ Good |

---
*Last updated: 2026-03-11 after Phase 5 closure (dashboard complete)*
