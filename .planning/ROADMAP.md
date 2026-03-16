# Roadmap: Pocket Nori

## Overview

The backend intelligence pipeline and the five user-surface execution phases are complete. Stabilization work is also now merged and deployed: `Insightful Dashboard` visual refresh, read-path latency reduction, durable stored topic clusters, conservative entity normalization, intelligent search (embed-at-ingest multi-table vector search + conversational Q&A), and the current pilot UX cleanup through Wave J. Partial production QA confirmed the deployed shell and auth redirect are live; next is a manual signed-in QA pass, then Upstash upgrade/backfill work and broader post-MVP hardening.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Frontend Web App** - Build the Next.js UI that surfaces all existing backend capabilities to users
- [x] **Phase 2: Topic Arcs and Commitment Tracker** - Backend computes topic timelines; user can track open commitments across meetings
- [x] **Phase 3: Connection Graph** - Backend detects meeting connections; user can see which meetings share topics or entities
- [x] **Phase 4: Calendar Sync and Pre-Meeting Briefs** - Google Calendar integration triggers automated briefs before each meeting
- [x] **Phase 5: Personal Context Dashboard** - Unified dashboard surface for upcoming meetings, recent activity, commitments, and new connections

## Phase Details

### Phase 1: Frontend Web App
**Goal**: Users can access Pocket Nori through a web browser, log in, import their meetings, and interact with all intelligence the backend already produces
**Depends on**: Nothing (backend is already complete; this surfaces it)
**Requirements**: FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, FRONT-06
**Success Criteria** (what must be TRUE):
  1. User can open the web app, click "Sign in with Google," and land on their dashboard without any backend errors
  2. User can trigger Drive retro-import from the UI and watch a live progress indicator update as meetings are indexed
  3. User can browse a paginated list of all their imported meetings and click one to see its extracted topics and commitments
  4. User can click any topic or commitment entry and see the exact source quote with speaker name and timestamp highlighted
  5. User can type a natural-language question in a search box and receive ranked meeting segment results with source citations
**Plans**: TBD

Plans:
- [x] 01-01: Auth flow and dashboard shell (Google OAuth callback, session cookie, empty state)
- [x] 01-02: Onboarding and import UI (Drive import trigger, live progress via polling /onboarding/import/status)
- [x] 01-03: Meeting list and conversation detail views (topics, commitments, citations)
- [x] 01-04: Semantic search UI (question input, ranked results, citation display)

### Phase 2: Topic Arcs and Commitment Tracker
**Goal**: Users can see how subjects evolved across meetings over time, and can manage open commitments in one consolidated view
**Depends on**: Phase 1
**Requirements**: TARC-01, TARC-02, CMMT-01, CMMT-02
**Success Criteria** (what must be TRUE):
  1. User can navigate to a topic and see a chronological timeline of every meeting where that topic appeared, with dates and brief context per entry
  2. User can click any timeline entry and jump to the exact transcript segment that produced it
  3. User can open a commitments view showing all open commitments across all meetings, filterable by assignee and showing deadline where extracted
  4. User can mark a commitment as resolved and see it removed from the open commitments list immediately
**Plans**: TBD

Plans:
- [x] 02-01: Topic Arc backend — compute and store topic_arcs and topic_arc_conversation_links from existing topics + conversations data
- [x] 02-02: Topic Arc API endpoint — GET /topics/{id}/arc returning timeline with segment citations
- [x] 02-03: Commitment tracker API — GET /commitments with filters, PATCH /commitments/{id} mark-resolved (stub exists, needs full implementation)
- [x] 02-04: Topic arc and commitment UI surfaces in the frontend

### Phase 3: Connection Graph
**Goal**: Users can see which meetings are connected by shared topics or entities, and understand exactly what links them
**Depends on**: Phase 2
**Requirements**: CONN-01, CONN-02
**Success Criteria** (what must be TRUE):
  1. User can open a meeting and see a list of other meetings that share topics or entities with it
  2. Each connection entry clearly states what links the two meetings (shared entity name, topic label, or commitment thread) — not just a list of meeting titles
  3. The /conversations/{id}/connections endpoint returns real data (currently a stub returning [])
**Plans**: TBD

Plans:
- [x] 03-01: Connection detection backend — Celery task or on-demand computation comparing topic/entity overlap across conversations, writing to connections and connection_linked_items tables
- [x] 03-02: Connections API endpoint — complete the stub at GET /conversations/{id}/connections with real data and linked item explanations
- [x] 03-03: Connection UI surface — meeting connection display within conversation detail view

### Phase 4: Calendar Sync and Pre-Meeting Briefs
**Goal**: Users receive a complete, cited pre-meeting brief automatically for eligible recurring meetings — no manual action required
**Depends on**: Phase 3
**Requirements**: CAL-01, CAL-02, BRIEF-01, BRIEF-02, BRIEF-03
**Success Criteria** (what must be TRUE):
  1. Google Calendar events are auto-linked to imported meetings by time-window matching — user sees the calendar event name on each meeting that corresponds to it
  2. Upcoming recurring meetings (with at least one prior indexed session) are read from Google Calendar; a brief is generated and ready 10-15 minutes before start
  3. The brief contains relevant topic context, open commitments, and connected meeting references — all three components present
  4. Every claim or fact in a brief links back to a specific transcript segment the user can click to verify
  5. The /calendar/today endpoint returns real upcoming meetings (currently a stub returning [])
**Plans**: TBD

Plans:
- [x] 04-01: Google Calendar sync backend — read calendar events via Google Calendar API, match to conversations by time window, write links to conversations table (drive_file_id or new calendar_event_id column)
- [x] 04-02: Brief generation Celery task — compose brief from topic_arcs + commitments + connections scoped to the meeting's participants and topic overlap; use claude-opus-4-6 sparingly
- [x] 04-03: Brief scheduler — user-scoped recurring scheduler task that reads upcoming events and dispatches brief generation at T-12 (or immediate if already within window)
- [x] 04-04: Brief API and citation surface — `GET /briefs/{id}` + `GET /briefs/latest`, citation segment surface, and frontend brief detail page with meeting deep links

### Phase 5: Personal Context Dashboard
**Goal**: Users can open a single dashboard showing upcoming meeting context, recent indexed activity, open commitments, and newly detected cross-meeting links
**Depends on**: Phase 4
**Requirements**: DASH-01
**Success Criteria** (what must be TRUE):
  1. `/today` shows upcoming meetings, recent indexed conversations, open commitments, and newly detected connections in one coherent view
  2. Each dashboard section links directly to source meeting/brief screens so users can drill down quickly
  3. Data shown in the dashboard is fully user-scoped and sourced from live backend APIs (no stubs)
**Plans**: TBD

Plans:
- [x] 05-01: Dashboard backend aggregation surface — extend today-context API to include recent indexed activity and recent/new connections
- [x] 05-02: Dashboard UI completion — render all dashboard sections with deep links and clear empty states

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Frontend Web App | 4/4 | Complete | 2026-03-11 |
| 2. Topic Arcs and Commitment Tracker | 4/4 | Complete | 2026-03-11 |
| 3. Connection Graph | 3/3 | Complete | 2026-03-11 |
| 4. Calendar Sync and Pre-Meeting Briefs | 4/4 | Complete | 2026-03-11 |
| 5. Personal Context Dashboard | 2/2 | Complete | 2026-03-11 |

## Active Follow-up Tracks (Post-Phase 5)

- [x] Visual refresh — deployed `Insightful Dashboard` styling (light workspace, dark navigation rail, stronger card hierarchy)
- [x] Read-path latency reduction — deployed user-scoped caching and frontend overfetch reduction on the slowest views
- [x] Pilot UX polish waves C-J — shipped Home/Actions naming cleanup, profile menu and entity management, meeting-detail simplification, persistent global search, persistent Meetings import access, onboarding wizard redesign, Home Quick Summary, and grouped Meetings cards with topic chips
- [ ] Topic intelligence cleanup — current active workstream
  - Deployed and verified live:
    - stored `topic_clusters` canonical layer with `topics.cluster_id` and `topic_arcs.cluster_id`
    - background-topic filtering during extraction
    - ingestion-time lexical-first + bounded LLM semantic merge through `src/llm_client.py`
    - per-user `POST /topics/recluster` worker path for historical backfill
    - cluster-backed `/topics`, topic detail, topic arc, dashboard counts, and search/topic linking
    - bounded `lexical-all + semantic-recent` recluster mode to stay within worker limits
    - stable topic-cluster IDs across future recluster runs where lineage is concrete
  - Remaining follow-up:
    - decide whether already-broken historical topic URLs need alias/redirect support
    - deploy and verify conservative entity normalization (`/entities`, dashboard `entity_count`)

## Quality Gate

- 2026-03-11 milestone validation (before Phase 4 planning):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (87 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 04-01 validation (calendar sync backend):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (91 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 04-02 validation (brief generation task):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (92 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 04-03 validation (recurring brief scheduler):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (97 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 04-04 validation (brief API + frontend citation surface):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (97 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 phase closure validation (Phase 4 complete):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (97 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 05-01 validation (dashboard backend aggregation):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (97 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-11 plan 05-02 validation (dashboard UI completion):
  - `ruff check src tests` ✅
  - `mypy src tests` ✅
  - `pytest -q` ✅ (97 passed, 7 skipped)
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-12 deployed visual refresh validation:
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-12 deployed read-path performance validation:
  - `pytest -q` ✅ (98 passed, 7 skipped)
  - `mypy src/ --ignore-missing-imports` ✅
  - `ruff check . && ruff format --check .` ✅
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-12 durable topic-intelligence validation (local, pre-deploy):
  - `pytest -q` ✅ (104 passed, 7 skipped)
  - `mypy src/ --ignore-missing-imports` ✅
  - `ruff check . && ruff format --check .` ✅
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-13 entity normalization validation (local):
  - `pytest -q tests/test_entities.py tests/test_index_stats.py` ✅ (6 passed)
  - `pytest -q` ✅ (112 passed, 7 skipped)
  - `mypy src/ --ignore-missing-imports` ✅
  - `ruff check . && ruff format --check .` ✅
- 2026-03-16 Wave I + Wave H/Wave J frontend validation (local):
  - `frontend: npm run lint && npm run build` ✅
- 2026-03-16 partial production QA after deploy:
  - deployed frontend root reachable ✅
  - `/auth/login` redirects to Google account chooser ✅
  - unauthenticated protected routes show session-expired state ✅
  - full signed-in walkthrough blocked by environment/tooling limits ⚠️
