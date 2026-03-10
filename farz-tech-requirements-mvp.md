# Farz — Technical Requirements (MVP Edition)

**Version:** 1.1
**Date:** March 2026
**Updated:** After senior engineer review v1 + v2
**Scope:** Phase 0a through Phase 2 — internal testing, solo founder + first engineer hire
**Audience:** You (founder) + engineer building with Claude Code
**Cost target:** ~$50/month

> This document covers what to build now. For the full architectural vision including Phase 3+ (Electron app, AWS, formal compliance, Intelligence Evaluation Contract), see `farz-tech-requirements-full.md`.

---

## Objective

**Build a personal intelligence layer that turns your meeting conversations into a searchable, connected memory system — starting with internal testing, designed to hand off to a full-time engineer.**

Farz captures what you discuss in meetings, extracts who said what, what was decided, and what was committed to, and surfaces all of it through search, topic timelines, and pre-meeting briefings.

**What success looks like at the end of internal testing (Phase 2):**
1. You upload a recording or transcript from a real meeting
2. Farz extracts topics, decisions, and commitments from it automatically — with citations back to who said what
3. You can ask "What did we decide about X?" and get an accurate answer across all your past meetings
4. You get a pre-meeting brief 10–15 minutes before your next call showing relevant context

---

## Non-Negotiable Constraints

These constraints are from PRD Section 3 and override every other technical decision. They are requirements, not preferences — and they must be enforced in code, not just in policy.

**1. Per-user index isolation.**
No shared state between users. No cross-user data access at any layer: database, cache, search index, or LLM calls. The database engine itself enforces this via Row-Level Security — not just the API layer.

**2. No model training on user data.**
Anthropic's standard API does not use submitted data for model training (confirmed per API terms). This is a no-training policy — sufficient for Phase 1 internal testing with no external users. Before onboarding any external user, a formal Data Processing Agreement (DPA) must be in place with every inference and embedding provider. The same no-training policy applies to embedding providers: Anthropic's and OpenAI's embedding APIs both confirm no training on API data.

**3. Hard-delete only. No soft-delete. Ever.**
The user owns all data. Deletion is immediate and irreversible. There is no `deleted_at` column, no grace period, no archival. When data is deleted, it cascades across: Postgres rows, pgvector embeddings, Redis cache keys, and Supabase Storage paths. If this isn't decided before the first migration, it becomes a painful refactor later.

**4. No admin visibility into user intelligence.**
No one other than the user can read their conversations, topics, commitments, or briefs — not you, not a future employee, not a contractor. No admin panel is built that surfaces individual user conversation content. This is an architectural constraint, not a policy toggle.

**5. Encryption at rest and in transit.**
AES-256 at rest and TLS 1.2+ in transit. Supabase provides both by default. No additional action required — but confirmed and stated here so it isn't questioned later.

**6. Compliance certifications.**
Not relevant for MVP internal testing. Compliance (SOC 2, GDPR, UAE ADGM) is a Phase 3+ concern — addressed in the full architecture document.

---

## How Competitors Were Analyzed

Before making any recommendations, the following products were researched:

| Competitor | Key Finding |
|------------|-------------|
| **Granola** | Native desktop app (not a bot), captures system audio at OS level, Deepgram for transcription, OpenAI+Claude for LLM, no audio stored |
| **Otter.ai** | Python backend, proprietary ASR, AWS infrastructure; faces GDPR issues due to US-only data storage |
| **Fireflies.ai** | Node.js, GraphQL API, bot-based; hybrid Google Cloud + AWS |
| **Notion** | PostgreSQL + Kafka + pgvector + S3 data lake; OpenAI + Anthropic; permission-aware AI |
| **Mem0** | 3-tier memory storage: vector DB + graph DB + key-value |

**Key pattern:** Granola and Notion made principled choices early (no bots, no audio storage, strong privacy). Otter cut corners on those principles and is now fighting GDPR consequences.

---

## 1. Language & Framework Choices

### Backend: Python 3.13 + FastAPI
**Why Python:** Python is the language of AI. Every LLM library, embedding library, and ML tool is built for Python first. Building an AI-heavy product in any other language means fighting the ecosystem.

**Why FastAPI:** Handles async operations natively (critical for streaming LLM responses), generates API documentation automatically, has tight integration with Pydantic v2 for data validation. Already installed in `.venv` — no reason to change it.

- Already installed: FastAPI, Pydantic v2, uvicorn, anyio
- Pydantic v2 models all PRD entities with strict validation

### Frontend: Next.js 15 + TypeScript + Tailwind CSS
**Why Next.js:** React's production-ready framework. Fast page loads, API routes, most hireable frontend skill. Any engineer you hire knows it.

**Why TypeScript:** Type-checking prevents whole classes of errors with the 9-entity data model. Shared language between frontend and Electron app.

**Why Tailwind:** Build UI fast without a custom design system. Speed matters more than polish at MVP stage.

### Desktop App: Electron + TypeScript — Phase 3 only
The Electron app (system audio capture, no bot) is the Phase 3 goal — after the intelligence layer is validated. Not in scope for MVP. See the full architecture document for details.

### Mobile: Skip entirely.

---

## 2. Database Strategy

### Primary: PostgreSQL 16 via Supabase
**Why PostgreSQL:** The gold standard relational database. Has Row-Level Security (RLS) — a feature that enforces per-user data isolation at the database engine level, not just the API layer. Even if the application code has a bug, the database refuses to serve User A's data to User B.

**Why Supabase:** Managed PostgreSQL with authentication, file storage, and real-time subscriptions in one service. Free tier handles MVP volumes. Eliminates the need to run a database server for internal testing.

- Every user-owned table has a `user_id` column
- RLS policy: `USING (user_id = auth.uid())` — enforced at DB engine level
- All user-owned tables use `ALTER TABLE ... FORCE ROW LEVEL SECURITY` (not just ENABLE — FORCE applies the policy even to the table owner)
- **No soft-delete on any table.** `deleted_at` columns are not permitted.

### Vector Search: pgvector (PostgreSQL extension)
**Why pgvector not Pinecone:** Pinecone is powerful but is one more service to manage and bill to pay. pgvector is a PostgreSQL extension — vector search lives in the same database. Handles up to ~10M vectors before performance degrades. Sufficient for MVP.

- Filtered by `user_id` before any similarity search
- Upgrade path to Pinecone when p95 query latency exceeds 200ms (defined in full doc)

### Cache: Upstash Redis (serverless)
Pre-meeting briefs must load instantly. Redis stores pre-computed results in memory. Upstash is serverless — free tier for testing.

- Key namespace: `user:{user_id}:brief:{meeting_id}` — no cross-user key collisions
- **Note:** Upstash free tier uses REST API, not native RESP protocol. Validate Celery broker compatibility in Phase 0a Spike 5. Fallback: Render Redis (~$7/month) as dedicated broker.

### Graph Database: Skip for MVP
Topic Arc traversal can be implemented with Postgres join tables for MVP. Evaluate Neo4j AuraDB if traversal logic outgrows Postgres in Phase 3.

### Object Storage: Supabase Storage (S3-compatible)
Transcript storage path: `/users/{user_id}/conversations/{conversation_id}/transcript.txt`

**No audio files stored** — audio is transient (see Section 4 for lifecycle).

---

## 3. Meeting Capture

**MVP approach: Google retro-import (Phase 1) → Automated Electron desktop app (Phase 3)**

**Phase 1 — Google retro-import:** On first login, Farz uses the Google Drive API to enumerate past Google Meet recordings stored in the user's Drive (configurable lookback window, default 60 days) and bulk-ingests them. No file upload UI is built. No manual upload endpoint. Google Meet recordings are automatically saved to the meeting organizer's Drive — this is the source Farz reads from. Audio is fetched transiently, transcribed via Deepgram, then discarded; it is never stored in Supabase Storage.

**Why retro-import over manual upload:** Manual upload requires user effort per meeting and doesn't deliver the "instant history" experience that makes the product valuable on day one. Retro-import gives the user weeks of indexed meetings immediately after the first OAuth consent.

**Why not Google Meet native transcription:** Google Meet's native captions lack speaker diarization, have lower accuracy on technical and business vocabulary, and provide no API for programmatic retrieval. Deepgram is the transcription engine for all phases.

**Phase 3 — Electron desktop app:** Native Mac/Windows app that captures system audio at the OS level (Core Audio / WASAPI). No bot. No "recorder joined" announcement. Works across Zoom, Google Meet, Teams, Slack Huddles simultaneously.

**Why not a bot (Fireflies/Otter model):** Bot joins as a visible participant — everyone sees it. Requires Google Workspace admin approval in many organizations. Farz's identity is privacy-first — no bots.

---

## 4. Transcription Pipeline

### Primary: Deepgram Nova-3
**Why Deepgram:** Used by Granola. Best combination of accuracy (~99% English), real-time latency (<300ms streaming), and speaker diarization. Speaker labels map directly to the PRD's Entity (Person) model.

**Cost:** ~$0.0043/minute. One hour of meetings costs $0.26. Negligible for internal testing.

- **Phase 1** (manual upload): Deepgram async file transcription API
- **Phase 3** (Electron app): Deepgram real-time streaming WebSocket
- `diarize: true` → speaker labels → stored as `speaker_id` in `TranscriptSegment`
- Backup: AssemblyAI (drop-in alternative, same API pattern)

### Audio Lifecycle (Phase 1 — retro-import)
Audio from Google Drive is **transient**. It is fetched in memory and never stored. The full lifecycle:

1. Drive API returns a download URL for a Meet recording
2. Audio streamed directly to Deepgram — never written to Supabase Storage
3. **On success:** transcript persisted to Postgres → audio stream discarded immediately
4. **On failure:** import job retried via Celery; no audio artifact is retained between attempts
5. The only artifact retained is the text transcript

For Phase 3 (Electron): audio is a memory-only PCM buffer — never written to disk at any point.

### Post-Meeting Processing: Celery + Redis
Extracting topics, commitments, and entities with an LLM takes 5–30 seconds. Processing happens asynchronously so the user doesn't wait.

- Celery job queue + Redis broker
- Jobs triggered after transcript is stored: entity extraction → topic clustering → commitment detection → embedding generation → brief pre-computation
- Workers scale independently of the API server

**Phase 1 data flow:**
```
User logs in → Google OAuth → Drive API enumerates past Meet recordings
  → /onboarding/available-recordings returns count
    → User triggers /onboarding/import
      → Celery job per recording: Drive API streams audio → Deepgram transcribes
        → Transcript chunked into TranscriptSegments → stored in Postgres
          → Audio stream discarded (never stored)
            → Celery job: LLM extraction
              → Topics, Commitments, Entities written to DB (with segment citations)
                → Embeddings generated → stored in pgvector
```

---

## 5. LLM Integration

### Primary Provider: Anthropic Claude
**Why Claude:** Best at following complex, nuanced instructions — which matters for extracting structured data from colloquial meeting transcripts. No training on API data by default. Best structured output capabilities.

**Important clarification on "ZDR":** Anthropic's standard API does not use data for model training (no-training policy). This is **not** the same as a formal Zero Data Retention agreement. A formal ZDR/DPA requires a signed enterprise agreement. For Phase 1 internal testing with no external users, the standard API is acceptable. Before any external user onboards, a formal DPA is required with all inference and embedding providers.

- `claude-sonnet-4-6` — all extraction tasks (topics, commitments, entities): fast and cost-effective
- `claude-opus-4-6` — Brief generation only: best reasoning quality; use sparingly
- **Monthly spend alert: set a $100/month alert on the Anthropic API dashboard before starting.** API costs can surprise you during active testing.

### ZDR applies to embeddings too
The same no-training policy applies to embedding providers. Both Anthropic's and OpenAI's embedding APIs confirm no training on API data by default.

### Enforcement in code
The server must not start if provider configuration is missing:
```python
# src/config.py — runs at startup
def validate_llm_config():
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot start")
```

All LLM calls route through a single `llm_client.py` module. No direct SDK calls scattered around the codebase. Transcript content must never appear in application logs.

### Structured Output via `instructor` + Pydantic
Every extraction returns a validated Pydantic object — no raw JSON parsing, no hallucinated keys.

```python
class CommitmentExtraction(BaseModel):
    text: str                    # The extracted commitment statement
    assignee: str                # Who made the commitment
    deadline: str | None         # Deadline if mentioned
    confidence_score: float      # 0.0–1.0
    segment_ids: list[str]       # Links to source TranscriptSegments

class TopicList(BaseModel):
    topics: list[str]
    sentiment: str               # "positive" | "neutral" | "negative"
    importance_score: float
    segment_ids: list[str]       # Links to source TranscriptSegments
```

---

## 6. Authentication

### Google OAuth 2.0 via Supabase Auth
**Why Google OAuth:** PRD specifies Google Workspace accounts. Google OAuth also grants Calendar API access — needed to read upcoming meetings and link recordings to calendar events. No custom auth system needed.

**Why Supabase Auth:** Handles the full OAuth flow, stores and refreshes tokens, and generates `auth.uid()` which plugs directly into all RLS policies. One auth system → isolation enforced at every layer automatically.

- Phase 1 scopes: `calendar.readonly`, `drive.readonly`, `profile`, `email`
  - `calendar.readonly` — read upcoming meetings and link imports to calendar events
  - `drive.readonly` — enumerate and stream past Google Meet recordings stored in Drive. Meet recordings are saved automatically to the organizer's Drive; there is no dedicated Meet Recordings API.
- Phase 4 addition: `gmail.readonly` (when Gmail integration is built)

---

## 7. Per-User Isolation — Enforced at Every Layer

Isolation is enforced simultaneously at six independent layers. A bug in one layer does not compromise isolation — all six must fail simultaneously for a breach.

### Database Role Matrix

| Role | Key | Allowed operations |
|------|-----|--------------------|
| `anon` | Supabase anon key | No access to user tables |
| `authenticated` | Supabase user JWT | Read/write own rows only (RLS enforced) |
| `service_role` | Supabase service key | DDL and migrations only — **never for data reads** |
| Celery workers | User JWT passed in job payload | Read/write own rows, `WHERE user_id = $1` filter on every query |

**Critical:** The `service_role` key bypasses RLS entirely. If workers use it by accident, the entire isolation model is broken. Workers MUST receive the user's JWT as part of the job payload and use it for all database operations.

### All Isolation Layers

| Layer | Mechanism |
|-------|-----------|
| Postgres | RLS with `FORCE ROW LEVEL SECURITY` on all user-owned tables |
| Object Storage | Path prefix: `/users/{user_id}/...` — inaccessible outside this prefix |
| Redis cache | Key namespace: `user:{user_id}:...` — no cross-user keys |
| Vector search | pgvector query: `WHERE user_id = $1` applied before ANN similarity search |
| LLM calls | Transcript text always single-user scoped — never batched across users |
| Celery jobs | Job payload includes `user_id`; worker validates ownership before any read/write |
| API layer | JWT middleware extracts `user_id`; injected into every DB query |

**CI requirement:** Isolation tests run on every PR. Test: User A's JWT cannot read User B's rows in any user-owned table.

---

## 8. Infrastructure (MVP — Phase 1 Only)

**Philosophy:** AWS is the right long-term choice, but it takes weeks to configure correctly. For internal testing with one user, that complexity provides zero benefit. Start with managed services; migrate when scale justifies it.

| Service | Provider | Cost |
|---------|----------|------|
| Backend API + Celery workers | Render.com | ~$25/month |
| Database + Auth + Storage | Supabase | Free tier |
| Redis (cache) | Upstash | Free tier |
| Redis (Celery broker, if Upstash fails spike) | Render Redis | ~$7/month |
| Transcription | Deepgram API | ~$0.26/hr of audio |
| LLM | Anthropic API | ~$0.50–2.00/hr meeting |
| **Total** | | **~$30–60/month** |

Phase 2+ infrastructure (AWS ECS, RDS, ElastiCache, CloudFront) is in the full architecture document.

---

## 9. Search & Indexing

### Semantic Search: pgvector
- Embeddings generated by `text-embedding-3-small` (OpenAI) or Anthropic's embedding API
- Every Conversation, TranscriptSegment, Topic, and Commitment gets an embedding
- Search: embed the query → cosine similarity search in pgvector, filtered by `user_id` first
- Returns results with citation fields (conversation_id, start_ts, end_ts, speaker_id, snippet)

### Full-Text Search: PostgreSQL full-text search (`tsvector` / `ts_rank_cd`)
Combined with vector similarity for hybrid ranking. No Elasticsearch needed for MVP.

Note: PostgreSQL's full-text search uses `ts_rank_cd` scoring — similar in spirit to BM25 but not identical. The hybrid formula combines normalized vector score and normalized lexical score.

### Topic Clustering (async, post-meeting)
After each meeting, a Celery job:
1. Extracts candidate topics from the new transcript via LLM
2. Embeds each topic
3. Finds similar topic embeddings in the user's existing index
4. Merges clear duplicates, creates new Topic entities, updates Topic Arc timelines

---

## 10. Data Model

The 9 core entities (8 from PRD + 1 new from engineering review).

### Entities

**Conversation**
The atomic unit of capture. Source platform, list of participants, start timestamp, duration.

**TranscriptSegment** *(new — required for traceability)*
A single speaker utterance. The atomic unit of a transcript. Every derived entity links back to one or more TranscriptSegments — enabling citations ("Murali said this at 14:23 in the March 5 standup").

Fields: `conversation_id`, `speaker_id`, `start_ts` (seconds), `end_ts`, `text`, `segment_confidence`

**Why this is required from Phase 0:** Without utterance-level storage, you cannot attribute commitments accurately, cannot provide citations in briefs, and cannot defend against hallucination ("show me where in the transcript this came from"). Adding this later requires a schema migration. Build it now.

**Topic**
A subject that recurs across Conversations, identified by Farz. Has: label, first_mentioned, last_mentioned, status (open/resolved), linked Conversations. Links to source TranscriptSegments.

**Topic Arc**
A timeline view over a Topic's linked Conversations — a synthesized narrative of how the topic evolved. Every claim traceable to a TranscriptSegment.

**Connection**
A detected relationship between two or more Conversations or Topics. Created when Farz identifies overlap in subject matter, entities, or commitments across separate meetings. Links to source TranscriptSegments.

**Commitment**
A statement in which the user indicates a future action. Fields: extracted text, assignee, due date (if mentioned), source Conversation, source TranscriptSegments, status (open/resolved).

**Entity**
A named person, project, company, or product referenced across Conversations. Internal enrichment layer — not directly user-facing.

**Brief**
A generated pre-meeting artifact composed from relevant Topic Arcs, open Commitments, flagged Connections, and calendar context. Private by default. User can share explicitly.

**Index**
The user's personal conversation store. Architecturally isolated per user. Contains all of the above for a given user.

### Entity Relationships
```
Index (per user)
├── Conversations [1..N]
│   └── contains → TranscriptSegments [1..N]
│       ├── extracted → Commitments [0..N]
│       └── references → Entities [0..N]
├── Topics [0..N]
│   └── linked to → Conversations + TranscriptSegments [1..N]
├── Topic Arcs [0..N] (view over Topics × Conversations, ordered by time)
└── Connections [0..N]
    └── links → Conversations or Topics [2..N]

Brief
└── composed from → Topic Arcs + Commitments + Connections + Calendar event
```

---

## Phase 0a — Technical Spikes (Week 1)

**Goal:** Validate high-risk assumptions before writing a single line of product code. These are feasibility checks — not features. If any spike fails, the architecture changes before Phase 0 begins.

- [ ] **Spike 1: Electron audio capture** — Can the Electron app capture system audio from an active Google Meet session and write it to a local file? (Mac Core Audio API, Chromium tab capture). *If this fails, evaluate alternative capture mechanisms before proceeding.*
- [ ] **Spike 2: Deepgram accuracy** — Run 3 real meeting recordings through Deepgram. Is transcription accuracy and speaker diarization acceptable for your meeting types?
- [ ] **Spike 3: LLM extraction quality** — Run 5 real transcripts through Claude extraction (topics, commitments, entities). Do the results make sense? Are commitments real? Are topics coherent?
- [ ] **Spike 4: Supabase RLS isolation** — Create 2 test users. Verify User A's JWT cannot read User B's rows in any user-owned table. Write as an automated test that runs in CI.
- [ ] **Spike 5: Celery broker via Upstash** — Test Celery task dispatch, retry on failure, and visibility timeout against Upstash Redis. If free tier doesn't support native RESP protocol reliably, switch to Render Redis (~$7/month) as the dedicated broker and use Upstash only for caching.

---

## Phase 0 — Foundation (Weeks 2–4)

*Goal: Infrastructure running. No product features yet.*

- [ ] Project structure: `src/api/`, `src/workers/`, `src/models/`, `tests/`, `migrations/`
- [ ] `pyproject.toml` + `requirements.txt` with pinned versions
- [ ] `.env.example` with all required environment variables documented
- [ ] Supabase project: full schema for all 9 entities + RLS policies (FORCE RLS on all user tables)
- [ ] Confirm: no `deleted_at` column on any table — hard delete only
- [ ] FastAPI skeleton: auth middleware, health check, OpenAPI docs at `/docs`
- [ ] Google OAuth flow working end-to-end (login → calendar access)
- [ ] Monthly spend alert set on Anthropic API ($100 threshold)

---

## Phase 1 — Google Retro-Import + Intelligence (Weeks 5–12)

*Goal: Prove the intelligence layer works on real meetings. Ingestion via Google Drive retro-import.*

- [ ] Google Drive API integration: enumerate past Meet recordings within configurable lookback window (default 60 days)
- [ ] `/onboarding/available-recordings` endpoint — returns count of importable recordings
- [ ] `/onboarding/import` endpoint — triggers bulk import as Celery jobs
- [ ] `/onboarding/import/status` endpoint — returns live progress (count indexed, total)
- [ ] Celery job: stream recording from Drive → Deepgram transcription → audio discarded (never stored)
- [ ] TranscriptSegment storage: every utterance stored with speaker_id, start_ts, end_ts
- [ ] LLM extraction pipeline: Topics, Commitments, Entities via `instructor` + Pydantic (with segment_id citations)
- [ ] pgvector embeddings for conversations, segments, topics, commitments
- [ ] Basic web UI: onboarding screen with import progress → meeting list → view extracted topics and commitments → click to see source quote
- [ ] Semantic search: type a question → get relevant segments back with citations

**Quality gate (end of Phase 1):**
Before moving to Phase 2, manually evaluate the system on 10 real meeting transcripts across all 3 Phase 1 output types:
- Topics: are they coherent? Are duplicates merged correctly across meetings?
- Commitments: are the ones extracted real? Are any missed? Are segment citations accurate?
- Search: does semantic search return relevant results with correct source citations?

If quality is poor on any dimension, fix it before building Phase 2 features on top. Do not proceed with a weak intelligence foundation.

*Note: Connections and Briefs are Phase 2 features — they are not built in Phase 1 and are not part of this quality gate.*

---

## Phase 2 — Intelligence Surface (Weeks 13–20)

*Goal: Make the intelligence visible and useful across meetings.*

- [ ] Topic Arc: timeline showing how a topic evolved across meetings, with per-claim citations
- [ ] Connection detection: surface meetings that share entities or topics with confidence scores
- [ ] Pre-meeting Brief generation — triggered 10–15 minutes before a calendar event (default T-12m)
  - If generation misses the trigger window, deliver immediately with a "late" label
- [ ] Dashboard: "What was discussed about X?" timeline view
- [ ] Commitment tracker: open action items with assignee and deadline
- [ ] Google Calendar sync: auto-link uploaded meetings to calendar events by time window

---

## Key Risks (MVP Scope)

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM extraction quality too low on noisy meetings | **High** | Validate on 10 real transcripts at Phase 1 end before building Phase 2 |
| service_role key used in workers, bypassing RLS | **High** | Phase 0 CI test; code review rule: no service_role in application code |
| Celery broker unreliable on Upstash free tier | **Medium** | Phase 0a Spike 5; fallback to Render Redis before Phase 1 buildout |
| Supabase free tier limits hit during testing | **Low** | Monitor storage + row counts; upgrade to Pro tier ($25/month) if needed |
| Anthropic API spend surprise | **Low** | $100/month alert set in Phase 0 |

---

## Tech Stack Summary

| Category | Choice | Rationale |
|----------|--------|-----------|
| Backend | Python 3.13 + FastAPI + Pydantic v2 | AI ecosystem, already installed, async |
| Frontend | Next.js 15 + TypeScript + Tailwind | Industry standard, hireable |
| Database | Supabase PostgreSQL 16 + pgvector | RLS for isolation + vector search in one |
| Auth | Supabase Auth + Google OAuth 2.0 | Ties into RLS; Calendar API access |
| Cache | Upstash Redis (serverless) | Pre-meeting brief cache; namespaced per user |
| Transcription | Deepgram Nova-3 | Best accuracy + diarization; used by Granola; streams from Drive, no storage |
| LLM (extraction) | claude-sonnet-4-6 | Fast, cost-effective, structured output |
| LLM (briefs) | claude-opus-4-6 | Best reasoning; used sparingly |
| LLM wrapper | `instructor` + Pydantic | Typed extraction, no raw JSON parsing |
| Async jobs | Celery + Redis | Post-meeting extraction pipeline |
| Object storage | Supabase Storage | Transcripts only; per-user path isolation |
| Hosting | Render.com | One-click deploy, no DevOps, ~$25/month |

---

## The Five Things to Prove Before Writing Product Code

Run these in Week 1. If any fails, fix the architecture before Phase 0.

1. **Supabase RLS blocks cross-user reads** — automated CI test, User A cannot read User B's data
2. **Deepgram transcribes your meetings accurately** — run 3 real recordings, check speaker diarization
3. **LLM extraction works on your real transcripts** — 5 transcripts, evaluate topic/commitment/entity quality
4. **Celery dispatches jobs reliably via Redis** — test retry, visibility timeout, worker restart
5. **Audio is never stored** — verify no audio artifact is written to Supabase Storage during a Drive retro-import; only the transcript reaches Postgres
