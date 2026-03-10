# Farz — Technical Requirements (Complete Architecture)

**Version:** 1.1
**Date:** March 2026
**Updated:** After senior engineer review v1 + v2
**Scope:** Full vision — MVP through scale, all phases, all contracts
**Audience:** Full-time senior engineer; scaling to real users

> For the lean, Claude Code-ready MVP version covering Phase 0–2 only, see `farz-tech-requirements-mvp.md`.

---

## Objective

**Build a personal intelligence layer that turns your meeting conversations into a searchable, connected memory system.**

Farz captures what you discuss in meetings, extracts who said what, what was decided, and what was committed to, and surfaces all of it through semantic search, topic timelines, and pre-meeting briefings. The product is personal, private, and traceable — every generated claim links back to a source meeting and speaker.

**What success looks like at production scale:**
1. User joins a meeting — Farz captures audio silently via desktop app, no bot
2. Within 60 seconds of meeting end: topics, commitments, and entities extracted and indexed
3. "What did we decide about the Q2 launch?" returns a synthesized narrative with citations across all past meetings
4. 10–15 minutes before every meeting: a tailored brief surfaces context the user needs
5. User can export or hard-delete all their data at any time — immediate and irreversible

---

## Non-Negotiable Constraints

All six PRD Section 3 privacy principles are encoded as technical requirements:

**1. Per-user index isolation.**
No shared state between users. Enforced simultaneously at: DB engine (RLS), object storage (path prefix), cache (key namespace), vector search (predicate filter), LLM calls (no cross-user batching), job queue (user-scoped execution).

**2. Zero data retention / no model training.**
All inference and embedding providers must have signed Data Processing Agreements (DPAs) with zero-data-retention terms before handling any external user data. For internal testing only, a standard API with a no-training policy is acceptable. Every provider is tracked in a config allowlist (see LLM Provider Policy section).

**3. Hard-delete only. No soft-delete.**
User-initiated deletion is immediate and irreversible. Cascades across: Postgres rows, pgvector embeddings, Redis cache entries, Supabase Storage objects, and all derived artifacts. No `deleted_at` columns. No grace periods. Users can export all data before deletion.

**4. No admin visibility into user intelligence.**
No employee, contractor, or admin can view user conversations, topics, commitments, or briefs. This is enforced architecturally via DB role controls — not policy. No admin panel is built that surfaces individual user conversation content.

**5. Encryption and infrastructure standards.**
AES-256 at rest, TLS 1.2+ in transit. Infrastructure on SOC 2-compliant providers. Least-privilege access controls with audit logging on export and delete operations.

**6. Compliance roadmap.**
SOC 2 Type II certification by Phase 3. GDPR readiness before any EU user onboarding. UAE ADGM/DIFC framework compliance before UAE enterprise sales. Sequencing table in the Security & Compliance section.

---

## How Competitors Were Analyzed

| Competitor | Key Finding |
|------------|-------------|
| **Granola** | Native desktop app (no bot), OS-level audio capture, Deepgram, OpenAI+Claude, no audio stored, AWS |
| **Otter.ai** | Python backend, proprietary ASR model, AWS; GDPR violations due to US-only data storage |
| **Fireflies.ai** | Node.js, GraphQL, bot-based, hybrid Google Cloud + AWS |
| **Notion** | PostgreSQL + Kafka + pgvector + S3 data lake; OpenAI + Anthropic; permission-aware AI at enterprise scale |
| **Mem0** | 3-tier memory: vector DB + graph DB + key-value — most sophisticated memory architecture in the space |

**Key pattern:** The products that earned user trust (Granola, Notion) made principled choices early — no bots, no audio storage, strong privacy enforcement. Otter cut corners and now faces GDPR consequences.

---

## 1. Language & Framework Choices

### Backend: Python 3.13 + FastAPI
Python is the language of AI. Every LLM, embedding, and ML library is Python-first. FastAPI provides native async, auto-generated OpenAPI docs, and first-class Pydantic v2 integration. Already installed in `.venv`.

### Frontend: Next.js 15 + TypeScript + Tailwind CSS
React's production-ready framework. SSR for fast loads, API routes for BFF pattern, most hireable frontend stack. TypeScript shared across frontend and Electron app.

### Desktop App: Electron + TypeScript (Phase 3)
Native Mac/Windows app. Captures system audio at the OS level (Core Audio on Mac, WASAPI on Windows). No bot. No announcement. Works across Zoom, Google Meet, Teams, Slack Huddles simultaneously.

**Why Electron over alternatives:**
- Swift: Mac-only, limits cross-platform reach
- Tauri (Rust): powerful but harder to hire for
- Electron: TypeScript (same as frontend), how Slack/VS Code/Notion/Figma are built — any experienced frontend engineer knows it

Requires: Apple Developer account ($99/year), Mac code signing + notarization for distribution, Windows code signing certificate. Budget one week of engineer time for the signing pipeline setup.

### Mobile: Phase 4+ only
React Native when core desktop experience is solid and user acquisition justifies it.

---

## 2. Database Strategy

### Primary: PostgreSQL 16 via Supabase (Phase 1–2) → AWS RDS (Phase 2+)
Row-Level Security enforces per-user isolation at the database engine level — not just the API. `FORCE ROW LEVEL SECURITY` on all user-owned tables. No `deleted_at` columns — hard-delete only.

### Vector Search: pgvector → Pinecone/Weaviate
Phase 1–2: pgvector (PostgreSQL extension). Handles up to ~10M vectors efficiently.

**Scale trigger for migration:** When p95 ANN query latency exceeds 200ms at production query volumes. At that point, migrate to Pinecone (serverless) or Weaviate. This is a well-documented migration path.

### Cache: Upstash Redis → AWS ElastiCache
Phase 1: Upstash serverless Redis. Validate Celery broker compatibility in Phase 0a (Spike 5). Fallback: Render Redis (~$7/month) as dedicated broker.

Phase 2+: AWS ElastiCache (Multi-AZ, managed).

### Graph Database: PostgreSQL CTEs → Neo4j AuraDB
Phase 1–2: Topic connections modeled as Postgres join tables. Recursive CTEs handle traversal.

**Scale trigger for migration:** When graph traversal depth exceeds 5 hops with acceptable latency, or when link-traversal query time exceeds 500ms at production volumes. Neo4j AuraDB (managed, no infrastructure) is the upgrade path.

### Object Storage: Supabase Storage → AWS S3
Path structure: `/users/{user_id}/conversations/{conversation_id}/transcript.txt`

No audio stored. Transcripts only. Per-user path prefix enforces isolation at the storage layer.

---

## 3. Meeting Capture

### Phase 1: Manual Upload
User uploads audio file or text transcript. Deepgram transcribes audio. Intelligence extraction runs async. No desktop app required.

**PRD departure note:** PRD Section 11.1 specifies "Phase 1 leverages Google Meet native transcription." Evaluated and rejected: Google Meet captions lack speaker diarization, have lower accuracy on technical vocabulary, and have no API for programmatic retrieval. Deepgram via manual upload is the correct Phase 1 approach, aligned with founder.

### Phase 3: Electron Desktop App (automated capture)
1. App runs as menu bar process in background
2. Detects meeting start via Google Calendar API polling
3. Activates system audio capture (OS-level API)
4. Streams raw PCM audio → FastAPI backend via WebSocket
5. Backend pipes audio → Deepgram real-time streaming
6. Transcript chunks stored in Postgres as TranscriptSegments
7. On meeting end: Celery extraction job triggered

**Phase 3 engineering requirements:**
- Apple Developer account + Mac notarization pipeline
- Windows code signing certificate
- Auto-update mechanism (Electron's built-in updater)
- CI: test on both macOS and Windows after each OS major version

### Why not a bot
Bot joins as visible participant (everyone sees it). Requires Google Workspace admin approval. Farz's privacy identity requires no bots. Bot is available as fallback for non-Mac users in Phase 4.

---

## 4. Transcription Pipeline

### Primary: Deepgram Nova-3
Used by Granola. Best combination of accuracy (~99% English), latency (<300ms streaming), and speaker diarization. Cost: ~$0.0043/minute.

- Phase 1: Deepgram async file transcription API
- Phase 3: Deepgram real-time streaming WebSocket
- `diarize: true` → speaker labels → stored as `speaker_id` in `TranscriptSegment`
- Backup: AssemblyAI (drop-in alternative)

### Audio Lifecycle
**Uploaded audio (Phase 1):**
1. Receive upload → temp storage path
2. Send to Deepgram
3. Success: persist transcript as TranscriptSegments → **hard-delete audio immediately**
4. Failure: **hard-delete audio after 1-hour timeout**
5. Audit log entry created for deletion (timestamp, file hash — no content)

**Streaming audio (Phase 3):**
Memory-only PCM buffer. Never written to disk at any point.

### Post-Meeting Processing: Celery + Redis
Background jobs triggered after transcript stored:
- Entity extraction (persons, projects, products)
- Topic detection and clustering
- Commitment identification (with segment citations)
- Embedding generation → pgvector storage
- Brief pre-computation for next calendar event

**Scale trigger for job queue:** When Celery + Redis queue depth persistently exceeds 1,000 jobs or job latency exceeds SLA (brief must generate within 5 minutes of meeting end), evaluate migration to a dedicated task queue service.

---

## 5. LLM Integration

### Primary Provider: Anthropic Claude
Best at nuanced instruction following — critical for extracting structured data from colloquial transcripts. No training on API data by default.

- `claude-sonnet-4-6`: extraction tasks (topics, commitments, entities)
- `claude-opus-4-6`: Brief generation (highest reasoning quality, used once per meeting)

### ZDR Policy (Internal Testing vs. Production)

**Phase 1 (internal testing):** Standard Anthropic API is acceptable. No-training policy confirmed per API terms. Not a formal ZDR agreement.

**Phase 2+ (external users):** Formal DPA required with every inference and embedding provider before any external user data is processed. Providers without signed DPAs must be removed from the enabled list.

### LLM Provider Policy (Phase 2+ enforcement)

A config file defines all allowed providers:

```yaml
# llm_providers.yaml
providers:
  - provider: anthropic
    model: claude-sonnet-4-6
    purpose: extraction
    zdr_attested: true
    dpa_reference: "Anthropic_DPA_2026-03.pdf"
    enabled: true
  - provider: anthropic
    model: claude-opus-4-6
    purpose: generation
    zdr_attested: true
    dpa_reference: "Anthropic_DPA_2026-03.pdf"
    enabled: true
  - provider: openai
    model: text-embedding-3-small
    purpose: embedding
    zdr_attested: false  # Fails startup if enabled
    enabled: false
```

**Startup enforcement (Phase 2+):**
- Startup fails if any `enabled: true` provider has `zdr_attested: false`
- Only `(provider, model, purpose)` tuples in this file are callable
- All SDK calls route through one `llm_client.py` module
- Transcript content is never logged in application logs, traces, or error payloads

### Structured Output via `instructor` + Pydantic

```python
class CommitmentExtraction(BaseModel):
    text: str
    assignee: str
    deadline: str | None
    confidence_score: float
    segment_ids: list[str]  # Source TranscriptSegment IDs

class TopicList(BaseModel):
    topics: list[str]
    sentiment: str
    importance_score: float
    segment_ids: list[str]

class EntityList(BaseModel):
    persons: list[str]
    projects: list[str]
    products: list[str]
    segment_ids: list[str]
```

### Model Routing Contract

| Task | Default model | Escalation condition | Escalation model |
|------|---------------|---------------------|-----------------|
| Entity extraction | claude-sonnet-4-6 | Never — deterministic task | — |
| Topic clustering | claude-sonnet-4-6 | Never — deterministic task | — |
| Commitment extraction | claude-sonnet-4-6 | Never — deterministic task | — |
| Brief generation | claude-sonnet-4-6 | Context >80k tokens OR ambiguity score >0.7 | claude-opus-4-6 |
| Topic Arc synthesis | claude-sonnet-4-6 | >20 source segments | claude-opus-4-6 |

**Budget guardrails:**
- Max 8,000 input tokens per extraction job
- Max 16,000 input tokens per Brief generation
- Daily spend alert at $10; monthly alert at $200
- On breach: automatic downgrade to cheaper model tier + alert sent

---

## 6. Authentication

### Google OAuth 2.0 via Supabase Auth
Handles full OAuth flow, token storage and refresh, generates `auth.uid()` for RLS policies.

- Phase 1 scopes: `calendar.readonly`, `profile`, `email`
- Phase 4: add `gmail.readonly` (requires Google OAuth app verification — start 6–8 weeks before Phase 4 launch)
- Electron app: `chrome.identity.getAuthToken()` for seamless in-app OAuth

---

## 7. Per-User Isolation — Enforced at Every Layer

### Database Role Matrix

| Role | Key | Allowed operations |
|------|-----|--------------------|
| `anon` | Supabase anon key | No access to user tables |
| `authenticated` | Supabase user JWT | Read/write own rows only (RLS enforced) |
| `service_role` | Supabase service key | DDL and migrations only — **never for data reads** |
| Celery workers | User JWT passed in job payload | Read/write own rows, `WHERE user_id = $1` on every query |
| `migration_admin` | Separate role | Schema changes only — no DML on user tables |

**`service_role` bypasses RLS entirely.** If workers use it for data reads, isolation is broken. Workers receive the user's JWT as part of the job payload and use it for all database operations. This is tested in CI.

### All Isolation Layers

| Layer | Mechanism |
|-------|-----------|
| Postgres | `FORCE ROW LEVEL SECURITY` on all user-owned tables |
| Object Storage | Path: `/users/{user_id}/...` enforced at bucket policy level |
| Redis | Key namespace: `user:{user_id}:...` |
| Vector search | `WHERE user_id = $1` applied before ANN search |
| LLM calls | No cross-user batching; each call is single-user scoped |
| Celery jobs | `user_id` in payload; ownership verified before execution |
| API | JWT middleware extracts `user_id`; injected into every DB query |

**CI requirement:** Isolation tests run on every PR and block release on failure. Tests cover: API endpoints, vector search, cache keys, object storage paths, and worker execution context.

---

## 8. Infrastructure

### Phase 1 — Internal Testing (~$50/month)

| Service | Provider | Cost |
|---------|----------|------|
| Backend + Celery workers | Render.com | ~$25/month |
| Database + Auth + Storage | Supabase | Free tier |
| Redis (cache) | Upstash | Free tier |
| Redis (Celery broker, fallback) | Render Redis | ~$7/month |
| Transcription | Deepgram API | ~$0.26/hr audio |
| LLM | Anthropic API | ~$0.50–2.00/hr meeting |

### Phase 2 — Production-Grade (engineer hired, first external users)

| Service | Provider | Notes |
|---------|----------|-------|
| Backend | AWS ECS Fargate | Containerized FastAPI + Celery, no server management |
| Database | AWS RDS PostgreSQL | Multi-AZ, point-in-time recovery |
| Cache | AWS ElastiCache | Redis Cluster mode |
| Storage | AWS S3 | Per-user bucket policies |
| CDN | AWS CloudFront | Frontend assets |
| CI/CD | GitHub Actions | Docker build → ECR → ECS deploy |
| Error monitoring | Sentry | |
| Performance monitoring | Datadog | |

### Phase 3 — Scale

| Component | Trigger | Migration |
|-----------|---------|-----------|
| pgvector → Pinecone | p95 ANN query latency >200ms | Pinecone serverless; re-index all user embeddings |
| Postgres CTEs → Neo4j | Graph traversal >5 hops with >500ms latency | Neo4j AuraDB; migrate connection graph |
| Redis → Kafka | Write throughput >10k events/min sustained | Kafka for CDC + data lake pattern (Debezium → Kafka → S3) |

---

## 9. Search & Indexing

### Semantic Search: pgvector
Embeddings generated for: Conversations, TranscriptSegments, Topics, Commitments.

Search algorithm:
1. Embed the query
2. `WHERE user_id = $1` filter applied before ANN search
3. Top-50 vector hits retrieved
4. Combined with top-50 lexical hits (see hybrid below)
5. Results ranked by hybrid formula
6. Return top-8 with full citation payload

### Hybrid Ranking: Vector + Full-Text

**Full-text:** PostgreSQL `tsvector`/`tsquery` with `ts_rank_cd` scoring (not BM25 — PostgreSQL uses its own scoring formula similar in spirit to BM25 but not identical).

**Hybrid formula:** `0.65 × normalized_vector_score + 0.35 × normalized_lexical_score`

This weighting prioritizes semantic similarity while retaining exact keyword recall. The weights are a starting point — tune against real query evaluation data.

### Citation Payload (required on all search results)
Every search result must include:
```python
class SearchResult(BaseModel):
    conversation_id: str
    start_ts: float         # seconds from conversation start
    end_ts: float
    speaker_id: str
    snippet: str            # the exact quote
    score: float            # final hybrid score
```

### Topic Clustering (async)
Post-meeting Celery job:
1. Extract candidate topics via LLM
2. Embed each topic
3. Compare against user's existing topic embeddings (cosine similarity)
4. **Dual-threshold merge policy:**
   - Similarity ≥ 0.85: auto-merge into existing topic
   - Similarity 0.65–0.85: flag as `needs_review` — surface to user for confirmation
   - Similarity <0.65: create new topic
5. Store confidence score on every topic link
6. User corrections feed back into the clustering job as labeled training signal

---

## 10. Data Model

### 9 Core Entities

**TranscriptSegment** *(required from Phase 0 — enables all traceability)*
`conversation_id`, `speaker_id`, `start_ts`, `end_ts`, `text`, `segment_confidence`

Every derived entity (Commitment, Topic, Connection) links to one or more TranscriptSegments. This is the foundation of citation and hallucination defense.

**Conversation** — source platform, participants, start_ts, duration

**Topic** — label, first_mentioned, last_mentioned, status, linked segments, confidence score

**Topic Arc** — view over Topic × Conversations ordered by time; every claim cites a TranscriptSegment

**Connection** — relationship between Conversations/Topics; links to source segments; confidence score

**Commitment** — text, assignee, deadline, status, source segments

**Entity** — persons, projects, products; internal enrichment layer

**Brief** — generated artifact from Topic Arcs + Commitments + Connections + Calendar event; private by default

**Index** — per-user conversation store; all entities above; architecturally isolated

### Relationships
```
Index (per user)
├── Conversations [1..N]
│   └── TranscriptSegments [1..N]
│       ├── extracted → Commitments [0..N]
│       └── referenced → Entities [0..N]
├── Topics [0..N]
│   ├── linked to → Conversations + TranscriptSegments
│   └── confidence_score on each link
├── Topic Arcs [0..N] (view: Topics × Conversations × time)
└── Connections [0..N]
    ├── links → Conversations or Topics [2..N]
    └── confidence_score, review_status

Brief
└── composed from → Topic Arcs + Commitments + Connections + Calendar event
```

---

## 11. Intelligence Evaluation Contract

Every intelligence output type has a quality gate. No release to the next phase unless all thresholds pass on the holdout set.

### Evaluation Dataset
- **Training/tuning set:** 30 labeled transcripts
- **Holdout (release gate):** 10 labeled transcripts (never used for tuning)

### Thresholds

| Output type | Metric | Minimum threshold |
|-------------|--------|------------------|
| Commitment extraction | Precision | ≥ 0.85 |
| Commitment extraction | Recall | ≥ 0.75 |
| Topic quality | Duplicate rate | ≤ 0.15 |
| Topic quality | Human coherence score | ≥ 0.80 (1–5 scale, averaged) |
| Connection quality | Precision@5 (top-5 surfaced links) | ≥ 0.80 |
| Brief quality | Citation coverage | ≥ 0.95 (factual claims that cite a source segment) |

**Release gate:** All thresholds must pass on the holdout set before advancing to the next roadmap phase.

---

## 12. Retrieval Contract

Deterministic retrieval behavior — tunable but never arbitrary.

- **Chunk unit:** Speaker-turn-first segments; hard cap 220 tokens; overlap 40 tokens between adjacent segments
- **Candidate generation:** top-50 vector hits + top-50 lexical hits, per user (isolation filter first)
- **Hybrid ranking:** `0.65 × normalized_vector_score + 0.35 × normalized_lexical_score`
- **Reranking:** deterministic reranker step on top-20 candidates → return top-8 evidence chunks
- **Citation payload required:** `conversation_id`, `start_ts`, `end_ts`, `speaker_id`, `snippet`

---

## 13. Data Lifecycle Contract

### Transient Audio
1. Receive upload → temp storage path (AES-256 encrypted)
2. Send to Deepgram
3. On success: hard-delete audio immediately after transcript persisted
4. On failure: hard-delete after 1-hour cleanup job
5. Audit event: `{event: "audio_deleted", file_hash: "...", ts: "..."}` — no content logged
6. Streaming audio (Phase 3): memory-only PCM buffer; never touches disk

### User-Initiated Delete
Irreversible cascade across all stores:
1. Postgres rows (all user-owned tables) — CASCADE delete
2. pgvector embeddings (all rows with `user_id`)
3. Redis cache keys (`SCAN` + `DEL` pattern: `user:{user_id}:*`)
4. Supabase Storage (`/users/{user_id}/` prefix — all objects)
5. Derived artifacts (Briefs, Topic Arcs, Connections)
6. Audit event: `{event: "user_delete", user_id_hash: "...", ts: "..."}` — no content logged

### User Export
User can request export of all owned data at any time:
- JSON export: all Conversations, TranscriptSegments, Topics, Commitments, Entities, Connections, Briefs
- Delivered as a download link (expires in 24 hours)
- Audit event: `{event: "user_export", user_id_hash: "...", ts: "..."}`

---

## 14. Security & Compliance

### Encryption
- At rest: AES-256 (Supabase/AWS default — confirmed, no additional configuration)
- In transit: TLS 1.2+ (enforced at load balancer level)

### Access Audit Logging
Log the following events (timestamps + actor ID — never content):
- User data export (triggered)
- User data delete (triggered)
- Audio file delete (each file)
- Admin production access (if any)

### Compliance Sequencing

| Certification | Target phase | Trigger |
|---------------|-------------|---------|
| SOC 2 Type II | Phase 3 | Before onboarding first paying customer |
| GDPR readiness | Phase 2 end | Before any EU user is onboarded |
| UAE ADGM / DIFC | Phase 3 | Before UAE enterprise sales |

---

## Phase Roadmap

### Phase 0a — Technical Spikes (Week 1)
Feasibility checks. Not product features. Architecture changes if any spike fails.

- [ ] Spike 1: Electron audio capture — system audio → local file
- [ ] Spike 2: Deepgram accuracy on real meetings (accuracy + diarization)
- [ ] Spike 3: LLM extraction quality on 5 real transcripts
- [ ] Spike 4: Supabase RLS isolation — automated CI test
- [ ] Spike 5: Celery broker via Upstash (retry, visibility timeout, reconnect)

### Phase 0 — Foundation (Weeks 2–4)
- [ ] Project structure + `pyproject.toml` with pinned versions
- [ ] Full schema for all 9 entities + RLS policies (FORCE RLS)
- [ ] No `deleted_at` columns — hard-delete only from the start
- [ ] FastAPI skeleton + Google OAuth + health check
- [ ] Spend alert ($100/month) set on Anthropic

### Phase 1 — Manual Upload + Intelligence (Weeks 5–12)
- [ ] File upload endpoint (audio + transcript)
- [ ] Deepgram async transcription
- [ ] Audio hard-delete lifecycle
- [ ] TranscriptSegment storage
- [ ] LLM extraction with segment citations (instructor + Pydantic)
- [ ] pgvector embeddings
- [ ] Basic UI: upload → view topics/commitments → click to source quote
- [ ] Semantic search with citation payload

**Quality gate:** 10 real transcripts evaluated across all 4 output types before proceeding.

### Phase 2 — Intelligence Surface (Weeks 13–20)
- [ ] Topic Arc with per-claim citations
- [ ] Connection detection with confidence scores
- [ ] Pre-meeting Brief (T-12m trigger, late-delivery fallback)
- [ ] Dashboard: timeline + commitment tracker
- [ ] Google Calendar sync

### Phase 3 — Automated Capture + Production (Weeks 21–36)
- [ ] Electron desktop app: system audio → WebSocket → real-time Deepgram
- [ ] Mac code signing + notarization
- [ ] Windows build pipeline
- [ ] Auto-update mechanism
- [ ] AWS migration: ECS Fargate + RDS + ElastiCache + S3
- [ ] CI/CD: GitHub Actions → Docker → ECS
- [ ] Monitoring: Sentry + Datadog
- [ ] SOC 2 Type II audit initiated

### Phase 4 — Expand (Post-engineer hire)
- [ ] Gmail integration (`gmail.readonly` scope — start Google OAuth verification 8 weeks early)
- [ ] Slack integration
- [ ] Bot-based capture (alternative for non-Mac users)
- [ ] Mobile app (React Native)
- [ ] Multilingual support (Arabic, Hindi — start language scope assessment in Phase 2)
- [ ] Cold-start utility mode (value for new users before enough meetings indexed)

---

## Key Risks (Full Scope)

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM extraction quality too low on noisy meetings | **High** | Phase 1 quality gate: 10 transcripts, all 4 output types, before Phase 2 |
| service_role bypasses RLS in workers | **High** | CI isolation test; code review rule; no service_role in application code |
| Electron audio capture breaks on macOS update | **Medium** | Pin Electron version; CI test on macOS and Windows after major OS updates |
| Mac code signing and notarization complexity | **Medium** | Budget 1 week; Apple Developer account ($99/year); start in first Phase 3 sprint |
| Celery broker unreliable on Upstash free tier | **Medium** | Phase 0a Spike 5; fallback to Render Redis before Phase 1 |
| pgvector performance at scale | **Medium** | Objective trigger defined: p95 >200ms → Pinecone migration |
| Topic merge over-merges unrelated topics | **Medium** | Dual-threshold policy (auto-merge / needs-review); user correction loop |
| Anthropic API spend surprise | **Low** | $100/month alert in Phase 0; model routing budget guardrails in Phase 2 |
| Google OAuth scope verification delays (Gmail) | **Low** | Start verification 8 weeks before Phase 4; only `calendar.readonly` in Phase 1 |
| Engineer handoff — undocumented decisions | **High** | This document + ADR folder in repo; inline code comments |

---

## Tech Stack Summary (Full Vision)

| Category | Phase 1–2 | Phase 3+ |
|----------|-----------|----------|
| Backend | Python 3.13 + FastAPI + Pydantic v2 | Same |
| Frontend | Next.js 15 + TypeScript + Tailwind | Same |
| Desktop app | — | Electron + TypeScript |
| Database | Supabase PostgreSQL + pgvector | AWS RDS + Pinecone |
| Graph | Postgres CTEs | Neo4j AuraDB |
| Auth | Supabase Auth + Google OAuth | Same |
| Cache | Upstash Redis | AWS ElastiCache |
| Transcription | Deepgram Nova-3 | Same |
| LLM (extraction) | claude-sonnet-4-6 | Same |
| LLM (briefs) | claude-opus-4-6 | Same |
| LLM wrapper | instructor + Pydantic | Same |
| Async jobs | Celery + Redis | Celery + Redis → Kafka |
| Object storage | Supabase Storage | AWS S3 |
| Hosting | Render.com | AWS ECS Fargate |
| CI/CD | — | GitHub Actions |
| Monitoring | — | Sentry + Datadog |
| Compliance | — | SOC 2, GDPR, UAE |
