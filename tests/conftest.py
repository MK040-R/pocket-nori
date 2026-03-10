"""
tests/conftest.py — Shared pytest fixtures for the Farz production test suite.

Merges fixtures from:
  - spikes/spike4_supabase_rls  (Supabase / RLS fixtures)
  - spikes/spike5_celery_redis  (Celery eager-mode + Redis guard fixtures)

Integration tests require real credentials in .env.
Unit tests run entirely offline — no credentials needed.

STUB INJECTION
--------------
Required env vars are stubbed at module-import time (before pytest collects
test files and triggers src.* imports).  Real .env values take precedence —
stubs only fill gaps so that pydantic-settings' Settings() can instantiate
without real credentials during offline unit-test runs.
"""

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env first so real values take precedence over stubs.
load_dotenv()

# ---------------------------------------------------------------------------
# Stub environment — set before any src.* module is imported.
# Module-level import in test files (e.g. test_workers.py) runs at collection
# time, before any fixture can inject values.  We therefore set stubs here,
# at conftest import time, which pytest guarantees happens first.
# ---------------------------------------------------------------------------

_STUB_ENV: dict[str, str] = {
    "SUPABASE_URL": "https://stub.supabase.co",
    "SUPABASE_ANON_KEY": "stub-anon-key",
    "SUPABASE_SERVICE_KEY": "stub-service-key",
    "DATABASE_URL": "postgresql://stub:stub@localhost/stub",
    "ANTHROPIC_API_KEY": "sk-ant-stub",
    "UPSTASH_REDIS_URL": "rediss://:stub@stub.upstash.io:6379",
    "DEEPGRAM_API_KEY": "stub-deepgram-key",
    "GOOGLE_CLIENT_ID": "stub-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "stub-client-secret",
    "SECRET_KEY": "0" * 64,
}

for _key, _val in _STUB_ENV.items():
    if not os.environ.get(_key):
        os.environ[_key] = _val


# ---------------------------------------------------------------------------
# Pytest marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (no external deps)"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (requires real credentials)",
    )


# ---------------------------------------------------------------------------
# Supabase fixtures (integration — require real credentials + test_credentials.json)
# ---------------------------------------------------------------------------

_CREDENTIALS_PATH = (
    Path(__file__).parent.parent
    / "spikes"
    / "spike4_supabase_rls"
    / "test_credentials.json"
)


@pytest.fixture(scope="session")
def supabase_url() -> str:
    """Read SUPABASE_URL from the environment; skip if not configured."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url or url == _STUB_ENV["SUPABASE_URL"]:
        pytest.skip(
            "SUPABASE_URL not configured — skipping Supabase integration tests."
        )
    return url


@pytest.fixture(scope="session")
def supabase_service_key() -> str:
    """Read SUPABASE_SERVICE_KEY from the environment; skip if not configured."""
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not key or key == _STUB_ENV["SUPABASE_SERVICE_KEY"]:
        pytest.skip(
            "SUPABASE_SERVICE_KEY not configured — skipping Supabase integration tests."
        )
    return key


def _load_test_credentials() -> dict:
    if not _CREDENTIALS_PATH.exists():
        pytest.skip(
            f"test_credentials.json not found at {_CREDENTIALS_PATH}. "
            "Run spikes/spike4_supabase_rls/setup_test_users.py first."
        )
    with _CREDENTIALS_PATH.open() as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def _supabase_credentials(supabase_url: str) -> dict:
    """Load test_credentials.json produced by setup_test_users.py."""
    return _load_test_credentials()


def _build_user_client(
    url: str,
    anon_key: str,
    access_token: str,
    refresh_token: str,
):
    """Return a Supabase client authenticated as a specific user via JWT."""
    from supabase import create_client  # noqa: PLC0415

    client = create_client(url, anon_key)
    client.auth.set_session(access_token, refresh_token)
    return client


@pytest.fixture(scope="session")
def service_client(supabase_url: str, supabase_service_key: str):
    """Supabase client authenticated with the service role key.

    Bypasses RLS — represents server-side admin access.
    """
    from supabase import create_client  # noqa: PLC0415

    return create_client(supabase_url, supabase_service_key)


@pytest.fixture(scope="session")
def user_a_client(supabase_url: str, _supabase_credentials: dict):
    """Supabase client authenticated as test User A."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    creds = _supabase_credentials["user_a"]
    return _build_user_client(
        supabase_url, anon_key, creds["access_token"], creds["refresh_token"]
    )


@pytest.fixture(scope="session")
def user_b_client(supabase_url: str, _supabase_credentials: dict):
    """Supabase client authenticated as test User B."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    creds = _supabase_credentials["user_b"]
    return _build_user_client(
        supabase_url, anon_key, creds["access_token"], creds["refresh_token"]
    )


# ---------------------------------------------------------------------------
# Celery fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def eager_app():
    """Return the production Celery app configured for synchronous (eager)
    execution.

    Tasks run inline in the calling process — no worker, no broker, no
    network.  Results are returned directly from .delay()/.apply_async().
    """
    from src.workers.tasks import celery_app  # noqa: PLC0415

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,  # surface exceptions immediately in tests
        result_backend="cache",
        cache_backend="memory",
    )
    yield celery_app
    # Restore to normal async mode after each test.
    celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
        result_backend=celery_app.conf.result_backend,
    )


@pytest.fixture(scope="session")
def require_redis() -> str:
    """Skip integration tests if UPSTASH_REDIS_URL is not configured."""
    url = os.environ.get("UPSTASH_REDIS_URL", "").strip()
    if (
        not url
        or url.startswith("rediss://:your_password")
        or url == _STUB_ENV["UPSTASH_REDIS_URL"]
    ):
        pytest.skip(
            "UPSTASH_REDIS_URL not set — skipping Celery integration tests. "
            "See FAR-67 to provision Upstash credentials."
        )
    return url
