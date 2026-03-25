# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.
**Current focus:** Operational rollout of the local intelligence stack. Local code is ready through TopicNode spine, Entity Nodes, Knowledge Graph, graph APIs, and advanced resolution; next is Render Redis cutover, backend/worker deploy, migrations `014`, `015`, `017`, and `018`, per-user rebuild/backfill, and signed-in production QA.

## Current Position

Phase: Post-Phase 5 stabilization
Plan: Active follow-up workstreams (MVP quality + pilot readiness)
Status: In progress
Last activity: 2026-03-25 — completed the local intelligence stack implementation beyond Milestone 1 closeout: TopicNode bridge semantics, deterministic provenance, canonical entity nodes, knowledge graph edges + evidence, graph APIs, and advanced write-time enrichment. Production rollout is still pending.

Progress: [██████████] 100% core phases complete; stabilization work active

## Performance Metrics

**Velocity:**
- Total plans completed: 17
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Frontend Web App | 4 | - | - |
| 2. Topic Arcs and Commitment Tracker | 4 | - | - |
| 3. Connection Graph | 3 | - | - |
| 4. Calendar Sync and Pre-Meeting Briefs | 4 | - | - |
| 5. Personal Context Dashboard | 2 | - | - |

**Recent Trend:**
- Last 5 plans: 04-01, 04-02, 04-03, 04-04, 05-01/05-02
- Trend: Execution stable, all validations green

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Arch]: Codex executes both backend and frontend workstreams end-to-end in this repository.
- [Arch]: Legacy `/calendar/today` stub has been replaced with live Google Calendar sync + conversation linking.
- [Arch]: `generate_brief` placeholder has been replaced; only `process_transcript` remains a legacy placeholder task.
- [Arch]: Topic Arc is now computed and persisted via `topic_arcs` and `topic_arc_conversation_links`, surfaced through `GET /topics/{id}/arc`.
- [Arch]: Commitments API now supports assignee filtering (`assignee` / `attributed_to`) and legacy status compatibility (`resolved`, `done`, `cancelled`).
- [Data]: Migration `005_commitment_status_alignment.sql` normalizes commitment status values to `open`/`resolved`.
- [Arch]: `/conversations/{id}/connections` now computes and persists real cross-meeting links using shared topics/entities/commitment signatures.
- [UI]: Meeting detail now renders live connection cards with rationale and linked-meeting metadata.
- [Quality]: Phase handoff QA gate is now tracked as `ruff + mypy + pytest + frontend lint/build`, all green on 2026-03-11.
- [Arch]: `/calendar/today` now serves live Google Calendar events and performs conversation↔calendar linking (`conversations.calendar_event_id`) during sync.
- [Arch]: `generate_brief` is now a real worker flow (not stub): context assembly + LLM brief generation + persistence to `briefs` and `brief_*_links`.
- [Arch]: Recurring brief scheduling is implemented via `schedule_recurring_briefs`, with recurring-series history checks and target-meeting overrides into `generate_brief`.
- [API]: Brief retrieval surface added via `GET /briefs/latest` and `GET /briefs/{id}` with resolved transcript citation segments for topic/commitment evidence.
- [UI]: Meeting detail now exposes latest brief links; dedicated brief page renders generated content and citation transcript snippets.
- [API]: `/calendar/today` now returns four dashboard feeds: `upcoming_meetings`, `open_commitments`, `recent_activity`, and `recent_connections`.
- [UI]: `/today` now renders complete dashboard sections with deep links into `/meetings/{id}` for activity, commitments, and connection context.
- [UI]: Design system has shifted from `Private Office` to `Insightful Dashboard`: light workspace, dark navigation rail, Inter typography, stronger card depth.
- [Perf]: Read-heavy endpoints now use short user-scoped caching and dashboard no longer overfetches commitments; topic detail loads arc separately from core detail.
- [Arch]: Topic intelligence now uses TopicNode semantics at runtime via a bridge module over the existing canonical storage table; physical `topic_nodes` cutover is deferred to migration `016`.
- [API]: `POST /topics/recluster` is the per-user trigger for rebuilding stored topic nodes and arcs for already indexed meetings.
- [Ops]: Historical recluster now runs as `lexical-all + semantic-recent` rather than a full semantic pass across the entire archive, to stay within worker time limits while still testing semantic merge quality on current data.
- [Arch]: Recluster preserves canonical topic IDs when rebuilt nodes overlap the same underlying topic rows, so durable topic URLs stay stable across rebuilds where lineage is clear going forward.
- [Product]: Background/admin/introductory topics are now filtered before insert, and topic browse surfaces default to recurring clusters while singleton topics remain searchable.
- [Product]: `/entities` and dashboard `entity_count` now share a conservative normalization layer for safe brand aliases (`N8`/`N8N`, `company`/`product` variants) and unambiguous short-form person names.
- [Product]: Despite phase completion, Pocket Nori remains in MVP cleanup mode; post-MVP hardening is deferred until topic quality and remaining pilot-critical UX issues are acceptable.
- [Search]: Search is now fully intelligent — LLM understands each meeting once at ingest (digest + topic/entity embeddings stored), search queries pre-stored vectors at ~$0.00001/query with zero LLM tokens.
- [UI]: The shared app shell now includes a persistent global search bar, and `/search` reads `?q=` URL state so direct links and cross-page search launches resolve into the same flow.
- [UI]: Meeting detail now uses per-item `action_type` from `GET /conversations/{id}` to separate `Commitments` and `Follow-ups` in the `Actions` tab.
- [UI]: The Meetings page now keeps a permanent `Import past meetings` entry point visible above the list so users can add more recordings at any time.
- [UI]: `/onboarding` is now a 3-step wizard with explicit skip paths, and `/meetings` shows a no-meetings prompt when users skip before importing anything.
- [UI]: Home now renders an optional Quick Summary card above the KPI grid using `GET /home/summary`, with a loading skeleton and silent hide on empty/error states.
- [UI]: Meetings now group conversation cards into `Today`, `This week`, and `Earlier`, and render up to 3 topic chips from `topic_labels` on each card.
- [API]: `POST /search/ask` adds conversational Q&A with index-based citation mapping; `POST /admin/backfill-embeddings` processes existing meetings idempotently.
- [Arch]: `_InstructorAnswer` intermediate model isolates Claude's citation output (index numbers only) from database-ID resolution, preventing structured-output validation failures.
- [Data]: Derived topic, commitment, and entity citations now use deterministic segment matching with scored provenance metadata; weak evidence produces no fabricated citation.
- [API]: `POST /admin/backfill-segment-links` now exists to repair stored citations for existing indexed meetings.
- [Search]: Topic-node rebuild now refreshes the final canonical node embeddings after metadata stabilization so search stays aligned after backfill.
- [Arch]: Canonical entity identity now persists in `entity_nodes`; extraction assigns `entity_node_id`, browse/search read node-backed entities, and rebuild/backfill preserves stable node IDs where lineage is clear.
- [Arch]: The knowledge graph now persists typed `knowledge_edges` plus `knowledge_edge_evidence`; graph-backed materialization preserves `connections` as the compatibility read model for existing surfaces.
- [API]: `GET /graph/neighbors/{node_type}/{node_id}`, `GET /graph/subgraph`, and `GET /graph/path` now exist as explainable graph surfaces.
- [API]: `GET /admin/jobs/{job_id}` now exposes maintenance-task status so rollout jobs can be queued and verified one-by-one.
- [Ops]: `scripts/run_rollout_backfill.py` can queue and poll the rollout maintenance sequence from a bearer-authenticated terminal session.
- [Ops]: Operational rollout uses Render Redis for production broker/cache usage via the existing `UPSTASH_REDIS_URL` environment variable.
- [QA]: Production frontend is reachable and auth redirect is live, but a full signed-in production walkthrough could not be completed from this environment because shell-based network tools could not resolve the production hosts and browser automation could not complete Google-authenticated flows reliably.
- [API]: `GET /home/summary` returns AI-generated 2-3 sentence daily briefing; uses claude-sonnet-4-6 (max_tokens=200), falls back to plain text on LLM failure, cached per user per day at 6h TTL.
- [API]: `GET /conversations` now includes `topic_labels: list[str]` (up to 3 per meeting) for meeting card previews.

### Pending Todos

- Provision Render Redis and set its connection URL into the existing `UPSTASH_REDIS_URL` env var
- Deploy backend + worker together on the operational rollout commit
- Apply migrations `014_topic_node_bridge.sql`, `015_provenance_links.sql`, `017_entity_nodes.sql`, and `018_knowledge_edges.sql`
- Run `/topics/recluster` per pilot user
- Run `/admin/backfill-segment-links` per pilot user
- Run `/admin/rebuild-entity-nodes` per pilot user
- Run `/admin/backfill-knowledge-graph` per pilot user
- Verify Search, Topics, Entities, Dashboard, Meetings, Home, `/search/ask`, and graph-backed connection surfaces after rebuild/backfill
- Decide later whether historical pre-fix topic URLs need redirect aliases
- Defer `016_topic_node_cutover.sql` until runtime no longer depends on legacy storage names

### Blockers/Concerns

- Phase execution is fully owned by Codex. Plan and implementation stay in one workflow; no cross-agent handoff assumptions.
- Phase 4 brief generation uses claude-opus-4-6 — use sparingly per cost constraint (~$50/month target).

## Session Continuity

Last session: 2026-03-25
Stopped at: Local intelligence-stack implementation is complete and validated. Next is Render Redis cutover, deploy, apply migrations `014`, `015`, `017`, and `018`, run per-user rebuild/backfill, then finish signed-in production QA.
Resume file: None
