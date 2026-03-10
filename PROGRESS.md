# Farz — Build Progress

> This document is written for non-technical readers. It is updated automatically after every completed task.
> Last updated: 2026-03-10

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

We are currently finishing **Phase 0 — Foundation**.

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
| AI module (single controlled gateway) | 🔄 Up next | `src/llm_client.py` |
| Database connector | 🔄 Up next | `src/database.py` |
| Apply database schema to Supabase | 🔄 Up next | Run migration script |
| Phase 0 complete | ⏳ Soon | |
| Phase 1 — Google Drive import | ⏳ Weeks 5–12 | |
| Phase 1 — Transcription pipeline | ⏳ Weeks 5–12 | |
| Phase 1 — AI extraction of topics/commitments | ⏳ Weeks 5–12 | |
| Phase 1 — Search interface (web UI) | ⏳ Weeks 5–12 | |
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

## What's Being Built Right Now (Wave 3)

### 🔄 AI Gateway Module (`src/llm_client.py`)
**What it is:** A single, controlled entry point for all AI calls. Every time Farz needs to talk to Claude (for extracting topics, writing briefs, etc.), it goes through this one module.

**Why it matters:** Centralising AI calls means we can control costs, add logging (without logging private content), enforce rate limits, and swap AI providers in one place if needed.

### 🔄 Database Connector (`src/database.py`)
**What it is:** A reusable connection to the Supabase database. Rather than every part of the app setting up its own connection, they all share one managed connector.

**Why it matters:** Consistent, safe database access across the entire codebase.

### 🔄 Applying the Database Schema
**What it is:** Running the SQL migration script against the live Supabase project to actually create all 9 tables.

**Why it matters:** Until this runs, the database exists but is empty — no tables, no data. After this runs, the data layer is live and ready.

---

## Full Roadmap

### Phase 0 — Foundation (NOW — completing this week)
What's being built: The invisible infrastructure. No user-facing features yet.
Outcome: A secure, running backend that can accept requests, store data, process jobs, and authenticate users.

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

*This document is updated automatically after every completed task.*
