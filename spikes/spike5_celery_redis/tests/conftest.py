"""
Shared pytest fixtures for Spike 5 integration and unit tests.

Integration tests require UPSTASH_REDIS_URL to be set in the environment
(via a .env file in the spike root).  Unit tests use ALWAYS_EAGER mode and
never touch the network.
"""
import os

import pytest

from tasks import app as celery_app


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a live Redis/Upstash connection",
    )


# ---------------------------------------------------------------------------
# Unit-test fixture: synchronous eager execution, no broker required
# ---------------------------------------------------------------------------

@pytest.fixture
def eager_app():
    """Return the Celery app configured for synchronous (eager) execution.

    Tasks run inline in the calling process — no worker, no broker, no network.
    Results are returned directly from .delay()/.apply_async() calls.
    """
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,  # surface exceptions immediately in tests
    )
    yield celery_app
    # Restore to normal async mode after each test.
    celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
    )


# ---------------------------------------------------------------------------
# Integration-test fixture: guard against missing credentials
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def require_redis():
    """Skip the entire test module if UPSTASH_REDIS_URL is not configured."""
    url = os.environ.get("UPSTASH_REDIS_URL", "").strip()
    if not url or url.startswith("rediss://:your_password"):
        pytest.skip(
            "UPSTASH_REDIS_URL not set — skipping integration tests. "
            "See FAR-67 to provision Upstash credentials."
        )
    return url
