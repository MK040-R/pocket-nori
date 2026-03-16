# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** A working professional can ask "What did we decide about X?" and get an accurate, cited answer across all their past meetings — without doing anything manually.
**Current focus:** Pilot UX polish, merge/deploy, and production QA on top of intelligent search. Upstash Redis free tier limit hit — worker needs upgrade before ingest pipeline resumes.

## Current Position

Phase: Post-Phase 5 stabilization
Plan: Active follow-up workstreams (MVP quality + pilot readiness)
Status: In progress
Last activity: 2026-03-16 — shipped Wave I onboarding redesign plus Round 2 Wave H + Wave J frontend. Home now renders `GET /home/summary` as an optional Quick Summary card; Meetings now group cards into `Today` / `This week` / `Earlier` and render topic chips from `topic_labels`. Frontend lint/build green.

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
- [UI]: The shared app shell now includes a persistent global search bar, and `/search` reads `?q=` URL state so direct links and cross-page search launches resolve into the same flow.
- [UI]: Meeting detail now uses per-item `action_type` from `GET /conversations/{id}` to separate `Commitments` and `Follow-ups` in the `Actions` tab.
- [UI]: The Meetings page now keeps a permanent `Import past meetings` entry point visible above the list so users can add more recordings at any time.
- [UI]: `/onboarding` is now a 3-step wizard with explicit skip paths, and `/meetings` shows a no-meetings prompt when users skip before importing anything.
- [UI]: Home now renders an optional Quick Summary card above the KPI grid using `GET /home/summary`, with a loading skeleton and silent hide on empty/error states.
- [UI]: Meetings now group conversation cards into `Today`, `This week`, and `Earlier`, and render up to 3 topic chips from `topic_labels` on each card.
- [API]: `POST /search/ask` adds conversational Q&A with index-based citation mapping; `POST /admin/backfill-embeddings` processes existing meetings idempotently.
- [Arch]: `_InstructorAnswer` intermediate model isolates Claude's citation output (index numbers only) from database-ID resolution, preventing structured-output validation failures.
- [Ops]: Upstash free tier (500k req/month) is exhausted; worker requires Pay As You Go upgrade to resume ingest pipeline.
- [API]: `GET /home/summary` returns AI-generated 2-3 sentence daily briefing; uses claude-sonnet-4-6 (max_tokens=200), falls back to plain text on LLM failure, cached per user per day at 6h TTL.
- [API]: `GET /conversations` now includes `topic_labels: list[str]` (up to 3 per meeting) for meeting card previews.

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

Last session: 2026-03-16
Stopped at: Wave I plus Wave H/Wave J frontend are shipped locally and validated. Next: compact live QA on Home and Meetings, then merge/deploy the frontend batch.
Resume file: None
