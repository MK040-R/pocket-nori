# Requirements: Pocket Nori

**Defined:** 2026-03-11
**Last aligned with source docs:** 2026-03-11
**Core Value:** A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.

## Alignment Basis

This file follows the documented hierarchy in `DOCS.md`:

1. `pocket-nori-tech-requirements-mvp.md` (implementation decisions)
2. `pocket-nori-prd.md` (product intent and UX principles)

Execution phases in `.planning/ROADMAP.md` intentionally split PRD/MVP Phase 2 into smaller delivery phases (2, 3, and 4). That decomposition is sequencing, not a scope change.

## Already Complete

Phases 0a, 0, 1, 2, and 3 are built and verified. These requirements are done:

- ✓ Google OAuth login, session management, RLS-enforced auth
- ✓ Google Drive retro-import pipeline (enumerate, ingest, idempotency)
- ✓ Deepgram transcription via Drive streaming (audio never stored)
- ✓ TranscriptSegment storage (speaker_id, start_ms, end_ms, text)
- ✓ LLM extraction: topics, commitments, entities with segment citations
- ✓ pgvector embeddings (1536-dim) on transcript_segments
- ✓ Semantic search endpoint (POST /search, cosine similarity, user-scoped)
- ✓ API routes: auth, conversations, topics, commitments, search, onboarding, health
- ✓ Frontend web app (dashboard, onboarding, meetings, topics, search, commitments)
- ✓ Topic arc compute/store + `GET /topics/{id}/arc` with citation metadata
- ✓ Commitment tracker hardening: assignee filtering + resolve flow in API and UI
- ✓ Connection graph delivery: real `/conversations/{id}/connections` + meeting-detail rationale UI
- ✓ Calendar sync backend delivery: `/calendar/today` now reads real Google Calendar events and links conversations to `calendar_event_id`
- ✓ Brief generation backend delivery: Celery `generate_brief` now composes from topic arcs + commitments + connections and persists brief link tables
- ✓ Recurring brief scheduler delivery: user-scoped `schedule_recurring_briefs` now schedules T-12 generation for recurring series with prior indexed history
- ✓ Brief API + frontend citation surface delivery: `GET /briefs/{id}`, `GET /briefs/latest`, latest-brief links in meeting detail, and dedicated brief page
- ✓ Dashboard delivery: `/calendar/today` now includes recent indexed activity + recent connections; `/today` renders all required dashboard sections with meeting deep links
- ✓ 97 backend tests passing (7 skipped integration tests) + frontend lint/build passing

## Non-Negotiable Architecture Requirements

These constraints apply to all MVP phases and must remain true:

- **ARCH-01 (Isolation):** Per-user isolation is enforced at all layers: Postgres RLS (`FORCE ROW LEVEL SECURITY` + `USING (user_id = auth.uid())`), storage path prefix (`/users/{user_id}/...`), Redis key namespace (`user:{user_id}:...`), pgvector queries filtered by `user_id` before ANN search, single-user scoped LLM payloads, and Celery ownership validation.
- **ARCH-02 (Worker auth):** Celery workers must use user JWTs for data reads/writes; `service_role` is never used for user-data reads.
- **ARCH-03 (No training):** LLM and embedding providers must follow no-training API policy; formal DPA is required before onboarding any external user.
- **ARCH-04 (Deletion):** Hard-delete only; no soft-delete (`deleted_at` forbidden). Deletion cascades across Postgres, pgvector, Redis, and Supabase Storage.
- **ARCH-05 (Audio lifecycle):** Audio is transient: discarded immediately after successful transcription, or removed on failure timeout; only transcript text is retained.
- **ARCH-06 (LLM control plane):** All LLM calls route through `src/llm_client.py`; transcript content must never be written to application logs.
- **ARCH-07 (Startup validation):** API startup fails fast if required provider configuration (for example `ANTHROPIC_API_KEY`) is missing.
- **ARCH-08 (CI gate):** Isolation test (User A JWT cannot read User B data) runs on every PR.

## v1 Requirements

Requirements for remaining MVP scope. Each requirement is mapped to both product phase (PRD/MVP) and execution phase (`.planning/ROADMAP.md`).

### Frontend

- [x] **FRONT-01**: User can log in via Google OAuth from the web app
- [x] **FRONT-02**: User can trigger Google Drive retro-import and see live progress (% indexed)
- [x] **FRONT-03**: User can browse a list of all their indexed meetings
- [x] **FRONT-04**: User can open a meeting and see the extracted topics and commitments for that meeting
- [x] **FRONT-05**: User can click any topic or commitment to see the exact source quote with speaker name and timestamp
- [x] **FRONT-06**: User can type a question and get semantically matched meeting segments with source citations

### Topic Arc

- [x] **TARC-01**: User can view a timeline showing how a topic evolved across multiple meetings in chronological order
- [x] **TARC-02**: Each entry in the Topic Arc timeline links to its source transcript segment

### Connections

- [x] **CONN-01**: User can see which meetings are connected by shared topics or entities
- [x] **CONN-02**: Each connection shows what links the meetings (shared entity, topic, or commitment thread)

### Briefs

- [x] **BRIEF-01**: User receives a pre-meeting brief 10–15 minutes before start for recurring meeting series with at least one prior indexed session
- [x] **BRIEF-02**: The brief includes relevant topic context, open commitments, and related meeting connections
- [x] **BRIEF-03**: Every claim in a brief links back to a source transcript segment

### Commitments

- [x] **CMMT-01**: User can view all open commitments across all meetings, with assignee and deadline where available
- [x] **CMMT-02**: User can mark a commitment as resolved

### Calendar

- [x] **CAL-01**: Google Calendar sync auto-links imported meetings to calendar events by time window
- [x] **CAL-02**: Upcoming recurring meetings are read from Google Calendar to trigger brief generation at T-12 minutes

### Dashboard

- [x] **DASH-01**: User can open a personal context dashboard showing upcoming meetings, recent indexed activity, open commitments, and newly detected cross-meeting connections

## v2 Requirements

Deferred — not in current roadmap.

### Desktop

- **DESK-01**: Native Mac/Windows desktop app (Electron) captures system audio without a bot
- **DESK-02**: Real-time Deepgram streaming WebSocket integration for live transcription

### Additional Integrations

- **INTG-01**: Gmail integration (gmail.readonly scope) for email context in briefs
- **INTG-02**: Slack integration for cross-channel conversation context

### Scale & Infrastructure

- **INFRA-01**: Migrate from Render.com to AWS ECS + RDS + ElastiCache
- **INFRA-02**: pgvector ivfflat/hnsw ANN index for sub-200ms p95 search at scale
- **INFRA-03**: Formal DPA with Anthropic and OpenAI before external user onboarding

## Out of Scope

| Feature | Reason |
|---------|--------|
| Mobile app | Web-first; mobile is post-MVP |
| Bot-based recording (Fireflies/Otter model) | Privacy constraint — no bots, ever |
| Admin panel with user content visibility | Architectural constraint — no admin reads user data |
| Soft-delete / deleted_at columns | Architectural constraint — hard-delete only, always |
| Manual file upload endpoint | Retro-import delivers instant history; manual upload adds friction with no benefit |
| Electron desktop app | Phase 3 — intelligence layer must be validated first |
| SOC 2 / GDPR / UAE ADGM compliance | Phase 3+ concern |

## Traceability

| Requirement | Product Phase (PRD/MVP) | Execution Phase (.planning/ROADMAP) | Status |
|-------------|--------------------------|--------------------------------------|--------|
| FRONT-01 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| FRONT-02 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| FRONT-03 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| FRONT-04 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| FRONT-05 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| FRONT-06 | Phase 1 | Phase 1 — Frontend Web App | Complete |
| TARC-01 | Phase 2 | Phase 2 — Topic Arcs and Commitment Tracker | Complete |
| TARC-02 | Phase 2 | Phase 2 — Topic Arcs and Commitment Tracker | Complete |
| CMMT-01 | Phase 2 | Phase 2 — Topic Arcs and Commitment Tracker | Complete |
| CMMT-02 | Phase 2 | Phase 2 — Topic Arcs and Commitment Tracker | Complete |
| CONN-01 | Phase 2 | Phase 3 — Connection Graph | Complete |
| CONN-02 | Phase 2 | Phase 3 — Connection Graph | Complete |
| BRIEF-01 | Phase 2 | Phase 4 — Calendar Sync and Pre-Meeting Briefs | Complete |
| BRIEF-02 | Phase 2 | Phase 4 — Calendar Sync and Pre-Meeting Briefs | Complete |
| BRIEF-03 | Phase 2 | Phase 4 — Calendar Sync and Pre-Meeting Briefs | Complete |
| CAL-01 | Phase 2 | Phase 4 — Calendar Sync and Pre-Meeting Briefs | Complete |
| CAL-02 | Phase 2 | Phase 4 — Calendar Sync and Pre-Meeting Briefs | Complete |
| DASH-01 | Phase 2 | Phase 5 — Personal Context Dashboard | Complete |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 for Phase 5 closure (dashboard complete)*
