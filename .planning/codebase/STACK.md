# Technology Stack

**Analysis Date:** 2026-03-11

## Languages

**Primary:**
- Python 3.13.5 - Backend API, workers, and all server-side logic

**Secondary:**
- TypeScript/JavaScript - Frontend (Next.js 15, developed separately in `frontend/`)
- SQL - Database migrations and queries (PostgreSQL 16)

## Runtime

**Environment:**
- Python 3.13 (pinned in `.python-version`)
- Virtual environment: `.venv/bin/activate`
- No Docker in use; deployment is direct to Render.com

**Package Manager:**
- pip (Python package manager)
- Lockfile: `requirements.txt` (pinned versions, no ranges)

## Frameworks

**Core:**
- FastAPI 0.135.1 - REST API framework, CORS middleware, dependency injection
- Uvicorn 0.41.0 (with standard extras) - ASGI server, deployed with `--workers 2`
- Pydantic 2.12.5 - Strict schema validation for all request/response models
- pydantic-settings 2.8.0 - Environment configuration with validation at startup

**Task Queue:**
- Celery 5.4.0 - Async job processing (ingest, extract, embed workers)
- Upstash Redis 5.2.1 - Broker and result backend, rediss:// with explicit TLS

**Testing:**
- pytest 9.0.2 - Unit test runner
- pytest-anyio 0.0.0 - Async test support

**Code Quality:**
- ruff 0.15.5 - Linting and formatting (enforced rules in `pyproject.toml`)
- mypy 1.19.1 - Strict type checking (`strict = true` in config)

## Key Dependencies

**Critical:**

- anthropic 0.84.0 - Claude API for extraction (topics/commitments/entities) and brief generation
- instructor 1.7.2 - Structured output parsing via Pydantic for LLM responses
- openai 1.109.1 - Embeddings (text-embedding-3-small, 1536 dimensions)
- supabase 2.15.1 - Database client, auth provider, storage integration
- psycopg2-binary 2.9.11 - Direct PostgreSQL connection for pgvector queries (RealDictCursor)
- deepgram-sdk 3.9.0 - Transcription (Nova-3 model)
- python-jose[cryptography] 3.3.0 - JWT validation for Supabase Auth tokens
- redis 5.2.1 - Redis client for Upstash broker communication

**HTTP & Config:**

- httpx 0.28.1 - Async/sync HTTP client for Google Drive API + OAuth token refresh
- python-dotenv 1.0.1 - Load environment variables from `.env`

## Configuration

**Environment:**

Environment variables are validated at startup via `src/config.py` using Pydantic `BaseSettings`. The server does NOT start if any required var is missing:

**Required:**
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` - Database, auth, storage
- `DATABASE_URL` - Direct PostgreSQL connection (psycopg2), password must be URL-encoded (`%40` for `@`)
- `ANTHROPIC_API_KEY` - Claude API access
- `OPENAI_API_KEY` - OpenAI embeddings
- `UPSTASH_REDIS_URL` - Celery broker (format: `rediss://:password@host:port`)
- `DEEPGRAM_API_KEY` - Transcription service
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - OAuth 2.0 credentials
- `SECRET_KEY` - 32-byte hex string for session signing

**Optional (with sensible defaults):**
- `ENVIRONMENT` - "development" or "production" (default: "development")
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR (default: "INFO")
- `API_BASE_URL` - Server origin (default: "http://localhost:8000")
- `FRONTEND_URL` - Frontend origin for CORS (default: "http://localhost:3000")
- `JWT_ALGORITHM` - HS256 or RS256 (default: "HS256")
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Session duration (default: 60)
- `SUPABASE_JWT_AUDIENCE` - JWT aud claim (default: "authenticated")
- `SUPABASE_JWT_ISSUER` - JWT iss claim (auto-derived if blank)
- `SUPABASE_JWT_SECRET` - For legacy HS256 projects (leave blank for RS256)
- `SUPABASE_JWKS_TTL_SECONDS` - JWKS cache lifetime (default: 3600)

**Build:**

- `pyproject.toml` - Project metadata, dependencies, tool configs (ruff, mypy, pytest)
- `requirements.txt` - Pinned production dependencies (generated from `pyproject.toml`)
- `.pre-commit-config.yaml` - Pre-commit hooks: ruff lint + format

## Platform Requirements

**Development:**

- Python 3.13
- pip
- PostgreSQL 16 client libraries (for psycopg2-binary)
- Source venv: `source .venv/bin/activate` (created with `pip install -r requirements.txt`)

**Production:**

- Render.com deployment (currently live at https://pocket-nori-personal-intelligence.onrender.com)
- Starter plan (4 services: 1× API web service + 1× combined Celery worker)
- Render builds via `buildCommand: pip install -r requirements.txt`
- Render starts API with: `uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 2`
- Render starts worker with: `celery -A src.workers.combined worker --loglevel=info --concurrency=2`

## CI/CD

**Testing Pipeline:**

- GitHub Actions (`.github/workflows/ci.yml`)
- Runs on: Ubuntu latest, Python 3.13
- Steps:
  1. Ruff lint: `ruff check .`
  2. Ruff format check: `ruff format --check .`
  3. Mypy type check: `mypy src/ --ignore-missing-imports`
  4. Pytest unit tests: `pytest tests/ -v -m "not integration"`
  5. RLS isolation tests (if Supabase credentials available): promotion from `spikes/spike4_supabase_rls/test_rls_isolation.py`

**Deployment:**

- Auto-deploy to Render.com on push to `main` branch
- Frontend (Next.js) auto-deploys to Vercel (separate from backend)

---

*Stack analysis: 2026-03-11*
