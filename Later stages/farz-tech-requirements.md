# Farz — Technical Requirements Document

**Version:** 1.0
**Date:** March 2026
**Role:** CTO-level architecture, pre-build stage
**Audience:** Non-technical founder + incoming full-time engineer

---

## Objective

**Build a personal intelligence layer that turns your meeting conversations into a searchable, connected memory system — starting with internal testing, designed to hand off to a full-time engineer.**

Farz captures what you discuss in meetings, extracts who said what, what was decided, and what was committed to, and surfaces all of it through search, topic timelines, and pre-meeting briefings. Think of it as a second brain for your professional life — one that remembers every decision, every commitment, and every conversation you've had, and connects them across time.

**What this document does:**
- Translates the Farz PRD into concrete technology choices
- Explains *why* each technology was chosen, not just what
- Lays out a realistic build sequence: validate the hard things early, build complexity incrementally
- Is designed to be handed directly to an engineer on day one

**What success looks like at the end of internal testing:**
1. You upload a recording or transcript from a real meeting
2. Farz extracts topics, decisions, and commitments from it automatically
3. You can ask "What did we decide about X?" and get an accurate answer across all your past meetings
4. You get a pre-meeting brief 5 minutes before your next call showing relevant context

---

## Non-Negotiable Constraints (from PRD)

These two constraints override every other technical decision. They are not preferences — they are requirements baked into the product's identity:

1. **Per-user index isolation** — no shared state between users; no cross-user data access at any layer (database, cache, search, LLM calls). Even if the application code has a bug, the database itself must refuse to serve User A's data to User B.

2. **Zero LLM data retention (ZDR)** — all LLM API calls must use providers with signed zero-data-retention agreements. Your meeting conversations never get logged to, stored by, or used for training by a third party. This is enforced in code at startup — not just in policy.

---

## How Competitors Were Analyzed

Before making any recommendations, the following products were researched for their tech stacks, architectures, and engineering decisions:

| Competitor | Key Finding |
|------------|-------------|
| **Granola** | Native desktop app (not a bot), captures system audio at OS level, uses Deepgram for transcription, OpenAI + Claude for LLM, no audio stored |
| **Otter.ai** | Python backend, proprietary ASR model, AWS infrastructure, faces GDPR lawsuits due to US-only data storage |
| **Fireflies.ai** | Node.js, GraphQL API, bot-based (bot joins meeting as participant), hybrid Google Cloud + AWS |
| **Notion** | PostgreSQL + Kafka + pgvector + S3 data lake, OpenAI + Anthropic, permission-aware AI at enterprise scale |
| **Mem0** | 3-tier memory storage: vector DB + graph DB + key-value — the most sophisticated memory architecture in the space |

**Key pattern:** The best products (Granola, Notion) made clear, principled choices early — no bots, no audio storage, strong privacy. The ones with the most complaints (Otter) cut corners on those same principles and are now fighting the consequences.

---

## 1. Language & Framework Choices

### Backend: Python 3.13 + FastAPI

**Why Python:** Python is the language of AI. Every LLM library, every embedding library, every ML tool is built for Python first. Building an AI-heavy product in any other language means fighting the ecosystem. The alternative (Node.js) has weaker AI tooling and would require more custom code for the extraction pipeline. Python is also what's already installed in this repo's `.venv` — no reason to change it.

**Why FastAPI:** FastAPI is the best Python web framework for this type of product. It handles async operations natively (critical for streaming LLM responses and processing multiple transcripts simultaneously), generates API documentation automatically, and has tight integration with Pydantic for data validation.

- Already installed: FastAPI, Pydantic v2, uvicorn, anyio
- Pydantic v2 models the 8 PRD entities (Conversation, Topic, TopicArc, Connection, Commitment, Entity, Brief, Index) with strict validation — every object entering or leaving the system is type-checked

### Frontend: Next.js 15 + TypeScript + Tailwind CSS

**Why Next.js:** React is the dominant frontend framework and Next.js is its production-ready version. Pages load fast (server-side rendering), API routes let the frontend talk to the backend securely, and it's the most hireable skill in frontend engineering today. When you bring on an engineer, there's a near-100% chance they know Next.js.

**Why TypeScript:** TypeScript catches bugs before they happen. For a product where data models matter (8 interconnected entities from the PRD), type-checking prevents a whole class of errors. Both the frontend and the Electron desktop app use TypeScript — one language across the full non-Python stack.

**Why Tailwind:** Tailwind lets you build UIs quickly without designing a custom design system. For internal testing, speed matters more than aesthetics.

### Desktop App: Electron + TypeScript *(Phase 3 — built after the intelligence layer is validated)*

**Why a desktop app, not a bot:** A bot joins your meeting as a visible participant — everyone sees "Fireflies Notetaker has joined." That creates friction, requires Google Workspace admin approval in many organizations, and feels invasive. A native desktop app captures audio silently at the OS level — no bot, no announcement, works on Zoom, Google Meet, Teams, and Slack simultaneously.

**Why not a Chrome extension:** A Chrome extension only captures browser tab audio. It cannot capture audio from the Zoom desktop app, Teams desktop app, or Slack Huddles. It's too limited for a product that needs to work everywhere.

**Why Electron over Swift or Tauri:** Swift would be Mac-only, which is too limiting. Tauri (Rust-based) is powerful but harder to hire for. Electron uses TypeScript — the same language as the frontend — and is how Slack, VS Code, Notion, and Figma are built. Any experienced frontend engineer knows Electron.

**Why this is Phase 3:** The Electron app is the most technically complex component. Building it first means spending weeks on audio capture before validating that the intelligence extraction is good. The smarter path: prove the AI works with manual uploads first, then automate the capture.

- Captures system audio at the OS level (Core Audio on Mac, WASAPI on Windows)
- No browser required, no bot, no "recorder joined" announcements
- Works across all platforms: Zoom, Google Meet, Teams, Slack Huddles

### Mobile: Skip entirely for now
Desktop-first; mobile adds platform complexity with no unique value at this stage. Phase 4+ only.

---

## 2. Database Strategy

### Primary: PostgreSQL 16 via Supabase

**Why PostgreSQL:** PostgreSQL is the gold standard for relational databases. It has been battle-tested for 30 years, supports the vector search extension (pgvector) Farz needs, and has Row-Level Security (RLS) — a feature that enforces per-user data isolation at the database engine level. This means even if the application code has a bug, the database itself will refuse to return User A's data to User B. That is the safest, most robust way to enforce the non-negotiable isolation constraint.

**Why Supabase:** Supabase is managed PostgreSQL that also provides authentication, file storage, and real-time subscriptions — all in one service. For a solo founder testing internally, this eliminates the need to run your own database server, manage backups, or set up a separate auth system. The free tier handles the volumes involved in internal testing.

- All structured data: Users, Conversations, Topics, Commitments, Entities, Connections, Briefs
- Every table has a `user_id` column
- RLS policy: `USING (user_id = auth.uid())` — enforced at the DB engine level, not just the API

### Vector Search: pgvector (PostgreSQL extension)

**Why pgvector, not Pinecone or Weaviate:** Purpose-built vector databases are powerful, but they're also one more service to manage, one more bill to pay, and one more integration to build. pgvector is a PostgreSQL extension that adds semantic search directly into the existing database. For internal testing and early scale (up to ~10 million vectors), pgvector performs well and keeps the architecture simple. When scale requires it, migrating to Pinecone is a well-documented path that any engineer can execute.

- Stores embeddings for semantic search directly in Postgres
- Filtered by `user_id` before any similarity search — isolation enforced even at the vector layer
- Upgrade path: Pinecone or Weaviate when needed

### Cache: Redis via Upstash (serverless)

**Why Redis:** The pre-meeting brief must load instantly — within seconds of opening a calendar event. Redis stores pre-computed results in memory so they don't need to be regenerated on demand. Upstash is serverless Redis: pay per request, free tier for testing, no server to run.

- Key namespace enforces isolation: `user:{user_id}:brief:{meeting_id}` — no shared keys between users

### Graph Database: Skip for Phase 1, add in Phase 2 if needed

The Topic Arc feature (tracking how a topic evolved across meetings) can be implemented with standard PostgreSQL join tables in Phase 1. The data volume does not justify a graph database yet. If traversal logic becomes complex, Neo4j AuraDB (fully managed, no infrastructure) is the upgrade path.

### Object Storage: Supabase Storage (S3-compatible)

**Why no audio storage:** Audio files are the most sensitive data category. Storing them creates liability, increases storage costs, and violates the spirit of the product's privacy principles. Granola made the same choice and it's a competitive differentiator. Farz stores transcripts only.

- Transcript path: `/users/{user_id}/conversations/{conversation_id}/transcript.txt`
- Path structure enforces per-user isolation at the storage layer

---

## 3. Meeting Capture: Google Meet / Calendar Integration

**Chosen approach: Native Desktop App (system audio capture, no bot)**

This is Granola's architecture. Granola is a native Mac/Windows app — it captures audio at the OS level (Core Audio on Mac, WASAPI on Windows), not from a browser tab. This means it works across every meeting platform simultaneously without any browser dependency.

**Why this wins over the alternatives:**

| Approach | Verdict | Reason |
|----------|---------|--------|
| Bot (Fireflies, Otter model) | Rejected | Visible to all participants. Requires Workspace admin approval. Creates friction. |
| Chrome extension | Rejected | Only captures browser tab audio. Misses Zoom desktop, Teams desktop, Slack. |
| Native desktop app (Granola model) | Chosen | Silent, universal, works on every platform, no admin approval needed. |

**How the Electron app works:**
1. Runs in the background as a menu bar app
2. Detects meeting start via Google Calendar API
3. Activates system audio capture at the OS level
4. Streams raw PCM audio to the FastAPI backend via WebSocket
5. Backend pipes audio to Deepgram in real-time
6. Transcript chunks stored in Postgres as they arrive
7. On meeting end: Celery job triggered for LLM extraction

**Key engineering risk:** Requires OS-level microphone permissions and Mac code signing (notarization) for distribution. Budget one week of engineer time for the Apple Developer account setup and signing pipeline. Validate audio capture works before building anything on top of it.

---

## 4. Transcription Pipeline

### Primary: Deepgram Nova-3

**Why Deepgram:** Transcription is the foundation of everything — if the transcript is bad, every downstream feature (topic extraction, commitment detection, search) is bad. Deepgram Nova-3 is what Granola uses. It has the best combination of: accuracy (~99% on English), real-time latency (<300ms streaming), and speaker diarization (it knows who said what, which maps directly to the PRD's Entity model).

**Cost:** ~$0.0043/minute. A one-hour meeting costs $0.26. Negligible for internal testing.

- **Phase 1** (manual upload): Deepgram async file transcription API
- **Phase 3** (Electron app): Deepgram real-time streaming WebSocket
- `diarize: true` → speaker labels → maps to PRD Entity (Person) automatically
- Backup: AssemblyAI (drop-in alternative, same API pattern)

### Post-Meeting Processing: Async via Celery

**Why async:** Extracting topics, commitments, and entities with an LLM takes 5–30 seconds depending on meeting length. Making the user wait blocks the experience. The transcript is stored immediately; a background job queue processes it asynchronously. The user sees results appear within a minute of the meeting ending.

**Technology:** Celery (the standard Python async job queue) + Redis as the task broker

**Jobs triggered post-meeting:**
1. Entity extraction (persons, projects, products)
2. Topic detection and clustering
3. Commitment identification (action items, decisions, promises)
4. Embedding generation → stored in pgvector
5. Pre-meeting brief pre-computation for the next relevant calendar event

### Data Flow — Phase 1 (Manual Upload):
```
User uploads audio or transcript file
  → FastAPI receives file
    → Deepgram async API transcribes audio (if audio)
      → Transcript stored in Postgres
        → Celery job triggered: LLM extraction
          → Topics, Commitments, Entities written to DB
            → Embeddings generated → stored in pgvector
```

### Data Flow — Phase 3 (Electron App, Real-Time):
```
Electron captures system audio → WebSocket → FastAPI
  → Deepgram real-time streaming (chunks every ~200ms)
    → Transcript chunks stored in Postgres incrementally
      → On meeting end: Celery LLM extraction job triggered
```

---

## 5. LLM Integration

### Primary Provider: Anthropic Claude

**Why Anthropic Claude:** Three reasons.

1. **Quality:** Claude is the best model at following complex, nuanced instructions. Extracting structured data (commitments, topics, entities) from messy, colloquial meeting transcripts requires nuance — Claude handles this better than any other model at comparable price.

2. **Privacy compliance:** Anthropic does not train on API data by default. This directly satisfies the zero-data-retention requirement without requiring a special enterprise agreement for Phase 1 testing.

3. **Structured output:** Claude's ability to return data that exactly matches a defined schema is among the best available. Combined with the `instructor` library, every extraction returns a validated Pydantic object — not a blob of text to parse.

**Why not OpenAI GPT-4o first:** GPT-4o is excellent and kept as a backup. However, OpenAI's default data handling requires additional enterprise agreements for full zero-data-retention guarantees. Anthropic's API-level guarantees are cleaner for a privacy-first product. GPT-4o is used if Claude API is degraded.

**Model selection:**
- `claude-sonnet-4-6` — extraction tasks (topics, commitments, entities): fast, cheap, accurate
- `claude-opus-4-6` — Brief generation: highest reasoning quality, used sparingly (once per meeting)

### Zero Data Retention: Enforced in Code

**Why enforce in code, not policy:** A policy memo can be forgotten or ignored. A boot-time check in code cannot. The FastAPI server refuses to start if ZDR configuration is missing.

```python
# src/config.py — runs at startup, not at first use
def validate_llm_config():
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set — server cannot start")
    # All LLM calls route through llm_client.py — no direct SDK calls elsewhere
```

### Structured Output via `instructor` + Pydantic

**Why structured output:** The naive approach is asking Claude to "extract commitments" and getting back a paragraph of text. The right approach is defining an exact data schema and having Claude fill it in. This produces typed, validated objects with zero parsing code.

```python
class CommitmentExtraction(BaseModel):
    assignee: str
    action: str
    deadline: str | None
    confidence_score: float  # 0.0–1.0

class TopicList(BaseModel):
    topics: list[str]
    sentiment: str  # "positive" | "neutral" | "negative"
    importance_score: float

class EntityList(BaseModel):
    persons: list[str]
    projects: list[str]
    products: list[str]
```

---

## 6. Authentication

### Google OAuth 2.0 via Supabase Auth

**Why Google OAuth:** The PRD specifies Google Workspace accounts for Phase 1. Google OAuth also grants access to the Google Calendar API — which Farz needs to read upcoming meetings, link recordings to calendar events, and auto-detect meeting start times. Building a custom auth system would be unnecessary complexity when Google OAuth provides everything needed and users already trust the Google sign-in flow.

**Why Supabase Auth:** Supabase Auth handles the full OAuth flow, stores and refreshes tokens securely, and generates a `user_id` (`auth.uid()`) that plugs directly into PostgreSQL's Row-Level Security policies. Every table's isolation rule references this same ID. One auth system → isolation enforced at every layer automatically.

- Phase 1 OAuth scopes: `calendar.readonly`, `profile`, `email`
- Phase 4 addition: `gmail.readonly` (email thread context)
- Google Calendar API uses the stored OAuth token to pull upcoming meetings

---

## 7. Per-User Isolation — Enforced at Every Layer

The isolation requirement is enforced simultaneously at six independent layers. Breaking it requires failing all six simultaneously — not just bypassing the API.

| Layer | Isolation Mechanism |
|-------|---------------------|
| **Postgres** | Row-Level Security: `USING (user_id = auth.uid())` — enforced by the DB engine, not application code |
| **Object Storage** | Path prefix: `/users/{user_id}/...` — paths outside this prefix are inaccessible |
| **Redis cache** | Key namespace: `user:{user_id}:...` — no cross-user key collisions possible |
| **Vector search** | pgvector query: `WHERE user_id = $1` applied before ANN search — embeddings never cross user boundaries |
| **LLM calls** | Transcript text is always scoped to a single user's conversation — never batched across users |
| **Celery jobs** | Job payload includes `user_id`; worker validates ownership before processing |
| **API layer** | JWT middleware extracts `user_id` from token; injected into every DB query via FastAPI dependency injection |

---

## 8. Infrastructure

### Phase 1 — Internal Testing (Weeks 1–16): Simple and cheap

**Philosophy:** AWS is the right long-term choice, but setting it up correctly (IAM roles, VPCs, security groups, load balancers, container orchestration) takes weeks of engineering time. For solo internal testing, that complexity provides zero benefit. Use managed services that handle infrastructure for you; migrate when scale justifies it.

| Service | Provider | Cost |
|---------|----------|------|
| Backend API + Celery workers | Render.com | ~$25/month |
| Database + Auth + Storage | Supabase | Free tier |
| Redis | Upstash | Free tier |
| Transcription | Deepgram API | Pay-per-minute (~$0.26/hr) |
| LLM | Anthropic API | Pay-per-token (~$0.50–2.00/hr meeting) |
| **Total** | | **~$30–60/month** |

### Phase 2 — Engineer Hired, First External Users: Production-grade

**Why switch to AWS:** When real users are involved, you need control over data residency, automated backups, multi-region failover, and compliance certifications (SOC 2, GDPR). AWS is where every mature SaaS product eventually lives.

- **Backend:** AWS ECS Fargate (containerized FastAPI + Celery — no server management)
- **Database:** AWS RDS PostgreSQL (Multi-AZ, point-in-time recovery)
- **Cache:** AWS ElastiCache
- **Storage:** AWS S3 (per-user bucket policies)
- **CDN:** CloudFront for the Next.js frontend
- **CI/CD:** GitHub Actions → Docker build → ECS deploy
- **Monitoring:** Sentry (errors) + Datadog (performance)

### Phase 3 — Scale:
- Vector DB: Pinecone or Weaviate (when pgvector hits performance limits at high user counts)
- Graph DB: Neo4j AuraDB (when Topic Arc traversal grows complex)
- Event streaming: Apache Kafka (following Notion's pattern: CDC → Kafka → data lake → AI features at scale)

---

## 9. Search & Indexing

### Semantic Search: pgvector

Every Conversation, Topic, and Commitment is embedded and stored in pgvector. Search works by embedding the user's query and finding the closest matches by cosine similarity — filtered by `user_id` first.

- Embedding model: `text-embedding-3-small` (OpenAI) or `voyage-3` (Anthropic) — both available, benchmark on real data
- Hybrid approach: combine vector similarity with full-text BM25 ranking for best results
- No Elasticsearch needed in Phase 1

### Full-Text Search: PostgreSQL `tsvector`

Standard Postgres full-text search for exact keyword queries. Combined with pgvector similarity for hybrid ranking — the same pattern used by Notion's search.

### Topic Clustering (async, post-meeting):

After each meeting, a Celery job:
1. Extracts candidate topics from the new transcript via LLM
2. Embeds each topic
3. Finds similar topic embeddings in the user's existing topic index
4. Merges duplicates, creates new Topic entities, updates Topic Arc timelines

This is what creates the "how did this topic evolve over time" view in the dashboard.

---

## 10. Phase Roadmap

### Phase 0 — Foundation (Weeks 1–3)
*Goal: Get infrastructure running. No features yet.*

- [ ] Project structure: `src/api/`, `src/workers/`, `src/models/`, `tests/`, `migrations/`
- [ ] `pyproject.toml` + `requirements.txt` with pinned versions
- [ ] Supabase project: full schema + RLS policies for all 8 entities
- [ ] FastAPI skeleton: auth middleware, health check endpoint, OpenAPI docs
- [ ] Google OAuth flow working end-to-end (login → calendar access)
- [ ] `.env.example` with all required environment variables documented

### Phase 1 — Manual Upload + Intelligence (Weeks 4–10)
*Goal: Prove the AI extraction works on real meetings before solving automated capture.*

- [ ] File upload endpoint: accept `.txt` transcript or `.mp3/.wav/.m4a` audio
- [ ] Deepgram async transcription for uploaded audio files
- [ ] LLM extraction pipeline: Topics, Commitments, Entities via `instructor` + Pydantic
- [ ] pgvector embeddings for all conversations and extracted entities
- [ ] Basic web UI: upload a file, see extracted topics and commitments
- [ ] Semantic search: type a question, get relevant conversation snippets back

**Validation gate (end of Phase 1):** Run 10 real meeting transcripts through the system. Target: >80% of actual commitments caught, topics coherent and de-duplicated. If this bar is not met, fix before moving forward. Do not build Phase 2 on a weak extraction foundation.

### Phase 2 — Intelligence Surface (Weeks 11–16)
*Goal: Make the intelligence visible and useful.*

- [ ] Topic Arc: timeline showing how a topic evolved across meetings
- [ ] Connection detection: surface conversations that share entities or topics
- [ ] Pre-meeting Brief generation (auto-triggered 5 minutes before a calendar event)
- [ ] Dashboard: "What was discussed about X?" timeline view
- [ ] Commitment tracker: open action items with assignee and deadline
- [ ] Google Calendar sync: auto-link uploaded meetings to calendar events by time window

### Phase 3 — Automated Capture (Weeks 17–26)
*Goal: Remove the manual upload friction. Build the Electron app.*

- [ ] Electron desktop app: system audio capture (Core Audio / WASAPI) → WebSocket stream
- [ ] Swap Deepgram async for real-time streaming WebSocket
- [ ] Auto-detect meeting start via Google Calendar polling
- [ ] Mac code signing and notarization (Apple Developer account, ~1 week setup)
- [ ] Auto-update mechanism (Electron's built-in updater)
- [ ] Windows build pipeline

### Phase 4 — Expand (Post-engineer hire)

- [ ] Gmail integration: pull email threads into the context graph
- [ ] Slack integration: index Slack messages as Conversations
- [ ] Bot-based capture: optional alternative for users who prefer it or are on non-Mac devices
- [ ] Mobile app (React Native): view briefs and search on the go

---

## 11. Key Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM extraction quality too low on noisy, colloquial meetings | **High** | Validate on 10 real transcripts at end of Phase 1 before building anything on top. Fix prompts and models before proceeding. |
| Engineer handoff — undocumented decisions cause rework | **High** | This document + inline code comments + ADR (Architecture Decision Records) folder in repo from day one |
| Electron app code signing and notarization on Mac | **Medium** | Required for any distribution. Budget 1 week. Requires Apple Developer account ($99/year). Do this in first sprint of Phase 3. |
| OS audio capture API changes with macOS / Windows updates | **Medium** | Pin Electron version. Test on both OS after major OS updates. Electron abstracts most platform differences. |
| Deepgram diarization degrades with >4 simultaneous speakers | **Medium** | Flag meetings with >10 speakers. Assess accuracy manually. Consider speaker count as a product constraint. |
| Postgres performance with pgvector at scale | **Medium** | Pre-planned upgrade path to Pinecone. Partition `user_id` index. Monitor query time as user count grows. |
| Anthropic ZDR agreement for enterprise launch | **Medium** | Default API is already no-training. Formal enterprise ZDR agreement needed before marketing to enterprises in Phase 2. Start this conversation early. |
| Google OAuth scope approval (Gmail) | **Low** | Only request `calendar.readonly` in Phase 1. Gmail scope requires Google's OAuth verification — start that process 6–8 weeks before Phase 4 launch. |

---

## 12. Final Tech Stack Summary

| Category | Technology | Rationale |
|----------|-----------|-----------|
| Backend language | Python 3.13 | Best AI/ML ecosystem; already installed |
| API framework | FastAPI + Pydantic v2 | Async, typed, auto-docs; already installed |
| Frontend | Next.js 15 + TypeScript + Tailwind | Industry standard, most hireable |
| Desktop app | Electron + TypeScript | System audio capture, no bot, cross-platform Mac + Windows |
| Database | Supabase (PostgreSQL 16 + pgvector) | RLS for isolation + vector search in one managed service |
| Cache | Upstash Redis (serverless) | Pre-meeting brief cache; zero ops |
| Auth | Supabase Auth + Google OAuth 2.0 | Ties directly into RLS; handles Calendar API token |
| Transcription | Deepgram Nova-3 | Used by Granola; best real-time accuracy + diarization |
| LLM (primary) | Anthropic claude-sonnet-4-6 | ZDR by default; best structured extraction |
| LLM (briefs) | Anthropic claude-opus-4-6 | Highest reasoning quality; used once per meeting |
| LLM wrapper | `instructor` library + Pydantic models | Typed extraction; no raw JSON parsing |
| Async jobs | Celery + Redis | Post-meeting extraction and embedding pipeline |
| Object storage | Supabase Storage (S3-compatible) | Transcripts only; per-user path isolation |
| Phase 1 hosting | Render.com + Supabase | No DevOps; ~$30–60/month |
| Phase 2 hosting | AWS ECS Fargate + RDS PostgreSQL | Production-grade; engineer-familiar |
| Phase 3 additions | Pinecone, Neo4j AuraDB, Kafka | Activated by scale; not needed until then |

---

## 13. The Four Things to Prove Before Writing Application Code

An engineer's first two weeks should validate these four assumptions. If any one fails, the architecture changes before a single line of product code is written.

1. **Supabase RLS isolation works** — create two test users, verify User A's token cannot fetch User B's rows in any table. Write this as an automated test that runs in CI forever.

2. **Deepgram produces usable transcripts** — run 3 real meeting recordings through the API. Check accuracy and speaker diarization quality. If accuracy is poor on your specific meeting types, evaluate AssemblyAI.

3. **LLM extraction meets the quality bar** — run 5 transcripts through the commitment/topic/entity extraction pipeline. Manually verify: are the commitments real? Are the topics coherent? Is anything hallucinated?

4. **Electron can capture system audio** — build a minimal Electron prototype that captures system audio from an active meeting and writes it to a file. This is the highest-risk technical assumption in the entire product.

If all four pass, the architecture is validated. Everything else is execution.
