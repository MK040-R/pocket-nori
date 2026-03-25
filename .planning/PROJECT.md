# Pocket Nori

## What This Is

Pocket Nori is a personal intelligence layer for working professionals. It captures meeting conversations via Google Meet/Calendar, extracts topics, commitments, and entities with LLM-powered analysis, and surfaces that intelligence through semantic search, topic timelines, connection graphs, and pre-meeting briefings. It's built for the individual professional — a private, per-user memory system that knows what you've discussed, decided, and committed to across all your meetings.

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
- ✓ Intelligent search: migration 009 applied (digest + embedding columns on conversations/topic_clusters/entities + IVFFlat ANN indexes); multi-table vector search; `generate_meeting_digest()` one LLM call/meeting at ingest; `answer_question()` with cited-index resolution; `POST /search/ask` Q&A endpoint; `POST /admin/backfill-embeddings` — 2026-03-15
- ✓ Search cost: ~$0.004/meeting at ingest, ~$0.00001/query (zero LLM tokens at search time) — 2026-03-15
- ✓ Persistent global search shell: shared header search launches into `/search?q=...`, and the search page auto-runs URL-driven queries while keeping manual searches in sync — 2026-03-16
- ✓ Persistent Meetings import entry: `/meetings` now always exposes `Import past meetings` linking back to `/onboarding` — 2026-03-16
- ✓ Onboarding wizard redesign: `/onboarding` now uses Welcome / Import / Processing steps with skip paths into `/meetings`, and `/meetings` shows a friendly no-meetings prompt after skip — 2026-03-16
- ✓ Home quick summary card: `/` now renders an optional Quick Summary card from `GET /home/summary`, with skeleton loading and silent hide on empty/error — 2026-03-16
- ✓ Meetings list enrichment: `/meetings` now groups cards into Today / This week / Earlier and shows up to 3 topic chips per meeting from `topic_labels` — 2026-03-16
- ✓ Deterministic TopicNode spine: TopicNode bridge semantics, deterministic provenance, rebuild-time topic-node embedding refresh, and segment-link backfill flow — 2026-03-25
- ✓ Canonical Entity Nodes: `entity_nodes`, mention-to-node assignment, rebuild/backfill, and node-backed entity search/browse — 2026-03-25
- ✓ Knowledge Graph: `knowledge_edges` + `knowledge_edge_evidence`, graph-backed connections materializer, and `/graph/*` APIs — 2026-03-25
- ✓ Advanced write-time enrichment: embedding-assisted entity candidate generation, bounded relation extraction, citation-backed brief mention detection — 2026-03-25

### Active

- [ ] Provision Render Redis and point its URL at the existing `UPSTASH_REDIS_URL` env var
- [ ] Deploy backend + worker together on the operational rollout commit
- [ ] Apply `014_topic_node_bridge.sql`, `015_provenance_links.sql`, `017_entity_nodes.sql`, and `018_knowledge_edges.sql`
- [ ] Run `/topics/recluster` per pilot user
- [ ] Run `/admin/backfill-segment-links` per pilot user
- [ ] Run `/admin/rebuild-entity-nodes` per pilot user
- [ ] Run `/admin/backfill-knowledge-graph` per pilot user
- [ ] Verify `/search/ask`, Search, Topics, Entities, Dashboard, Home, Meetings, and graph-backed connections after rebuild/backfill
- [ ] Manual signed-in production QA against the deployed frontend
- [ ] Defer `016_topic_node_cutover.sql` until runtime no longer depends on legacy storage names
- [ ] Post-MVP roadmap definition (v2 integrations, infra scaling, evaluation framework) after MVP topic quality is acceptable

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

**Current state (March 2026):** Phase 0a spikes complete (all CONDITIONAL GO), Phase 0 foundation complete, and execution Phases 1–5 complete. The local backend now extends that foundation with the deterministic TopicNode spine, deterministic segment provenance, canonical Entity Nodes, typed Knowledge Graph edges with evidence, graph APIs, and advanced write-time enrichment. Production rollout now depends on Render Redis cutover, backend/worker deploy, migrations `014`, `015`, `017`, and `018`, per-user rebuild/backfill, and signed-in production QA. Physical `topic_nodes` cutover via migration `016` is intentionally deferred.

**Backend is implemented through the current intelligence stack.** Canonical topic identity is bridged through TopicNode semantics; canonical entity identity is persisted in `entity_nodes`; graph relationships are persisted in `knowledge_edges` with `knowledge_edge_evidence`; compatibility `connections` remain materialized for existing read surfaces. Full Celery pipeline now covers ingest → extract → topic/entity node assignment → embed → graph materialization → recurring brief scheduling/generation, plus per-user rebuild/backfill flows. FastAPI now includes `POST /topics/recluster`, `POST /admin/backfill-segment-links`, `POST /admin/rebuild-entity-nodes`, `POST /admin/backfill-knowledge-graph`, and `GET /graph/*` routes. Search is node-backed across topics, entities, conversations, and transcript segments with date filters, grouped result types, and score threshold 0.30. Local validation is green (`ruff`, `mypy`, `pytest`); production rollout still depends on the broker/deploy/backfill sequence above.

**Tech environment:** Python 3.13 + FastAPI + Pydantic v2, Supabase PostgreSQL 16 + pgvector, Redis-compatible broker/cache via `UPSTASH_REDIS_URL` (Render Redis for rollout/pilot operations), Celery 5.4.0, Claude via instructor, OpenAI embeddings, Deepgram Nova-3.

**Known concerns from codebase map:**
- `process_transcript` in `src/workers/tasks.py` remains a legacy placeholder; `generate_brief` is now implemented for Phase 4
- No pagination on list endpoints (acceptable for MVP user count)
- Physical `topic_nodes` cutover is deferred; runtime still bridges over legacy canonical topic storage names internally
- Frontend production build in this sandbox is blocked by `next/font` resolving Google Fonts; deploy-time verification must still run in network-enabled infrastructure
- Production rollout still requires real-user rebuild/backfill and signed-in QA for the new entity-node and graph surfaces

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
| Render Redis for operational rollout (via existing `UPSTASH_REDIS_URL`) | Upstash free tier is exhausted; keep config churn low while restoring worker reliability | ✓ Adopted |
| OpenAI text-embedding-3-small over Anthropic embeddings | Stability + cost at 1536 dims | — Pending |
| No Electron for MVP | De-risk intelligence layer validation before platform investment | ✓ Good |
| instructor + Pydantic for LLM extraction | Typed output, no hallucinated keys, easy to validate | ✓ Good |
| Google Drive as transcript source (not Google Meet API) | Meet API lacks diarization; Drive has full recordings | ✓ Good |

---
*Last updated: 2026-03-25 after the local intelligence stack was completed through Entity Nodes, Knowledge Graph, and advanced resolution*
