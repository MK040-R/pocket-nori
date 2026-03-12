# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.
**Current focus:** MVP stabilization, with stored topic-cluster deployment and recluster verification as the active workstream

## Current Position

Phase: Post-Phase 5 stabilization
Plan: Active follow-up workstreams (MVP quality + pilot readiness)
Status: In progress
Last activity: 2026-03-12 — implemented the durable topic-intelligence batch locally: stored `topic_clusters`, write-time semantic merge, background-topic filtering, and a per-user recluster worker/route. Next step is deploy + run recluster + production QA.

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
- [Product]: Background/admin/introductory topics are now filtered before insert, and topic browse surfaces default to recurring clusters while singleton topics remain searchable.
- [Product]: Despite phase completion, Farz remains in MVP cleanup mode; post-MVP hardening is deferred until topic quality and remaining pilot-critical UX issues are acceptable.

### Pending Todos

- Deploy migration `007_topic_clusters.sql` and the stored-cluster API/worker changes
- Trigger and validate per-user topic recluster/backfill in production
- Run production QA on Search, Topics, Dashboard, Commitments, and meeting detail against stored clusters
- Resume post-MVP hardening roadmap after MVP topic quality is acceptable

### Blockers/Concerns

- Phase execution is fully owned by Codex. Plan and implementation stay in one workflow; no cross-agent handoff assumptions.
- Phase 4 brief generation uses claude-opus-4-6 — use sparingly per cost constraint (~$50/month target).

## Session Continuity

Last session: 2026-03-12
Stopped at: Durable topic-intelligence batch implemented locally; next step is deploy + per-user recluster + production QA.
Resume file: None
