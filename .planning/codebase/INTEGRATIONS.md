# External Integrations

**Analysis Date:** 2026-03-11

## APIs & External Services

**LLM (Anthropic):**
- claude-sonnet-4-6 - Extraction of topics, commitments, entities from transcripts
  - SDK/Client: `anthropic==0.84.0` wrapped via `instructor==1.7.2` for structured output
  - Config: `src/llm_client.py` centralizes all Claude API calls (ONLY module allowed to call Claude)
  - Auth: `ANTHROPIC_API_KEY` env var
  - Cost monitoring: Set $100/month alert on Anthropic dashboard before use

- claude-opus-4-6 - Pre-meeting brief generation from context
  - SDK/Client: `anthropic==0.84.0` via `src/llm_client.py`
  - Auth: Same `ANTHROPIC_API_KEY`
  - Usage: Sparingly; called only when generating briefs

**Embeddings (OpenAI):**
- text-embedding-3-small - 1536-dimensional embeddings for transcript segments
  - SDK/Client: `openai==1.109.1`
  - Config: `src/llm_client.py` — `embed_texts()` function
  - Dimensions: 1536 (fixed by model)
  - Auth: `OPENAI_API_KEY` env var
  - Vector storage: pgvector in `transcript_segments.embedding` column

**Transcription (Deepgram):**
- Deepgram Nova-3 - Speech-to-text from meeting audio
  - SDK/Client: `deepgram-sdk==3.9.0`
  - Auth: `DEEPGRAM_API_KEY` env var
  - Estimated cost: ~$0.0043/minute (1 hour of meetings ≈ $0.26)
  - Usage: Invoked by Celery ingest worker; no reference in current codebase but required for spike 2

**Google APIs:**
- Google Drive API v3 - List and export Meet transcript documents
  - SDK/Client: Custom via `httpx==0.28.1` (not using official Google client)
  - Scope: `drive.readonly` (only read transcripts, never write)
  - Auth: Google OAuth 2.0 access token (stored in `user_index.google_access_token`)
  - Implementation: `src/drive_client.py` with async + sync variants
  - Functions:
    - `list_meet_transcripts()` — lists Google Docs in "Meet Recordings" folder, created in last 365 days
    - `export_transcript_sync()` — exports single transcript as plain text
    - `refresh_access_token()` / `refresh_access_token_sync()` — OAuth token refresh

- Google OAuth 2.0 - User authentication + authorization
  - Config: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` env vars
  - Callback endpoint: `POST /auth/callback` (route in `src/api/routes/auth.py`)
  - Token storage: Refresh token in `user_index.google_refresh_token`; access token cached in memory during request
  - Redirect URIs: `${FRONTEND_URL}/auth/callback` (configured in Google Cloud Console)

- Google Calendar API - Retrieve upcoming meetings (stub in Phase 1)
  - Scope: `calendar.readonly` (same OAuth flow as Drive)
  - Status: Not yet implemented; `GET /calendar/today` returns empty `upcoming_meetings: []`

## Data Storage

**Databases:**

- Supabase PostgreSQL 16 - Primary application database
  - Connection: `SUPABASE_URL` (HTTPS endpoint)
  - Auth layer: Supabase Auth (JWT-based)
  - Client: `supabase==2.15.1` (PostgREST API wrapper)
  - Direct connection: `DATABASE_URL` via `psycopg2==2.9.11` (for pgvector queries only)
  - RLS: FORCE ROW LEVEL SECURITY on all user-owned tables and junctions
  - Schema: 9 core tables + 8 junction tables, managed via migrations in `migrations/`
  - Extensions: pgvector (1536-dim embeddings), uuid-ossp
  - Tables with user isolation:
    - `user_index` (per-user metadata)
    - `conversations`, `transcript_segments`, `topics`, `commitments`, `entities` (user-scoped)
    - `topic_arc`, `briefs`, `connections` (user-scoped)
    - 8 junction tables for linking (all enforced FORCE RLS)

**File Storage:**

- Supabase Storage (S3-compatible) - Transcript text storage only
  - Path namespace: `/users/{user_id}/...` (per-user isolation)
  - Content: Text transcripts only (audio files are transient — deleted immediately after transcription)
  - Access: Via Supabase client or direct S3 API (not yet in use for audio; Phase 2+)

**Caching:**

- Upstash Redis (serverless, rediss:// TLS) - Celery broker + result backend
  - Connection: `UPSTASH_REDIS_URL` env var (format: `rediss://:password@host:port`)
  - Serialization: JSON only (never pickle)
  - Key namespace: `user:{user_id}:...` (enforced at Celery task level)
  - Config: `src/celeryconfig.py` with explicit TLS (`ssl_cert_reqs: CERT_REQUIRED`)
  - Reliability settings:
    - `task_acks_late: True` — ack only after task completes
    - `task_reject_on_worker_lost: True` — reject if worker dies
    - `visibility_timeout: 3600` (1 hour, adjust if tasks run longer)
    - `result_expires: 86400` (24 hours)
    - `worker_prefetch_multiplier: 1` (process one task at a time)

## Authentication & Identity

**Auth Provider:**

- Supabase Auth + Google OAuth 2.0 (custom integration)
  - Implementation: `src/api/routes/auth.py`
  - Flow:
    1. Frontend redirects user to `/auth/login` → Google OAuth consent screen
    2. User authorizes → Google redirects to `/auth/callback` with auth code
    3. Backend exchanges code for tokens (access + refresh)
    4. Backend creates Supabase user or links to existing account
    5. JWT token returned; set as HttpOnly `session` cookie
  - Token storage:
    - Supabase JWT: HttpOnly cookie `session` (for browser auth) or Authorization Bearer header (for API clients)
    - Google access token: In-memory during request; can be cached in database
    - Google refresh token: Stored in `user_index.google_refresh_token` for token refresh
  - JWT validation: JWKS endpoint from Supabase (cached for 3600 seconds)

**Auth Headers:**

- Cookie-first strategy: `GET /auth/session` checks HttpOnly `session` cookie
- Bearer token fallback: `Authorization: Bearer {jwt}` for API clients (tests, Celery workers)
- Dependency: `src/api/deps.py` — `get_current_user()` enforces auth on protected routes

## Monitoring & Observability

**Error Tracking:**

- Not implemented (Phase 2+)
- Placeholder: Sentry integration planned for production

**Logs:**

- stdout/stderr via Python `logging` module
- Log level: Controlled by `LOG_LEVEL` env var (default: INFO)
- Format: `"%(asctime)s %(levelname)s %(name)s — %(message)s"`
- Render.com: Logs visible in dashboard
- Critical constraint: Transcript content NEVER logged (enforced in `src/llm_client.py`)

## CI/CD & Deployment

**Hosting:**

- Render.com (4 services in `render.yaml`)
  1. `farz-api` (web, starter plan, ~$7/mo)
  2. `farz-worker` (combined Celery worker, starter plan, ~$7/mo)
  3. Estimated total: ~$28/mo for 4 services (API + worker was combined in latest config)
  4. Region: Oregon
  5. Auto-deploy: Connected to `main` branch

- Frontend (Next.js 15): Auto-deployed to Vercel (separate from backend, URL: `https://farz-personal-intelligence.vercel.app`)

**CI Pipeline:**

- GitHub Actions (`.github/workflows/ci.yml`)
- Runs on push to `main` or PR creation
- Jobs:
  1. **lint-typecheck-test**: Ruff + mypy + pytest (unit tests only)
  2. **rls-isolation**: RLS tests if Supabase credentials available (gated by `vars.SUPABASE_URL`)
  - Environment: `ENVIRONMENT=test` (disables external service dependencies)

**Deployment URL:**

- Backend health check: https://farz-personal-intelligence.onrender.com/health
- Auto-restart on push to main via Render GitHub integration

## Environment Configuration

**Required env vars (all must be present at startup):**

```
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY
DATABASE_URL
ANTHROPIC_API_KEY
OPENAI_API_KEY
UPSTASH_REDIS_URL
DEEPGRAM_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
SECRET_KEY
```

**Secrets location:**

- Development: `.env` file (gitignored)
- Production: Render.com Secret Group (shared across all 4 services)
- Template: `.env.example` (safe to commit)
- Manual setup: Copy `.env.example` → `.env` and fill in real values

**Important:** Do NOT commit `.env`. Ensure `.gitignore` covers `.env*` (except `.env.example`).

## Webhooks & Callbacks

**Incoming:**

- `POST /auth/callback` — Google OAuth redirect URI (receives auth code)
- Status: Active, used in production auth flow

**Outgoing:**

- None currently (Phase 1)
- Planned Phase 2+: Webhook delivery for calendar event triggers, context updates

---

*Integration audit: 2026-03-11*
