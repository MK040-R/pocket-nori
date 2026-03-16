# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.
**Current focus:** Intelligent search shipped (embed-at-ingest, multi-table vector search, conversational Q&A). Upstash Redis free tier limit hit — worker needs upgrade before ingest pipeline resumes.

## Current Position

Phase: Post-Phase 5 stabilization
Plan: Active follow-up workstreams (MVP quality + pilot readiness)
Status: In progress
Last activity: 2026-03-15 — shipped intelligent search (migration 009, digest generation, multi-table vector search, /search/ask Q&A, /admin/backfill-embeddings). PR #14 open. Two post-deploy bugs fixed (citation UUID resolution, unused type: ignore). Upstash free tier limit hit — worker crashes until plan upgraded.

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
- [Arch]: Topic intelligence now uses a durable write-time model: `topic_clusters` are canonical, `topics.cluster_id` / `topic_arcs.cluster_id` persist membership, and semantic merge is allowed only during ingestion/backfill through `src/llm_client.py`.
- [API]: `POST /topics/recluster` now exists as a per-user trigger for rebuilding stored topic clusters and arcs for already indexed meetings.
- [Ops]: Historical recluster now runs as `lexical-all + semantic-recent` rather than a full semantic pass across the entire archive, to stay within worker time limits while still testing semantic merge quality on current data.
- [Arch]: Recluster now preserves topic-cluster IDs when rebuilt clusters overlap the same underlying topic rows, so durable topic URLs stay stable across rebuilds where lineage is clear going forward.
- [Product]: Background/admin/introductory topics are now filtered before insert, and topic browse surfaces default to recurring clusters while singleton topics remain searchable.
- [Product]: `/entities` and dashboard `entity_count` now share a conservative normalization layer for safe brand aliases (`N8`/`N8N`, `company`/`product` variants) and unambiguous short-form person names.
- [Product]: Despite phase completion, Pocket Nori remains in MVP cleanup mode; post-MVP hardening is deferred until topic quality and remaining pilot-critical UX issues are acceptable.
- [Search]: Search is now fully intelligent — LLM understands each meeting once at ingest (digest + topic/entity embeddings stored), search queries pre-stored vectors at ~$0.00001/query with zero LLM tokens.
- [API]: `POST /search/ask` adds conversational Q&A with index-based citation mapping; `POST /admin/backfill-embeddings` processes existing meetings idempotently.
- [Arch]: `_InstructorAnswer` intermediate model isolates Claude's citation output (index numbers only) from database-ID resolution, preventing structured-output validation failures.
- [Ops]: Upstash free tier (500k req/month) is exhausted; worker requires Pay As You Go upgrade to resume ingest pipeline.

### Pending Todos

- **URGENT**: Upgrade Upstash Redis to Pay As You Go — free tier limit exhausted, worker cannot start
- Restart Pocket Nori worker on Render after Upstash upgrade
- Merge PR #14 (`feat/durable-topic-clusters`) → Render auto-deploys
- Run `POST /admin/backfill-embeddings` once after deploy to process all existing meetings
- Verify `/search/ask` returns cited answers and grouped search results include topic/meeting/entity types
- Run compact production QA on Search, Topics, Dashboard, Commitments against stored clusters
- Decide whether historical pre-fix topic URLs need redirect aliases
- Resume post-MVP hardening roadmap after MVP topic quality is acceptable

### Blockers/Concerns

- Phase execution is fully owned by Codex. Plan and implementation stay in one workflow; no cross-agent handoff assumptions.
- Phase 4 brief generation uses claude-opus-4-6 — use sparingly per cost constraint (~$50/month target).

## Session Continuity

Last session: 2026-03-15
Stopped at: Intelligent search shipped and on PR #14. Two post-deploy bugs fixed in CI. Upstash Redis free tier hit — upgrade required before worker can restart and ingest pipeline resumes.
Resume file: None
