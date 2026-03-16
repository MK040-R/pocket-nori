"""
tests/conftest.py — Shared pytest fixtures for the Pocket Nori production test suite.

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
import socket
import ssl
from collections.abc import Generator
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib.parse import urlparse

import pytest
from celery import Celery
from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

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
    "OPENAI_API_KEY": "sk-openai-stub",
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
    config.addinivalue_line("markers", "unit: marks tests as unit tests (no external deps)")
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (requires real credentials)",
    )


# ---------------------------------------------------------------------------
# Supabase fixtures (integration — require real credentials + test_credentials.json)
# ---------------------------------------------------------------------------

_CREDENTIALS_PATH = (
    Path(__file__).parent.parent / "spikes" / "spike4_supabase_rls" / "test_credentials.json"
)


class UserCredentials(TypedDict):
    user_id: str
    access_token: str
    refresh_token: str


class TestCredentials(TypedDict):
    user_a: UserCredentials
    user_b: UserCredentials


@pytest.fixture(scope="session")
def supabase_url() -> str:
    """Read SUPABASE_URL from the environment; skip if not configured."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url or url == _STUB_ENV["SUPABASE_URL"]:
        pytest.skip("SUPABASE_URL not configured — skipping Supabase integration tests.")
    return url


@pytest.fixture(scope="session")
def supabase_service_key() -> str:
    """Read SUPABASE_SERVICE_KEY from the environment; skip if not configured."""
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not key or key == _STUB_ENV["SUPABASE_SERVICE_KEY"]:
        pytest.skip("SUPABASE_SERVICE_KEY not configured — skipping Supabase integration tests.")
    return key


def _load_test_credentials() -> TestCredentials:
    if not _CREDENTIALS_PATH.exists():
        pytest.skip(
            f"test_credentials.json not found at {_CREDENTIALS_PATH}. "
            "Run spikes/spike4_supabase_rls/setup_test_users.py first."
        )
    with _CREDENTIALS_PATH.open() as fh:
        payload = json.load(fh)
    return cast(TestCredentials, payload)


@pytest.fixture(scope="session")
def _supabase_credentials(supabase_url: str) -> TestCredentials:
    """Load test_credentials.json produced by setup_test_users.py."""
    return _load_test_credentials()


def _build_user_client(
    url: str,
    anon_key: str,
    access_token: str,
    refresh_token: str,
) -> Any:
    """Return a Supabase client authenticated as a specific user via JWT."""
    from supabase import create_client

    client = create_client(url, anon_key)
    client.auth.set_session(access_token, refresh_token)
    return client


@pytest.fixture(scope="session")
def service_client(supabase_url: str, supabase_service_key: str) -> Any:
    """Supabase client authenticated with the service role key.

    Bypasses RLS — represents server-side admin access.
    """
    from supabase import create_client

    return create_client(supabase_url, supabase_service_key)


@pytest.fixture(scope="session")
def user_a_client(supabase_url: str, _supabase_credentials: TestCredentials) -> Any:
    """Supabase client authenticated as test User A."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    creds = _supabase_credentials["user_a"]
    return _build_user_client(supabase_url, anon_key, creds["access_token"], creds["refresh_token"])


@pytest.fixture(scope="session")
def user_b_client(supabase_url: str, _supabase_credentials: TestCredentials) -> Any:
    """Supabase client authenticated as test User B."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    creds = _supabase_credentials["user_b"]
    return _build_user_client(supabase_url, anon_key, creds["access_token"], creds["refresh_token"])


# ---------------------------------------------------------------------------
# Celery fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def eager_extract() -> Generator[Celery]:
    """Eager-mode fixture scoped to the extract_from_conversation Celery app."""
    from src.celery_app import celery_app as extract_celery_app

    original_eager = bool(extract_celery_app.conf.task_always_eager)
    original_propagates = bool(extract_celery_app.conf.task_eager_propagates)
    original_backend = extract_celery_app.conf.result_backend
    original_cache = getattr(extract_celery_app.conf, "cache_backend", None)

    extract_celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache",
        cache_backend="memory",
    )
    yield extract_celery_app
    extract_celery_app.conf.update(
        task_always_eager=original_eager,
        task_eager_propagates=original_propagates,
        result_backend=original_backend,
    )
    if original_cache is not None:
        extract_celery_app.conf.update(cache_backend=original_cache)


@pytest.fixture
def eager_ingest() -> Generator[Celery]:
    """Eager-mode fixture scoped to the ingest_recording Celery app."""
    from src.workers.ingest import celery_app as ingest_celery_app

    original_eager = bool(ingest_celery_app.conf.task_always_eager)
    original_propagates = bool(ingest_celery_app.conf.task_eager_propagates)
    original_backend = ingest_celery_app.conf.result_backend
    original_cache = getattr(ingest_celery_app.conf, "cache_backend", None)

    ingest_celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache",
        cache_backend="memory",
    )
    yield ingest_celery_app
    ingest_celery_app.conf.update(
        task_always_eager=original_eager,
        task_eager_propagates=original_propagates,
        result_backend=original_backend,
    )
    if original_cache is not None:
        ingest_celery_app.conf.update(cache_backend=original_cache)


@pytest.fixture
def eager_app() -> Generator[Celery]:
    """Return the production Celery app configured for synchronous (eager)
    execution.

    Tasks run inline in the calling process — no worker, no broker, no
    network.  Results are returned directly from .delay()/.apply_async().
    """
    from src.workers.tasks import celery_app

    original_task_always_eager = bool(celery_app.conf.task_always_eager)
    original_task_eager_propagates = bool(celery_app.conf.task_eager_propagates)
    original_result_backend = celery_app.conf.result_backend
    original_cache_backend = getattr(celery_app.conf, "cache_backend", None)

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,  # surface exceptions immediately in tests
        result_backend="cache",
        cache_backend="memory",
    )
    yield celery_app
    # Restore to normal async mode after each test.
    celery_app.conf.update(
        task_always_eager=original_task_always_eager,
        task_eager_propagates=original_task_eager_propagates,
        result_backend=original_result_backend,
    )
    if original_cache_backend is not None:
        celery_app.conf.update(cache_backend=original_cache_backend)


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

    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 6379
    if not host:
        pytest.skip("UPSTASH_REDIS_URL is invalid — skipping Celery integration tests.")

    # Integration tests should not fail on machines/environments that cannot
    # reach external Redis endpoints (for example, network-restricted sandboxes).
    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError:
        pytest.skip(
            "UPSTASH_REDIS_URL is set but unreachable from this environment — "
            "skipping Celery integration tests."
        )

    # Validate end-to-end broker connectivity before running integration tests.
    # A plain TCP connect can pass while TLS verification fails during the first
    # actual Redis command.
    try:
        Redis.from_url(
            url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        ).ping()
    except ssl.SSLCertVerificationError:
        pytest.skip(
            "UPSTASH_REDIS_URL is reachable but TLS certificate verification "
            "fails in this environment — skipping Celery integration tests."
        )
    except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
        reason = str(exc).lower()
        if "certificate verify failed" in reason:
            pytest.skip(
                "UPSTASH_REDIS_URL is reachable but TLS certificate verification "
                "fails in this environment — skipping Celery integration tests."
            )
        if "invalid password" in reason or "authentication" in reason or "wrongpass" in reason:
            pytest.fail(f"UPSTASH_REDIS_URL appears misconfigured (auth failed): {exc}")
        pytest.skip(
            "UPSTASH_REDIS_URL is set but Redis ping failed from this environment — "
            "skipping Celery integration tests."
        )

    return url
