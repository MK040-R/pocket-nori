# Farz — Build Progress

> This document is written for non-technical readers. It is updated automatically after every completed task.
> Last updated: 2026-03-10 (Phase 1 Wave 1 complete — Google Drive ingest pipeline built and tested)

---

## What is Farz?

Farz is a personal intelligence layer for working professionals. It connects to your Google Calendar and meeting recordings, listens to what happens in your meetings, and automatically surfaces what matters — the topics discussed, the commitments made, the people mentioned, and how everything connects over time. Before your next meeting, it gives you a personalised briefing based on everything that was discussed in past meetings with the same people or on the same topic. Think of it as a private, AI-powered chief of staff that never forgets anything said in a meeting, and always prepares you for the next one.

---

## How Building Software Works — The Phases Explained

Building a software product from scratch happens in stages, like constructing a building:

| Phase | Analogy | What it means for Farz |
|-------|---------|------------------------|
| **Phase 0a — Proof of Concept** | Testing the materials before building | We tried each piece of technology separately to see if it works at all — can we capture audio? Can AI extract useful information from a transcript? |
| **Phase 0 — Foundation** | Laying pipes, wiring, and concrete | Building the invisible infrastructure the app runs on — the server, the database, the login system, the background processing engine |
| **Phase 1 — First Working Product** | Putting up walls and a roof | The first version users can actually interact with — import past meetings, get AI summaries, search across meetings |
| **Phase 2 — Full Product** | Interior design, finishing, furniture | The complete dashboard — topic timelines, pre-meeting briefs, commitment tracker, cross-meeting connections |

**Phase 0 is complete.** We are now starting **Phase 1 — First Working Product**.

---

## Overall Progress

| Milestone | Status | Notes |
|-----------|--------|-------|
| Phase 0a — Proof of Concept | ✅ Complete | All 5 technology tests passed |
| Infrastructure & credentials set up | ✅ Complete | All services connected |
| Code repository (GitHub) | ✅ Complete | `MK040-R/Farz-personal-intelligence` |
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
| Phase 1 Wave 2 — AI extraction pipeline + pgvector | ⏳ Next | Topics, commitments, entities, embeddings |
| Phase 1 Wave 3 — Semantic search endpoint | ⏳ After Wave 2 | GET /search?q=... |
| Phase 1 Wave 4 — Web UI | ⏳ After Wave 3 | Next.js frontend |
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

| Service | What it does for Farz |
|---------|----------------------|
| **Supabase** | The database where all user data is stored securely |
| **Upstash Redis** | A fast memory store that queues background jobs |
| **Anthropic (Claude AI)** | The AI that reads transcripts and extracts insights |
| **Deepgram** | The service that converts audio into text |
| **Google OAuth** | Lets users sign in with their Google account |

**Why it mattered:** Without these credentials, none of the code can run. This was the final unblocking step before building could start.

---

### ✅ GitHub Repository
**What happened:** The codebase is now stored on GitHub at `MK040-R/Farz-personal-intelligence`. Every change made going forward is tracked, versioned, and recoverable.

**Why it mattered:** This is the single source of truth for all code. It enables collaboration, rollback if something goes wrong, and a CI/CD pipeline in the future.

---

### ✅ Running Web Server (FastAPI Application)
**What happened:** We built the skeleton of the Farz backend — a web server that starts up, checks that all credentials are present, and listens for incoming requests.

What it can currently do:
- Start up and refuse to run if any required credential is missing (fail-fast protection)
- Respond to a health check: `GET /health` → `{"status": "ok"}`
- Show an interactive API documentation page at `/docs`
- Accept requests and route them to the right handler

**Analogy:** This is like the front door and reception desk of a building. Nothing is decorated yet, but the structure is standing and the door opens.

**Why it mattered:** Every feature in Phase 1 and 2 will be delivered as an endpoint on this server. Now we have somewhere to attach them.

---

### ✅ Data Blueprint — 9 Core Data Types
**What happened:** We defined the exact shape of every piece of information Farz stores. Think of this like designing the filing system before you start filing things.

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

**Why it mattered:** This is the most critical non-negotiable in the product. Farz handles private meeting conversations. A breach of user isolation would be catastrophic. Building it in at the foundation means it's never an afterthought.

---

### ✅ Background Job System (Celery + Redis)
**What happened:** We set up the system that processes meetings in the background. When a meeting recording is imported, Farz doesn't make you wait — it queues the work and processes it asynchronously.

**Analogy:** Like dropping a letter in a post box. You don't stand there waiting for it to be delivered. You drop it and go. The postal system handles the rest.

Current jobs defined:
- `process_transcript` — takes a transcript and queues it for AI extraction
- `generate_brief` — takes a conversation and queues a pre-meeting brief for generation

**Why it mattered:** Without this, importing a 1-hour meeting would make the app freeze for minutes. Background processing is what makes the app feel fast and responsive.

---

### ✅ Google Sign-In
**What happened:** We built the login flow. Users will be able to click "Sign in with Google", grant Farz permission to read their calendar, and be authenticated in the app.

Two endpoints built:
- `GET /auth/login` — redirects to Google's consent screen
- `GET /auth/callback` — receives the user back from Google, exchanges the code for a session, and logs them in

**Why it mattered:** Google login is the front door for users. It also gives Farz permission to read the user's Google Calendar (needed for pre-meeting briefs) and eventually Google Meet recordings.

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
**What it is:** A single, controlled entry point for all AI calls. Every time Farz needs to talk to Claude (for extracting topics, writing briefs, etc.), it goes through this one module — nowhere else.

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

### Phase 1 — First Working Product (IN PROGRESS ✅ Wave 1 complete)

### Phase 1 — First Working Product (Weeks 5–12)
What becomes usable: You can connect your Google Drive, import past meeting recordings, and Farz will transcribe them, extract topics and commitments, and let you search across all your meetings.

Key deliverables:
- Google Drive retro-import (pull in past meeting recordings)
- Deepgram transcription pipeline (audio → text → stored, audio deleted)
- AI extraction pipeline (text → topics, commitments, entities, with source citations)
- pgvector search (semantic search across all your meeting content)
- Basic web UI with search

Quality gate: Before moving to Phase 2, we manually evaluate AI extraction quality on 10 real meeting transcripts.

### Phase 2 — Full Product (Weeks 13–20)
What becomes usable: The full Farz experience — timeline views, pre-meeting briefs, connection detection, dashboard.

Key deliverables:
- Topic Arc timeline (see how topics evolve across meetings over weeks/months)
- Connection detection (AI surfaces links between meetings you may have missed)
- Pre-meeting Brief (auto-generated 12 minutes before a meeting starts, based on all relevant history)
- Commitment tracker (all promises made, by whom, by when)
- Google Calendar sync (Farz knows what meetings you have coming up)
- Full dashboard

### Phase 3 — Desktop App + Scale (Future)
What becomes usable: A native macOS desktop app that listens to Google Meet in real-time (no upload needed), plus enterprise-grade compliance.

---

---

## ✅ Phase 1 Wave 1 — Google Drive Ingest Pipeline

### What was built

This is the first piece of Phase 1 — the pipeline that connects Farz to your Google Drive and pulls in your past meeting recordings.

**What it can now do:**
- After you sign in with Google, Farz stores your Google credentials securely so it can access Drive on your behalf — even when you're not actively using the app
- A new screen (when the UI is built) will show you your last 60 days of Drive video recordings and which ones are already imported
- You select which recordings to import; Farz queues background jobs for each one
- Each job: connects to Drive → downloads the audio/video to memory → sends it to Deepgram for transcription with speaker labels → stores the transcript in the database as a series of speaking segments → **immediately deletes the audio from memory** — Farz never stores audio
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

*This document is updated automatically after every completed task.*
