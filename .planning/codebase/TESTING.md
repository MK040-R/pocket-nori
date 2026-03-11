# Testing

## Framework

**pytest 8.3.5+** with custom markers and conftest-based fixture injection.

```bash
# Run all unit tests (no credentials needed)
python -m pytest tests/ -v -m unit

# Run integration tests (requires live credentials)
python -m pytest tests/ -v -m integration --timeout=30

# Run specific test file
python -m pytest tests/test_ingest.py -v
```

## Test Markers

| Marker | When runs | Requirements |
|---|---|---|
| `@pytest.mark.unit` | Always | No external deps — stubs injected via conftest |
| `@pytest.mark.integration` | Explicitly via `-m integration` | Real Supabase + Redis credentials in `.env` |

## File Structure

```
tests/
├── conftest.py            # Shared fixtures — Celery eager mode, Supabase clients, env stubs
├── test_workers.py        # process_transcript + generate_brief tasks (unit + integration)
├── test_ingest.py         # ingest_recording task (parsing, persistence, idempotency)
├── test_extract.py        # extract_from_conversation task (LLM extraction logic)
├── test_search.py         # POST /search endpoint (pgvector cosine similarity)
├── test_topics.py         # GET /topics, GET /topics/{id} endpoints
├── test_commitments.py    # GET /commitments, PATCH /commitments/{id}
└── test_rls_isolation.py  # Cross-user data isolation (Supabase RLS — integration only)
```

## conftest.py Patterns

### Environment Stubbing
All required env vars are stubbed at conftest import time (before any `src.*` module loads), so unit tests run without credentials:

```python
_STUB_ENV = {
    "SUPABASE_URL": "https://stub.supabase.co",
    "ANTHROPIC_API_KEY": "sk-ant-stub",
    # ...
}
for _key, _val in _STUB_ENV.items():
    if not os.environ.get(_key):
        os.environ[_key] = _val
```

### Celery Eager Mode
Tasks run synchronously in tests — no broker, no worker, no network:

```python
@pytest.fixture
def eager_app() -> Generator[Celery]:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache",
        cache_backend="memory",
    )
    yield celery_app
    # restore original config after each test
```

Per-worker fixtures available: `eager_extract`, `eager_ingest`, `eager_app`.

### FastAPI Dependency Mocking
**Critical:** FastAPI dependencies CANNOT be patched with `unittest.mock.patch`. Use `app.dependency_overrides` instead:

```python
# WRONG — does not work with FastAPI:
with patch("src.api.deps.get_current_user", return_value=mock_user):
    ...

# CORRECT:
from src.main import app
from src.api.deps import get_current_user

app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-test", "jwt": "tok"}
# test here
app.dependency_overrides.clear()
```

### Supabase Fixtures (integration only)
```python
user_a_client  # Supabase client authenticated as test User A
user_b_client  # Supabase client authenticated as test User B
service_client # Service-role client (bypasses RLS — admin use in tests only)
```
These fixtures call `pytest.skip()` if credentials aren't configured.

### Redis Guard
```python
require_redis  # Skips integration tests if UPSTASH_REDIS_URL not reachable
```

## Test Structure Conventions

Tests are class-based, grouped by feature and scenario:

```python
@pytest.mark.unit
class TestIngestRecordingUnit:
    def test_parses_google_meet_transcript(self, eager_ingest) -> None: ...
    def test_skips_duplicate_drive_file_id(self, eager_ingest) -> None: ...
    def test_raises_on_missing_required_args(self, eager_ingest) -> None: ...

@pytest.mark.integration
class TestIngestRecordingIntegration:
    def test_full_pipeline_persists_conversation(self, ...) -> None: ...
```

## What's Tested

| Area | Coverage | Notes |
|---|---|---|
| Celery task arg validation | ✓ Unit | All tasks validate required args, raise ValueError |
| Celery task result shape | ✓ Unit | Return dict keys always echoed back |
| Transcript parsing | ✓ Unit | Google Meet + Gemini Notes format, edge cases |
| LLM extraction | ✓ Unit | Mocked Anthropic client |
| pgvector search | ✓ Unit | Mocked psycopg2 connection |
| API route auth | ✓ Unit | via `app.dependency_overrides` |
| RLS cross-user isolation | ✓ Integration | User A cannot read User B's rows |
| Celery broker dispatch | ✓ Integration | Requires UPSTASH_REDIS_URL |

## CI

GitHub Actions (`ci.yml`) runs:
1. `ruff check` — lint
2. `mypy` — type checking
3. `pytest -m unit` — all unit tests (no credentials needed in CI)

RLS isolation tests are the only integration tests required on every PR.

## Running Tests Locally

```bash
source .venv/bin/activate

# Unit only (fast, no credentials needed)
python -m pytest tests/ -v -m unit

# With coverage
python -m pytest tests/ -v -m unit --cov=src --cov-report=html

# Single file
python -m pytest tests/test_ingest.py -v

# Full QA report
python scripts/qa_check.py
```
