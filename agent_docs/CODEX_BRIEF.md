# Pocket Nori — Codex Brief: Parallel Work Division

> Status update (2026-03-11): This document is now **historical reference only**.
> Active execution tracking has moved to:
> - `.planning/ROADMAP.md`
> - `.planning/STATE.md`
> - `.planning/PROJECT.md`
> - `PROGRESS.md`
>
> Current ownership model is Codex end-to-end (backend + frontend), so the old
> Claude/Codex split described below is no longer active.

---

## What is Pocket Nori?

Pocket Nori is a personal intelligence layer for working professionals. It connects to Google Drive, pulls in past meeting recordings, transcribes them, and extracts topics, commitments, and named entities using AI. Users can then search across all their meetings.

---

## Current state (as of Phase 1 Wave 1)

The Python backend is partially built. What exists today:

| What | Status |
|------|--------|
| FastAPI server (`src/main.py`) | ✅ Running |
| Google OAuth login (`/auth/login`, `/auth/callback`) | ✅ Built |
| Google Drive listing + import (`/onboarding/...`) | ✅ Built |
| Celery background job: download + transcribe + store | ✅ Built |
| Database: 17 tables in Supabase (all with privacy enforcement) | ✅ Live |
| AI extraction (Topics, Commitments, Entities) | 🔨 Claude Code building now |
| Semantic search (pgvector) | 🔨 Claude Code building next |
| Next.js frontend | ⬜ Codex's job |

---

## Hard boundaries — READ BEFORE WRITING A SINGLE LINE

```
Codex owns:      frontend/           (create this directory, work only here)
Claude Code owns: src/               (Python backend)
                  tests/             (Python tests)
                  migrations/        (SQL migrations)
                  requirements.txt   (Python deps)
```

**Codex must NOT touch:**
- Anything in `src/`
- Anything in `tests/`
- Anything in `migrations/`
- `requirements.txt`
- Any `.py` file anywhere

**Claude Code must NOT touch:**
- Anything in `frontend/`

Both agents may update `docs/working-notes/PROGRESS.md` — but only to record their own completed waves.

---

## API Contract

The seam between the two tracks. Neither agent changes this without the founder signalling the other.

### OpenAPI spec

The backend auto-publishes a machine-readable contract:
- Interactive docs: `http://localhost:8000/docs`
- JSON spec: `http://localhost:8000/openapi.json`

When in doubt, the live `/openapi.json` is the source of truth.

---

## Auth — HttpOnly cookie session

The backend sets an HttpOnly cookie on login. Codex does **not** manage JWTs in localStorage.

### Login flow

```
1. Frontend redirects user to:  GET /auth/login
2. User approves Google OAuth
3. Backend redirects to:        GET /auth/callback?code=...
4. Backend exchanges code → Supabase JWT
5. Backend sets HttpOnly cookie: Set-Cookie: session=<jwt>; HttpOnly; SameSite=Lax; Path=/
6. Backend redirects frontend to: /onboarding  (or /meetings if already onboarded)
```

### Session management endpoints

```
GET  /auth/session
     → 200 { user_id, email }   (if cookie is valid)
     → 401                      (if no session / expired)

POST /auth/logout
     body: {}
     → 200 { ok: true }
     Clears the session cookie server-side.
```

Codex should call `GET /auth/session` on app load to determine if the user is logged in. No JWT handling in frontend code — all auth is cookie-based. The backend `get_current_user` dependency accepts both cookie and `Authorization: Bearer` header (for local API testing via `/docs`).

---

## Codex's job: Phase 1 Wave 4 — Next.js Frontend

**Branch:** `feat/phase-1-wave-4-frontend`

**Root directory:** `frontend/` (create this at repo root)

**Stack:** Next.js 15 + TypeScript + Tailwind CSS

### Design system

Read `.interface-design/system.md` before writing any UI. Key tokens:

| Token | Value |
|-------|-------|
| Background | `#0A1510` (near-black forest green) |
| Primary text | `#F0EDE4` (warm cream) |
| Accent (gold) | `#C9A84C` — the only accent colour |
| Heading font | Plus Jakarta Sans |
| Data/code font | JetBrains Mono |
| Depth | Borders only — no box shadows |

### Screens to build (in this order)

#### 1. Onboarding screen — connects to real backend NOW

Path: `/onboarding`

What it does: Shows the user's Google Drive recordings from the last 60 days. User selects which to import. Progress updates in real time.

**Real endpoints (already live, use these):**

```
GET  /onboarding/available-recordings
     → [{ file_id, name, created_time, size_bytes, mime_type, already_imported }]

POST /onboarding/import
     body: { file_ids: ["abc123", "def456"] }
     → 202 { jobs: [{ file_id, job_id }] }

GET  /onboarding/import/status/{job_id}
     → { job_id, status: "pending"|"progress"|"success"|"failure", detail, result }

GET  /onboarding/import/status
     → { total, pending, processing, succeeded, failed,
         jobs: [{ job_id, file_id, status, detail }] }
     (user-level aggregate — poll this to show overall progress)
```

Poll the per-job status endpoint every 3 seconds until `status === "success"` or `"failure"`. Use the aggregate endpoint to show a progress summary banner.

#### 2. Meetings list — mock data first, swap to real later

Path: `/meetings`

**Mock data shape:**
```typescript
// GET /conversations  (Claude Code builds this — use mock until it's ready)
type ConversationSummary = {
  id: string
  title: string
  source: "google_drive"
  meeting_date: string   // ISO-8601
  duration_seconds: number | null
  status: "indexed" | "processing"
}
```

Show: title, date, duration, a status badge (indexed = green dot, processing = spinner).

#### 3. Meeting detail — mock data first, swap to real later

Path: `/meetings/[id]`

**Mock data shape:**
```typescript
// GET /conversations/{id}  (Claude Code builds this — use mock until it's ready)
type ConversationDetail = {
  conversation: {
    id: string
    title: string
    meeting_date: string
    duration_seconds: number | null
  }
  topics: Array<{
    id: string
    label: string
    summary: string
    status: "open" | "resolved"
    key_quotes: string[]
  }>
  commitments: Array<{
    id: string
    text: string
    owner: string
    due_date: string | null
    status: "open" | "resolved"
  }>
  entities: Array<{
    id: string
    name: string
    type: "person" | "project" | "company" | "product"
    mentions: number
  }>
  segments: Array<{
    id: string
    speaker_id: string
    start_ms: number
    end_ms: number
    text: string
  }>
  connections: []   // always empty in Phase 1 — Phase 2 feature
}
```

Show: topics list, commitments list, entities list. Transcript segments are secondary (collapsible). Connections section: render the section heading but show an empty state ("No connections yet") — the shape is agreed, data arrives in Phase 2.

#### 4. Search — mock data first, swap to real later

Path: `/search`

**Mock data shape:**
```typescript
// POST /search  (Claude Code builds this — use mock until it's ready)
// Request body: { q: string, limit?: number }
type SearchResult = {
  segment_id: string
  text: string
  conversation_id: string
  conversation_title: string
  meeting_date: string
  score: number   // 0.0–1.0
}
```

Show: a search input. On submit (`POST /search` with body `{ q: query, limit: 10 }`), display results as cards with the matched text, meeting name, and date.

**Note:** Search uses `POST`, not `GET`, because the query body is structured and may grow.

#### 5. Today's briefing — mock data first, swap to real later

Path: `/today`

**Mock data shape:**
```typescript
// GET /calendar/today  (Claude Code builds this — use mock until it's ready)
type TodayBriefing = {
  date: string
  upcoming_meetings: Array<{
    id: string
    title: string
    start_time: string
    attendees: string[]
  }>
  open_commitments: Array<{
    id: string
    text: string
    owner: string
    due_date: string | null
    conversation_title: string
  }>
}
```

---

### Additional endpoints (use once Claude Code ships them)

```
GET  /index/stats
     → { conversation_count, topic_count, commitment_count, entity_count,
         last_updated_at }
     Use on a dashboard header or sidebar to show the user's index health.

GET  /topics
     → [{ id, label, conversation_count, latest_date }]
     Global topics list across all meetings.

GET  /topics/{id}
     → { id, label, summary, conversations: [...], key_quotes: [...] }

GET  /commitments
     → [{ id, text, owner, due_date, status, conversation_id, conversation_title }]
     All commitments across all meetings (filterable by status).

PATCH /commitments/{id}
     body: { status: "resolved" }
     → 200 { id, status: "resolved" }
     Mark a commitment as done — build this interaction into the UI.

GET  /conversations/{id}/connections
     → { connections: [] }   ← always empty in Phase 1; shape is agreed for Phase 2
```

---

### API client

All fetch calls must go through a single typed client at `frontend/src/lib/api.ts`. Never call `fetch` directly from a component. This makes swapping mock → real a one-line change.

```typescript
// frontend/src/lib/api.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// No JWT parameters — auth is handled via HttpOnly cookie automatically
// All fetch calls use credentials: "include" so the browser sends the cookie

export async function getSession(): Promise<{ user_id: string; email: string } | null>
export async function logout(): Promise<void>

// Onboarding (real endpoints)
export async function getAvailableRecordings(): Promise<RecordingItem[]>
export async function startImport(fileIds: string[]): Promise<ImportJobList>
export async function getImportStatus(jobId: string): Promise<ImportJobStatus>
export async function getAllImportStatus(): Promise<ImportStatusAggregate>

// Meetings (mock until Claude Code ships)
export async function getConversations(): Promise<ConversationSummary[]>
export async function getConversation(id: string): Promise<ConversationDetail>

// Search (mock until Claude Code ships) — POST, not GET
export async function search(q: string, limit?: number): Promise<SearchResult[]>

// Index stats (mock until Claude Code ships)
export async function getIndexStats(): Promise<IndexStats>

// Topics (mock until Claude Code ships)
export async function getTopics(): Promise<TopicSummary[]>
export async function getTopic(id: string): Promise<TopicDetail>

// Commitments (mock until Claude Code ships)
export async function getCommitments(): Promise<Commitment[]>
export async function resolveCommitment(id: string): Promise<Commitment>

// Today's briefing (mock until Claude Code ships)
export async function getTodayBriefing(): Promise<TodayBriefing>
```

All `fetch` calls must include `credentials: "include"` so the browser sends the session cookie:
```typescript
const res = await fetch(`${BASE_URL}/some/endpoint`, {
  credentials: "include",
  // ...
})
```

### Environment setup

```bash
cd frontend
npm install
npm run dev      # starts on http://localhost:3000
```

Create:
```
frontend/.env.local.example
  NEXT_PUBLIC_API_URL=http://localhost:8000
```

Read `pocket-nori-ui-spec.md` in the repo root for the full screen spec and navigation structure.

---

## What Claude Code is building in parallel

Claude Code is working on:

1. **`src/workers/extract.py`** — Celery task that reads transcript segments from DB, calls Claude AI to extract topics/commitments/entities, and stores the results.

2. **`src/workers/embed.py`** — Celery task that generates pgvector embeddings for each transcript segment.

3. **`src/api/routes/conversations.py`** — endpoints:
   - `GET /conversations` — list of conversations
   - `GET /conversations/{id}` — full detail (topics, commitments, entities, segments)
   - `GET /conversations/{id}/connections` — returns `{ connections: [] }` stub in Phase 1

4. **`src/api/routes/search.py`** — `POST /search` with body `{ q, limit }` — pgvector semantic search

5. **`src/api/routes/topics.py`** — `GET /topics`, `GET /topics/{id}`

6. **`src/api/routes/commitments.py`** — `GET /commitments`, `PATCH /commitments/{id}`

7. **`src/api/routes/index.py`** — `GET /index/stats`

8. **`src/api/routes/calendar.py`** — `GET /calendar/today`

9. **Auth updates** — `GET /auth/session`, `POST /auth/logout`, HttpOnly cookie set on callback

When these are ready, Codex connects the frontend by updating `frontend/src/lib/api.ts` to call the real endpoints instead of returning mock data.

---

## PR and review process

- Each agent opens a PR when a wave is complete
- The founder shares the PR diff with the other agent for review
- Neither agent merges without the founder's approval
- Integration PR (connecting frontend to real backend) is the final step — both agents review it

---

## How to run the backend locally (for Codex's reference)

```bash
# From repo root (not frontend/)
source .venv/bin/activate
uvicorn src.main:app --reload

# Server runs on http://localhost:8000
# Interactive API docs: http://localhost:8000/docs
# OpenAPI JSON spec:    http://localhost:8000/openapi.json
```

The `.env` file at repo root has all credentials. Do not commit it.

---

*Delete this file once Phase 1 integration is complete.*
