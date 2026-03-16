# Structure

## Directory Layout

```
Pocket Nori/
├── src/                          # Application source (Python)
│   ├── main.py                   # FastAPI app factory + lifespan
│   ├── config.py                 # Pydantic-settings (env var validation at startup)
│   ├── database.py               # Supabase client factory + psycopg2 direct conn
│   ├── celery_app.py             # Celery instance (shared broker config)
│   ├── celeryconfig.py           # Celery broker/backend config (Upstash Redis TLS)
│   ├── llm_client.py             # All LLM + embedding calls (Anthropic + OpenAI)
│   ├── drive_client.py           # Google Drive export + token refresh
│   ├── api/
│   │   ├── deps.py               # FastAPI dependencies (auth, current_user)
│   │   └── routes/
│   │       ├── __init__.py       # Aggregated router (includes all sub-routers)
│   │       ├── auth.py           # /auth — OAuth2 callback, session, logout
│   │       ├── conversations.py  # /conversations — list + detail
│   │       ├── topics.py         # /topics — list + detail
│   │       ├── commitments.py    # /commitments — list + patch
│   │       ├── search.py         # /search — pgvector cosine
│   │       ├── onboarding.py     # /onboarding — bulk import + status
│   │       ├── calendar.py       # /calendar — upcoming meetings (stub)
│   │       ├── index_stats.py    # /index/stats
│   │       └── health.py         # /health — liveness probe
│   ├── models/                   # Pydantic models (9 core entities)
│   │   ├── conversation.py
│   │   ├── transcript_segment.py
│   │   ├── topic.py
│   │   ├── topic_arc.py
│   │   ├── commitment.py
│   │   ├── entity.py
│   │   ├── connection.py
│   │   ├── brief.py
│   │   └── index.py
│   └── workers/                  # Celery tasks
│       ├── tasks.py              # Legacy stubs (process_transcript, generate_brief)
│       ├── ingest.py             # ingest_recording task (Drive → DB)
│       ├── extract.py            # extract_from_conversation task (LLM → DB)
│       ├── embed.py              # embed_conversation task (OpenAI → pgvector)
│       └── combined.py           # Combined worker entry point
│
├── tests/                        # pytest test suite
│   ├── conftest.py               # Shared fixtures (Celery eager, Supabase clients)
│   ├── test_workers.py           # process_transcript + generate_brief unit/integration
│   ├── test_ingest.py            # ingest_recording unit tests
│   ├── test_extract.py           # extract_from_conversation unit tests
│   ├── test_search.py            # /search endpoint unit tests
│   ├── test_topics.py            # /topics endpoint unit tests
│   ├── test_commitments.py       # /commitments endpoint unit tests
│   └── test_rls_isolation.py     # Supabase RLS cross-user isolation (integration)
│
├── migrations/                   # Supabase SQL migrations (applied in order)
│   ├── 001_core_schema.sql       # 9 core tables + FORCE RLS policies
│   ├── 002_junction_rls.sql      # 8 junction tables + FORCE RLS
│   ├── 003_google_tokens.sql     # google_access_token + google_refresh_token cols
│   └── 004_conversation_status.sql # status column on conversations
│
├── spikes/                       # Phase 0a technical spikes (reference only)
│   ├── spike1_electron_audio/    # Electron audio capture POC
│   ├── spike2_deepgram/          # Deepgram transcription POC
│   ├── spike3_llm_extraction/    # Claude LLM extraction POC
│   ├── spike4_supabase_rls/      # Supabase RLS isolation POC
│   └── spike5_celery_redis/      # Celery + Upstash Redis POC
│
├── agent_docs/                   # Extended context documents for Claude
│   └── CODEX_BRIEF.md            # API contract for Codex frontend agent
│
├── docs/                         # Project documentation
│   └── working-notes/PROGRESS.md # Execution log (update after each task)
│
├── .interface-design/
│   └── system.md                 # Design tokens (colors, typography, depth)
│
├── .planning/                    # GSD planning artifacts (this dir)
│   └── codebase/                 # Codebase map documents
│
├── .github/workflows/            # CI pipelines
│   └── ci.yml                    # Main CI (lint, type-check, tests)
│
├── .venv/                        # Python 3.13 virtual environment
├── pyproject.toml                # Ruff + mypy config
├── CLAUDE.md                     # Claude Code project instructions
├── DOCS.md                       # Documentation index + hierarchy
├── pocket-nori-prd.md                   # Product requirements document
├── pocket-nori-tech-requirements-mvp.md # Technical decisions (source of truth)
└── pocket-nori-ui-spec.md               # UI object model + screen specs
```

## Key Locations

| What | Where |
|---|---|
| Add a new API route | `src/api/routes/<name>.py` → register in `src/api/routes/__init__.py` |
| Add a new Celery task | `src/workers/<domain>.py` → import task in combined.py if needed |
| Add a new Pydantic model | `src/models/<entity>.py` |
| Add a migration | `migrations/00N_description.sql` (sequential, never modify existing) |
| All LLM calls | `src/llm_client.py` only — never import SDK directly in other files |
| Auth dependency | `src/api/deps.get_current_user` — inject in every protected route |
| Design tokens | `.interface-design/system.md` |
| Frontend | `frontend/` — Codex's domain, Claude Code stays out |

## Naming Conventions

- **Files**: `snake_case.py`
- **Classes/Models**: `PascalCase` (e.g., `TranscriptSegment`, `UserIndex`)
- **Functions**: `snake_case` (e.g., `get_current_user`, `ingest_recording`)
- **Routes**: plural nouns (e.g., `/conversations`, `/topics`, `/commitments`)
- **Celery tasks**: verb + noun (e.g., `ingest_recording`, `extract_from_conversation`)
- **DB tables**: `snake_case` plural (e.g., `transcript_segments`, `topic_arc_conversation_links`)
- **Migrations**: `NNN_description.sql` (zero-padded 3 digits)
- **Tests**: `test_<module>.py`, classes `TestFeatureScenario`, methods `test_what_happens`
