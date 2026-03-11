# Architecture

## Pattern

**Layered monolith with async job offloading.** FastAPI handles synchronous HTTP requests; Celery handles long-running async work (transcript ingestion, extraction, embedding). Both share the same Pydantic models and database layer.

```
Client (browser / Codex frontend)
        │  HTTPS
        ▼
FastAPI app (src/main.py)
        │
        ├── Middleware: CORSMiddleware (single allowed origin)
        │
        └── Router (src/api/routes/__init__.py)
              ├── /auth        — OAuth2 callback, session, logout
              ├── /conversations — list, detail, connections stub
              ├── /topics      — list, detail
              ├── /commitments — list, patch status
              ├── /search      — pgvector cosine similarity
              ├── /onboarding  — bulk import, job status polling
              ├── /calendar    — upcoming meetings (stub)
              ├── /index/stats — per-user index stats
              └── /health      — liveness probe

Celery workers (Upstash Redis broker)
        ├── ingest_recording   — Drive export → parse → persist
        ├── extract_from_conversation — LLM extraction (topics/commitments/entities)
        └── embed_conversation — OpenAI embedding → pgvector store
```

## Data Flow

### Transcript Ingestion Pipeline
```
Google Drive (user's transcript Doc)
  → ingest_recording task
      1. refresh_access_token_sync(refresh_token) → fresh access_token
      2. export_transcript_sync(access_token, file_id) → plain text
      3. _detect_and_parse(text) → segments + source_type
         ├── google_meet_transcript: timestamp-based parser
         └── gemini_notes: paragraph-based parser
      4. INSERT conversations + transcript_segments (RLS via user_jwt)
      5. UPDATE user_index.last_updated
      6. .delay() → extract_from_conversation
      7. .delay() → embed_conversation

extract_from_conversation
  → Claude (claude-sonnet-4-6 via instructor + Pydantic)
  → INSERT topics / commitments / entities + junction links

embed_conversation
  → OpenAI text-embedding-3-small (1536 dims)
  → UPDATE transcript_segments.embedding (pgvector)
```

### Search Flow
```
POST /search { query, user_id }
  → embed query text (OpenAI)
  → raw psycopg2 (get_direct_connection) with <=> cosine operator
  → WHERE user_id = %s  ← explicit, not RLS (RLS bypassed by direct conn)
  → return ranked transcript_segments
```

### Auth Flow
```
GET /auth/callback?code=...
  → Supabase exchange_code_for_session
  → Set HttpOnly "session" cookie (access_token)
  → User routed to frontend

Subsequent requests:
  → deps.get_current_user() extracts JWT from cookie or Bearer header
  → get_client(jwt) → Supabase client with user's JWT (RLS enforced)
```

## Key Abstractions

| Abstraction | File | Purpose |
|---|---|---|
| `settings` | `src/config.py` | Pydantic-settings singleton; validates all env vars at startup |
| `get_client(jwt)` | `src/database.py` | Supabase client scoped to user (RLS enforced) |
| `get_admin_client()` | `src/database.py` | Service-role client — migrations/CI only |
| `get_direct_connection()` | `src/database.py` | Raw psycopg2 for pgvector queries |
| `celery_app` | `src/celery_app.py` | Shared Celery instance (Upstash Redis, TLS) |
| `llm_client` | `src/llm_client.py` | All LLM calls go here — no direct SDK calls elsewhere |
| `get_current_user` | `src/api/deps.py` | FastAPI dependency — extracts validated user_id + jwt |

## Security Layer

All 17 tables use `FORCE ROW LEVEL SECURITY` (not just ENABLE). Policies: `USING (user_id = auth.uid())`. The `service_role` key bypasses RLS — it is only used in:
- Migration scripts
- CI test harness setup (`conftest.py` service_client fixture)

Celery workers always receive `user_id` + `user_jwt` in payload and use `get_client(user_jwt)` for DB writes.

## Entry Points

| Entry Point | Command |
|---|---|
| API server | `uvicorn src.main:app --reload` |
| Celery worker | `celery -A src.celery_app worker ...` |
| Combined worker | `src/workers/combined.py` |
| Migrations | `supabase db push` (SQL files in `migrations/`) |

## Frontend

Currently a stub — Phase 1 Wave 4 is the Next.js frontend (Codex's track). The `agent_docs/CODEX_BRIEF.md` defines the full API contract. Claude Code does not touch `frontend/`.
