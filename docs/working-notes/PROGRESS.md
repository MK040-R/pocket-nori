# Pocket Nori — Build Progress

> This document is written for non-technical readers. It is updated automatically after every completed task.
> Last updated: 2026-03-12 (durable topic intelligence implemented locally; deploy + recluster next)

---

## What is Pocket Nori?

Pocket Nori is a personal intelligence layer for working professionals. It connects to your Google Calendar and meeting recordings, listens to what happens in your meetings, and automatically surfaces what matters — the topics discussed, the commitments made, the people mentioned, and how everything connects over time. Before your next meeting, it gives you a personalised briefing based on everything that was discussed in past meetings with the same people or on the same topic. Think of it as a private, AI-powered chief of staff that never forgets anything said in a meeting, and always prepares you for the next one.

---

## How Building Software Works — The Phases Explained

Building a software product from scratch happens in stages, like constructing a building:

| Phase | Analogy | What it means for Pocket Nori |
|-------|---------|------------------------|
| **Phase 0a — Proof of Concept** | Testing the materials before building | We tried each piece of technology separately to see if it works at all — can we capture audio? Can AI extract useful information from a transcript? |
| **Phase 0 — Foundation** | Laying pipes, wiring, and concrete | Building the invisible infrastructure the app runs on — the server, the database, the login system, the background processing engine |
| **Phase 1 — First Working Product** | Putting up walls and a roof | The first version users can actually interact with — import past meetings, get AI summaries, search across meetings |
| **Phase 2 — Full Product** | Interior design, finishing, furniture | The complete dashboard — topic timelines, pre-meeting briefs, commitment tracker, cross-meeting connections |

**Phases 0, 1, 2, 3, 4, and 5 are complete.** Current execution focus is **MVP topic intelligence cleanup**, with the stored cluster model implemented locally and awaiting deployment + per-user backfill.

---

## Overall Progress

| Milestone | Status | Notes |
|-----------|--------|-------|
| Phase 0a — Proof of Concept | ✅ Complete | All 5 technology tests passed |
| Infrastructure & credentials set up | ✅ Complete | All services connected |
| Code repository (GitHub) | ✅ Complete | `MK040-R/pocket-nori` |
| Running web server | ✅ Complete | App starts, responds to requests |
| Data blueprint (9 entities) | ✅ Complete | All data types defined |
| Database schema | ✅ Complete | Ready to apply to Supabase |
| Per-user privacy enforcement | ✅ Complete | 6-layer isolation built in |
| Background job system | ✅ Complete | Async processing ready |
| Google Sign-In | ✅ Complete | Login/callback endpoints built |
| Automated test suite | ✅ Complete | 10 tests passing |
| AI module (single controlled gateway) | ✅ Complete | `src/llm_client.py` |
| Database connector | ✅ Complete | `src/database.py` |
| Apply database schema to Supabase | ✅ Complete | Migration applied — all 9 tables live |
| Junction table privacy enforcement | ✅ Complete | Migration 002 — all 8 link tables have FORCE RLS |
| Engineer QA review | ✅ Complete | 8 bugs found and fixed, 75/75 QA checks passing |
| Phase 0 complete | ✅ Complete | Foundation fully built and independently verified |
| Phase 1 Wave 1 — Google Drive import + transcription pipeline | ✅ Complete | Drive listing, ingest task, 22 tests passing |
| Phase 1 Wave 2 — AI extraction pipeline + pgvector | ✅ Complete | Topics, commitments, entities, embeddings, conversations API |
| Phase 1 Wave 3 — Semantic search + supporting endpoints | ✅ Complete | POST /search, topics, commitments, index stats, calendar |
| Backend security hardening | ✅ Complete | Job ownership checks, API contract fixes, 60 tests |
| Render deployment config | ✅ Complete | render.yaml — 1 API + 3 workers, ready to connect |
| Phase 1 Wave 4 — Web UI | ⏳ In progress | Next.js frontend (Codex building) |
| Phase 2 — Pre-meeting briefs | ⏳ Weeks 13–20 | |
| Phase 2 — Full dashboard | ⏳ Weeks 13–20 | |
| Phase 2 — Pre-meeting briefs | ⏳ Weeks 13–20 | |
| Phase 2 — Full dashboard | ⏳ Weeks 13–20 | |

---

## What Has Been Completed — In Plain English

### ✅ Phase 0a — Proof of Concept (5 technology tests)
**What happened:** Before writing any real product code, we ran 5 isolated experiments to confirm that each piece of technology we plan to use actually works the way we need it to.

| Test | What we proved |
|------|---------------|
| Audio capture | We can capture audio from a live Google Meet session |
| Transcription (Deepgram) | We can convert that audio into accurate text, with speaker labels ("Alex said…", "Priya said…") |
| AI extraction (Claude) | We can feed a meeting transcript to AI and reliably get back structured data — topics, commitments, people mentioned |
| Database privacy (Supabase) | We can store data so that User A's meetings are completely invisible to User B, even at the database level |
| Background jobs (Celery + Redis) | We can process meetings in the background without making the user wait — jobs queue up and run asynchronously |

**Why it mattered:** These 5 tests de-risked the entire product. If any of them had failed, we would have had to rethink the technology choices before writing a single line of product code. All 5 passed.

---

### ✅ Infrastructure & Credentials
**What happened:** We connected all the external services the app needs to function.

| Service | What it does for Pocket Nori |
|---------|----------------------|
| **Supabase** | The database where all user data is stored securely |
| **Upstash Redis** | A fast memory store that queues background jobs |
| **Anthropic (Claude AI)** | The AI that reads transcripts and extracts insights |
| **Deepgram** | The service that converts audio into text |
| **Google OAuth** | Lets users sign in with their Google account |

**Why it mattered:** Without these credentials, none of the code can run. This was the final unblocking step before building could start.

---

### ✅ GitHub Repository
**What happened:** The codebase is now stored on GitHub at `MK040-R/pocket-nori`. Every change made going forward is tracked, versioned, and recoverable.

**Why it mattered:** This is the single source of truth for all code. It enables collaboration, rollback if something goes wrong, and a CI/CD pipeline in the future.

---

### ✅ Running Web Server (FastAPI Application)
**What happened:** We built the skeleton of the Pocket Nori backend — a web server that starts up, checks that all credentials are present, and listens for incoming requests.

What it can currently do:
- Start up and refuse to run if any required credential is missing (fail-fast protection)
- Respond to a health check: `GET /health` → `{"status": "ok"}`
- Show an interactive API documentation page at `/docs`
- Accept requests and route them to the right handler

**Analogy:** This is like the front door and reception desk of a building. Nothing is decorated yet, but the structure is standing and the door opens.

**Why it mattered:** Every feature in Phase 1 and 2 will be delivered as an endpoint on this server. Now we have somewhere to attach them.

---

### ✅ Data Blueprint — 9 Core Data Types
**What happened:** We defined the exact shape of every piece of information Pocket Nori stores. Think of this like designing the filing system before you start filing things.

| Data type | What it represents |
|-----------|-------------------|
| **Conversation** | A single meeting (date, title, source, duration) |
| **TranscriptSegment** | One person speaking for a stretch of time — the atomic unit of a meeting |
| **Topic** | A subject discussed in a meeting ("Q3 budget", "new hire") |
| **Commitment** | Something someone agreed to do ("Alex will send the proposal by Friday") |
| **Entity** | A person, company, project, or product mentioned |
| **TopicArc** | How a topic evolves across multiple meetings over time |
| **Connection** | A link between two meetings or topics ("This relates to what was said in the March 3rd call") |
| **Brief** | A pre-meeting briefing document, auto-generated by AI |
| **Index** | Each user's personal index — their private universe of meetings and insights |

**Why it mattered:** Getting the data model right at this stage prevents costly redesigns later. Every AI extraction, every search result, every briefing is built on top of this structure.

---

### ✅ Database Schema
**What happened:** We wrote the SQL script that will create all 9 data tables inside Supabase, with all privacy rules and performance indexes built in. It is written and ready — the next step is running it.

**Privacy baked in:** Every table has Row Level Security enforced. This means the database itself will reject any query that tries to access another user's data — it's not just enforced in the code, it's enforced at the lowest possible level.

**Why it mattered:** The database is where all user data lives permanently. Getting the structure, privacy rules, and performance optimisations right here saves a lot of pain later.

---

### ✅ Per-User Privacy — 6-Layer Isolation
**What happened:** We built privacy enforcement at 6 separate layers of the system. Even if one layer has a bug, 5 others still protect the user.

| Layer | What it does |
|-------|-------------|
| PostgreSQL RLS | Database rejects cross-user queries at the lowest level |
| Storage paths | Files stored under `/users/{your-id}/…` — other users' paths literally don't exist to you |
| Redis namespacing | Cache keys scoped to `user:{your-id}:…` |
| Vector search | AI similarity searches always filter by your user ID first |
| LLM calls | Your transcript text is never mixed with another user's in an AI call |
| Background jobs | Every job carries your user ID and validates ownership before touching data |

**Why it mattered:** This is the most critical non-negotiable in the product. Pocket Nori handles private meeting conversations. A breach of user isolation would be catastrophic. Building it in at the foundation means it's never an afterthought.

---

### ✅ Background Job System (Celery + Redis)
**What happened:** We set up the system that processes meetings in the background. When a meeting recording is imported, Pocket Nori doesn't make you wait — it queues the work and processes it asynchronously.

**Analogy:** Like dropping a letter in a post box. You don't stand there waiting for it to be delivered. You drop it and go. The postal system handles the rest.

Current jobs defined:
- `process_transcript` — takes a transcript and queues it for AI extraction
- `generate_brief` — takes a conversation and queues a pre-meeting brief for generation

**Why it mattered:** Without this, importing a 1-hour meeting would make the app freeze for minutes. Background processing is what makes the app feel fast and responsive.

---

### ✅ Google Sign-In
**What happened:** We built the login flow. Users will be able to click "Sign in with Google", grant Pocket Nori permission to read their calendar, and be authenticated in the app.

Two endpoints built:
- `GET /auth/login` — redirects to Google's consent screen
- `GET /auth/callback` — receives the user back from Google, exchanges the code for a session, and logs them in

**Why it mattered:** Google login is the front door for users. It also gives Pocket Nori permission to read the user's Google Calendar (needed for pre-meeting briefs) and eventually Google Meet recordings.

---

### ✅ Automated Test Suite
**What happened:** We wrote automated tests that run every time a code change is made. They verify that the system behaves correctly and that privacy rules hold.

Current test coverage:
- 10 unit tests — verify background job logic (no external services needed to run these)
- RLS isolation tests — verify User A cannot read User B's data (runs against real Supabase)

**Why it mattered:** Tests are the safety net that catches regressions. As the codebase grows, they ensure that adding new features doesn't break existing ones.

---

## ✅ Wave 3 — Completed

### ✅ AI Gateway Module (`src/llm_client.py`)
**What it is:** A single, controlled entry point for all AI calls. Every time Pocket Nori needs to talk to Claude (for extracting topics, writing briefs, etc.), it goes through this one module — nowhere else.

Four functions built:
- `extract_topics` — reads a transcript and returns the main topics discussed
- `extract_commitments` — reads a transcript and returns action items with owners and due dates
- `extract_entities` — reads a transcript and returns people, projects, companies, and products mentioned
- `generate_brief` — given context about past meetings, writes a pre-meeting briefing

Uses the faster, cheaper Claude Sonnet model for the three extraction tasks, and the more powerful Claude Opus model for brief generation (briefs are used once per meeting and justify the higher quality).

**Why it matters:** Centralising AI calls means we can control costs, add safe logging (without ever logging private transcript content), and change models in one place if needed.

### ✅ Database Connector (`src/database.py`)
**What it is:** A reusable connection to the Supabase database. Rather than every part of the app setting up its own connection, they all use one controlled module.

Two modes built:
- `get_client(user_jwt)` — connects as the actual user, so all database privacy rules (RLS) are enforced. Used by all API routes and background workers.
- `get_admin_client()` — connects as the database administrator, bypassing privacy rules. Used ONLY for running migrations. Logs a warning every time it's called as a safety guard.

**Why it matters:** Consistent, safe database access across the entire codebase. The admin client's warning log makes it impossible to accidentally use it in the wrong place without a visible signal.

### ✅ Database Schema Applied to Supabase
**What happened:** Ran the migration script against the live Supabase project. All 9 tables now exist in the database with all privacy rules and performance indexes in place.

**Why it matters:** The database is now live and ready to store real data. The data layer is complete.

---

## ✅ Engineer QA Review — Completed

After the foundation was built, an independent senior engineer reviewed all the code and ran QA without seeing our results. The outcome: 8 real bugs were found and fixed, and 75 automated checks now pass.

### What the engineer found and fixed

| Issue | What it was | Why it mattered |
|---|---|---|
| **Login system (JWT validation)** | The original code only understood one type of login token (HS256). Supabase uses a more secure format in production (RS256). | Without this fix, users would be rejected when trying to log in on the live server. |
| **Database connection auth** | The original way of passing a user's login credentials to the database was broken. | Queries would have failed silently when the app tried to read or write data on behalf of a user. |
| **Redis/Celery TLS** | The background job system was missing required security settings for Upstash's encrypted connection. | Background jobs would have crashed immediately when deployed. |
| **Google Drive access scope** | The Google login was not requesting permission to read Drive files. | Phase 1's meeting import would have been blocked — Google would refuse access to recordings. |
| **Junction table privacy** | 8 "link" tables (which connect topics to meetings, commitments to transcript quotes, etc.) had no privacy rules. | Any user could theoretically see another user's links between data. |
| **Commitment status mismatch** | The app model and database used slightly different words for commitment status. | Would have caused validation errors when saving commitments. |
| **Test reliability** | Tests were failing in environments without access to external services. | CI pipeline would have been broken for any developer not connected to real credentials. |

### What the engineer confirmed was correct
Everything else — the server structure, the AI gateway, the data models, the per-user isolation architecture, the Celery task design — was confirmed solid.

### The independent result
Running the full QA script after fixes: **75 of 75 checks passing (100%)**.

---

## Full Roadmap

### Phase 0 — Foundation (COMPLETE ✅)
What was built: The invisible infrastructure. No user-facing features.
Outcome: A secure, running backend that can accept requests, store data, process jobs, and authenticate users. Independently verified by a second engineer — 75/75 QA checks passing.

### Phase 1 — First Working Product (IN PROGRESS ✅ Waves 1–3 complete, Wave 4 in progress)

### Phase 1 — First Working Product (Weeks 5–12)
What becomes usable: You can connect your Google Drive, import past meeting recordings, and Pocket Nori will transcribe them, extract topics and commitments, and let you search across all your meetings.

Key deliverables:
- Google Drive retro-import (pull in past meeting recordings)
- Deepgram transcription pipeline (audio → text → stored, audio deleted)
- AI extraction pipeline (text → topics, commitments, entities, with source citations)
- pgvector search (semantic search across all your meeting content)
- Basic web UI with search

Quality gate: Before moving to Phase 2, we manually evaluate AI extraction quality on 10 real meeting transcripts.

### Phase 2 — Full Product (Weeks 13–20)
What becomes usable: The full Pocket Nori experience — timeline views, pre-meeting briefs, connection detection, dashboard.

Key deliverables:
- Topic Arc timeline (see how topics evolve across meetings over weeks/months)
- Connection detection (AI surfaces links between meetings you may have missed)
- Pre-meeting Brief (auto-generated 12 minutes before a meeting starts, based on all relevant history)
- Commitment tracker (all promises made, by whom, by when)
- Google Calendar sync (Pocket Nori knows what meetings you have coming up)
- Full dashboard

### Phase 3 — Desktop App + Scale (Future)
What becomes usable: A native macOS desktop app that listens to Google Meet in real-time (no upload needed), plus enterprise-grade compliance.

---

---

## ✅ Phase 1 Wave 1 — Google Drive Ingest Pipeline

### What was built

This is the first piece of Phase 1 — the pipeline that connects Pocket Nori to your Google Drive and pulls in your past meeting recordings.

**What it can now do:**
- After you sign in with Google, Pocket Nori stores your Google credentials securely so it can access Drive on your behalf — even when you're not actively using the app
- A new screen (when the UI is built) will show you your last 60 days of Drive video recordings and which ones are already imported
- You select which recordings to import; Pocket Nori queues background jobs for each one
- Each job: connects to Drive → downloads the audio/video to memory → sends it to Deepgram for transcription with speaker labels → stores the transcript in the database as a series of speaking segments → **immediately deletes the audio from memory** — Pocket Nori never stores audio
- You can check the status of each import job at any time

**Safety guardrails built in:**
- If a recording has already been imported, the system detects this and skips it — so running an import twice has no effect
- Audio bytes are deleted from memory inside a `try/finally` block — even if transcription fails, the audio is never retained
- Each Celery job always refreshes the Google access token from the stored refresh token before downloading, so tokens expiring overnight don't break imports
- The database write uses the user's own JWT (not the admin key) so all privacy rules are enforced

**Test coverage:**
- 12 new unit tests added (mocking Drive, Deepgram, and Supabase)
- All 22 unit tests passing (10 original + 12 new)

**New API endpoints (backend-only for now — UI comes in Wave 4):**
- `GET /onboarding/available-recordings` — shows what's available to import
- `POST /onboarding/import` — starts the import jobs
- `GET /onboarding/import/status/{job_id}` — check progress

---

---

## ✅ Phase 1 Wave 2 — AI Extraction Pipeline + Conversations API

### What was built

This is the intelligence layer — the part that turns raw transcripts into searchable knowledge.

**What the system can now do:**
- After a recording is ingested, two background jobs automatically kick off:
  1. **AI Extraction**: Claude reads the transcript and pulls out topics discussed, commitments made (who, what, and by when), and named entities (people, projects, companies, products). All of this is stored in the database with links back to the exact transcript segments they came from.
  2. **Semantic Embedding**: Each transcript segment is converted into a mathematical vector (1536-dimensional, via OpenAI's text-embedding-3-small model) and stored in the database. This powers the semantic search coming in Wave 3 — where you search by meaning, not just keywords.
- The conversations API is now live — you can list all your past meetings and drill into any one of them to see the full AI analysis

**New API endpoints (live now):**
- `GET /conversations` — list all your meetings (title, date, duration, status: processing or indexed)
- `GET /conversations/{id}` — full detail: topics, commitments, entities, and transcript segments
- `GET /conversations/{id}/connections` — returns empty for now; connection detection is Phase 2

**Auth improvements (agreed with frontend):**
- After signing in, the app now sets an HttpOnly cookie (more secure than the previous approach of storing a token in the browser)
- `GET /auth/session` — lets the frontend check if the user is logged in on app load
- `POST /auth/logout` — clears the session
- API testing via `/docs` still works — you can still pass a Bearer token in the header

**Test coverage:**
- 7 new unit tests for the extraction pipeline (input validation, ownership checks, happy path, user isolation)
- All 29 unit tests passing

**New migration:**
- `migrations/004_conversation_status.sql` — adds a `status` column to conversations (`processing` → `indexed`). Run this against Supabase before deploying.

---

---

## ✅ Phase 1 Wave 3 — Semantic Search + Supporting Endpoints

### What was built

This is the search layer — the part that lets you find anything said in any meeting, just by describing what you're looking for.

**What the system can now do:**
- You type a question or phrase — e.g. "shipping deadline discussion" or "budget concerns" — and Pocket Nori finds the most relevant transcript segments across all your meetings, ranked by semantic similarity (meaning, not keywords)
- The search converts your query into a mathematical vector (using the same OpenAI embedding model used for transcript segments) and compares it against every stored segment in the database using pgvector's cosine similarity operator
- All topics, commitments, and index statistics are now accessible via API — the frontend has everything it needs to build the main screens

**New API endpoints (live now):**
- `POST /search` — semantic search across all transcript segments; body: `{q: string, limit?: 1–50}`; returns ranked results with conversation metadata
- `GET /topics` — all topics extracted from your meetings, with source conversation title and date
- `GET /topics/{id}` — single topic with key quotes
- `GET /commitments` — all commitments (filterable by `?filter_status=open|resolved`)
- `PATCH /commitments/{id}` — mark a commitment as resolved or re-open it
- `GET /index/stats` — quick summary: how many conversations, topics, commitments, and entities you have indexed
- `GET /calendar/today` — today's date plus your open commitments (upcoming meetings will be populated in Phase 2 when Google Calendar sync is built)

**How the search works (for non-technical readers):**
- When a meeting is imported, each transcript segment is converted into a list of 1,536 numbers that mathematically represent its meaning. These are stored in the database.
- When you search, your query is also converted into 1,536 numbers.
- The database then finds all segments whose numbers are closest to your query's numbers — these are the most semantically similar results.
- The result: searching for "risks with the supplier" will surface segments where people said "I'm worried about the vendor's timeline" even if the word "risk" never appeared.

**Privacy guarantee maintained:** The raw SQL query that drives search applies your user ID as a filter *before* the similarity scan begins. Even though this query bypasses Supabase's Row Level Security (necessary to use pgvector), explicit `WHERE user_id = ?` clauses appear twice in the query — once on transcript segments, once on conversations via the JOIN condition.

**Test coverage:**
- 9 new unit tests for search (input validation, happy path, error handling, user isolation)
- All **38 unit tests passing**

---

---

## ✅ Backend Security Hardening + Frontend Integration Prep

### What was done

After the frontend engineer (Codex) reviewed the backend, four issues were found and fixed:

| Issue | What it was | Why it mattered |
|---|---|---|
| **Job ownership gap** | When you checked the status of an import job, the backend didn't verify the job actually belonged to you | Someone who guessed a job ID could see another user's import progress |
| **Topics API shape mismatch** | The topics endpoint returned the wrong data shape — the frontend expected a simplified summary list, and the detail view expected a `conversations` array | Frontend would have crashed trying to display the topics screen |
| **Commitments filter param** | The frontend sends `?status=open` but the backend only accepted `?filter_status=open` | Filtering commitments by status would have silently failed |
| **Import status missing file ID** | The job status response didn't include which Drive file each job was processing | Frontend couldn't show which recording was being imported |

### What else was done

- **22 new unit tests** added for commitments and topics endpoints — total now 60 tests passing
- **Render deployment config created** (`render.yaml`) — the file that tells Render.com how to run the backend. Four services defined: one web API and three background workers.
- **Database migration applied** — the `status` column on conversations (processing → indexed) is now live in Supabase

---

---

## ✅ Linear Project Board — Fully Populated (FAR-1 to FAR-326)

All 326 Linear issues have been created across 5 projects. The board is now complete and ready for sprint planning.

| Project | Issues | Coverage |
|---|---|---|
| Phase 0a — Technical Spikes | FAR-1 to ~FAR-104 | All spike tasks + CI isolation tests |
| Phase 0 — Foundation | FAR-35 + sub-tasks | Dashboard + foundation items |
| Phase 1 — Google Drive Retro-import + Intelligence | FAR-105 to ~FAR-275 | All Phase 1 tasks |
| Phase 2 — Intelligence Surface | FAR-276–318 | Commitment Tracker, Shared Brief, Insights, Hard Delete, Data Export |
| Security & Infrastructure | FAR-279, FAR-319–326 | Render.com deployment (8 sub-tasks) |

**Last batch added (this session):**
- FAR-305–313: User Hard Delete (9 tasks under FAR-277)
- FAR-314–318: User Data Export (5 tasks under FAR-278)
- FAR-319–326: Render.com Deployment (8 tasks under FAR-279)

---

*This document is updated automatically after every completed task.*

---

## ✅ 2026-03-12 — Read-path latency reduction deployed

### What changed

- Added short user-scoped read caching to the slowest browse endpoints:
  - `/calendar/today`
  - `/index/stats`
  - `/topics`, `/topics/{id}`, `/topics/{id}/arc`
  - `/entities`
  - `/commitments`
- Reduced dashboard overfetch so the main dashboard no longer makes a second commitments request just to render open items already present in the briefing payload.
- Simplified topic detail loading so the topic page can render primary content first and fetch the arc separately.
- Deployed to production; app responsiveness improved materially, with more optimization deferred.

### Validation

- `pytest -q` → **98 passed, 7 skipped**
- `mypy src/ --ignore-missing-imports` → **pass**
- `ruff check . && ruff format --check .` → **pass**
- `frontend: npm run lint && npm run build` → **pass**

---

## ✅ 2026-03-12 — Visual refresh deployed

### What changed

- Updated the design system from `Private Office` to `Insightful Dashboard`.
- Switched the app shell to a light workspace with a dark navigation rail, stronger card depth, and Inter typography.
- Kept all route structure, data flow, and business behavior unchanged; this was a presentation-only refresh.

### Validation

- `frontend: npm run lint && npm run build` → **pass**

### Next focus

- Topic intelligence cleanup: fewer one-off labels, stronger recurring-topic merging, and cleaner topic arcs for pilot users.

---

## ✅ 2026-03-12 — Durable topic intelligence implemented locally

### What changed

- Added a stored canonical topic layer with `topic_clusters`, plus `cluster_id` on `topics` and `topic_arcs`, so Pocket Nori no longer depends on read-time clustering as the source of truth.
- Tightened topic extraction to prefer stable initiative-level labels and added `is_background`, then filtered background/admin/introductory topics before insert.
- Moved semantic merge to write time only: lexical match first, then bounded LLM merge through `src/llm_client.py`, never on the read path.
- Added `POST /topics/recluster` and a worker task to rebuild stored topic clusters and arcs for already indexed meetings.
- Updated Search, Topics, dashboard topic counts, topic detail, meeting detail topic links, briefs, and commitments to read cluster-backed topic identity instead of raw topic-row grouping.

### Validation

- `pytest -q` → **104 passed, 7 skipped**
- `mypy src/ --ignore-missing-imports` → **pass**
- `ruff check . && ruff format --check .` → **pass**
- `frontend: npm run lint && npm run build` → **pass**

### Next focus

- Deploy migration `007_topic_clusters.sql` and the API/worker changes
- Trigger per-user recluster for existing meetings
- Run production QA on Search, Topics, Dashboard, Commitments, and meeting detail against stored clusters

---

## ✅ 2026-03-13 — Reclustering bounded to lexical-all + semantic-recent

### What changed

- Split recluster into two passes: a full lexical rebuild across all historical topics, followed by a bounded semantic merge pass only for recent singleton leftovers.
- Added semantic-budget limits so historical backfill no longer tries to semantically re-understand the full archive in one worker task.
- Fixed recluster arc rebuilding so the final arc set is rebuilt from the full final cluster registry, even when the semantic recent pass makes no merges.

### Validation

- `pytest -q tests/test_extract.py tests/test_topic_cluster_store.py tests/test_topic_utils.py tests/test_llm_client.py tests/test_topics.py` → **31 passed**
- `mypy src/ --ignore-missing-imports` → **pass**
- `ruff check ... && ruff format --check ...` → **pass**

### Next focus

- Deploy the bounded recluster fix to API + worker
- Re-run `POST /topics/recluster`
- Confirm the worker completes within the 20-minute limit and review live topic pages for reduced false merges

---

## ✅ 2026-03-16 — Wave C frontend: Actions UI refresh

### What changed

- Renamed the touched shell/dashboard surfaces to `Home` and `Actions` where required by the new root brief.
- Added frontend support for `action_type` filtering plus manual action creation in `frontend/src/lib/api.ts`.
- Rebuilt `/commitments` as an `Actions` page with `Commitments` / `Follow-ups` tabs, compact cards, resolve buttons, meeting deep links, and a manual add form.
- Updated the home dashboard widget to split open items into `Commitments` and `Follow-ups`.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Proceed to Wave D (`You` dropdown + move Entities out of primary nav)

---

## ✅ 2026-03-16 — Wave D frontend: profile dropdown + entity management

### What changed

- Added a top-right profile dropdown driven by the signed-in session, with initials, profile summary, `Manage Entities`, placeholder items, and sign-out.
- Removed `Entities` from the main sidebar navigation.
- Rebuilt `/entities` as `Manage Entities` with search, type filtering, sort controls, and browser-local label overrides.
- Kept label editing local-only because the current API exposes read-only grouped entity summaries without stable entity IDs or an update route.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Proceed to Wave E (meeting detail overhaul)

---

## ✅ 2026-03-16 — Wave E frontend: meeting detail overhaul

### What changed

- Rebuilt the meeting detail page around `Topics`, `Actions`, and `Transcript` tabs.
- Cleaned up the header and added count chips plus the existing latest-brief deep link.
- Added a dedicated connections block sourced from `GET /conversations/{id}/connections`.
- Replaced the raw segment list with a grouped conversation-style transcript view.
- Removed the inline entities block and renamed `Commitments` to `Actions`.
- Left per-meeting action splitting unsplit because the current conversation-detail API does not return `action_type`.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Proceed to Wave F (global search bar)

---

## ✅ 2026-03-16 — Wave F frontend: persistent global search bar

### What changed

- Added a shared header search form so search can be launched from anywhere in the app shell.
- Updated `/search` to hydrate from the `q` URL param and auto-run a `Find` search when navigation originates from the global header or a deep link.
- Synced manual `/search` submissions back into the URL so the page input and global header input stay aligned.
- Wrapped the shared app shell in `Suspense` so Next.js prerendering accepts the new search-param-aware shell.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Proceed to Wave G

---

## ✅ 2026-03-16 — Wave E follow-up: meeting detail actions split by type

### What changed

- Added `action_type` to the frontend conversation-detail contract for `GET /conversations/{id}`.
- Split the meeting detail `Actions` tab into `Commitments` and `Follow-ups`.
- Removed the old “waiting for action_type” placeholder copy because the backend field is now live.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Proceed to Wave G or run compact QA across Search, Topics, Dashboard, and Actions

---

## ✅ 2026-03-16 — Wave G frontend: persistent import entry on Meetings

### What changed

- Added a permanent `Import past meetings` entry point above the Meetings list.
- Linked that entry directly to `/onboarding`.
- Styled it as a quiet secondary row so it stays discoverable without reading like an alert banner.
- Kept it visible regardless of meeting count so users can import more history later.

### Validation

- `cd frontend && npm run lint` → **pass**
- `cd frontend && npm run build` → **pass**

### Next focus

- Run compact QA across Search, Topics, Dashboard, Meetings, and Actions, or define the next cleanup wave explicitly

---

## ✅ 2026-03-13 — Topic cluster IDs stabilized across recluster

### What changed

- Added a post-rebuild reconciliation step so recluster reuses old cluster IDs when the rebuilt cluster shares the same underlying topic rows.
- This keeps durable topic links stable across recluster runs instead of deleting every cluster row and replacing it with new IDs.
- The reconciliation is overlap-first and one-to-one, so it only preserves IDs when the lineage is concrete.

### Validation

- `pytest -q tests/test_extract.py tests/test_topic_cluster_store.py tests/test_topic_utils.py tests/test_llm_client.py tests/test_topics.py` → **32 passed**
- `mypy src/ --ignore-missing-imports` → **pass**
- `ruff check ... && ruff format --check ...` → **pass**

### Next focus

- Deploy the stable-identity fix to API + worker
- Re-run `POST /topics/recluster`
- Verify that old topic links still resolve after rebuild and then resume entity normalization

---

## ✅ 2026-03-13 — Entity directory normalization aligned with dashboard stats

### What changed

- Added a shared entity-grouping helper that safely normalizes obvious brand aliases and `company`/`product` variants without adding risky semantic entity merge logic.
- Updated `/entities` to use that shared grouping layer, including conservative short-form person collapsing only when there is a single unambiguous full-name match.
- Updated dashboard `entity_count` to use the same grouped-entity logic as the directory so both surfaces report the same reality.

### Validation

- `pytest -q tests/test_entities.py tests/test_index_stats.py` → **6 passed**
- `pytest -q` → **112 passed, 7 skipped**
- `mypy src/ --ignore-missing-imports` → **pass**
- `ruff check ... && ruff format --check ...` → **pass**

### Next focus

- Deploy the entity-normalization batch
- Verify `/entities` and dashboard counts match on production
- Decide whether already-broken historical topic URLs need a redirect/alias layer
