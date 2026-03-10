"""
Integration tests: visibility timeout behaviour with Upstash Redis.

Requires:
  - UPSTASH_REDIS_URL set in .env
  - A running Celery worker:  celery -A tasks worker --loglevel=info

Run:
    pytest tests/test_timeout.py -v --timeout=60 -m integration

Background — what visibility timeout means for Redis/Upstash
-------------------------------------------------------------
Unlike AMQP (RabbitMQ), Redis does not have native message acknowledgement.
Celery emulates it using two lists per queue:

    <queue>          — the normal task queue
    unacked          — tasks that have been fetched but not yet acked

When a worker fetches a task:
  1. The task moves from <queue> → unacked.
  2. A separate heartbeat key is set with TTL = visibility_timeout.
  3. If the worker acks the task (success OR failure with acks_late=True),
     the task is removed from unacked.
  4. If the worker dies and the heartbeat key expires, the Celery Redis
     transport's "restore_at_shutdown" / periodic task-restore mechanism
     moves the task back to <queue> so another worker can pick it up.

Our configuration (celeryconfig.py):
  - visibility_timeout = 3600 s (1 hour)
  - task_acks_late = True        → ack happens AFTER task completes
  - task_reject_on_worker_lost = True → explicit reject on SIGTERM

Implication: tasks longer than visibility_timeout will appear to re-queue
(duplicate execution risk).  Set visibility_timeout > longest task duration.
"""
import time

import pytest

from tasks import app, slow_task

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def need_redis(require_redis):
    return require_redis


class TestVisibilityTimeout:
    def test_short_task_completes_within_timeout(self):
        """A task much shorter than visibility_timeout completes normally."""
        handle = slow_task.delay(duration_seconds=0.2)
        result = handle.get(timeout=15)
        assert result["completed"] is True

    def test_task_result_available_after_completion(self):
        """After a slow task completes, its result persists in the backend."""
        handle = slow_task.delay(duration_seconds=0.5)
        result = handle.get(timeout=15)

        # Re-fetch from result backend to confirm it was stored.
        stored = app.AsyncResult(handle.id)
        assert stored.get(timeout=5) == result

    def test_visibility_timeout_config_is_set(self):
        """Verify our celeryconfig sets visibility_timeout to at least 3600 s.

        This is a configuration sanity check — it does not require a live worker.
        """
        transport_opts = app.conf.broker_transport_options
        assert "visibility_timeout" in transport_opts, (
            "broker_transport_options must include visibility_timeout"
        )
        assert transport_opts["visibility_timeout"] >= 3600, (
            "visibility_timeout should be >= 3600 s to accommodate long tasks"
        )

    def test_acks_late_is_enabled(self):
        """Confirm task_acks_late=True — tasks are acked after completion."""
        assert app.conf.task_acks_late is True, (
            "task_acks_late must be True so tasks return to queue on worker crash"
        )

    def test_reject_on_worker_lost_is_enabled(self):
        """Confirm task_reject_on_worker_lost=True."""
        assert app.conf.task_reject_on_worker_lost is True

    def test_worker_prefetch_is_one(self):
        """Confirm worker_prefetch_multiplier=1 to limit unacked task exposure."""
        assert app.conf.worker_prefetch_multiplier == 1, (
            "worker_prefetch_multiplier=1 limits how many tasks are un-acked "
            "at once, reducing duplicate work after a worker crash"
        )

    # -----------------------------------------------------------------------
    # Documented limitation
    # -----------------------------------------------------------------------

    def test_visibility_timeout_expiry_causes_redelivery(self):
        """Demonstrate that tasks re-queue after visibility_timeout expires.

        SKIP in automated tests — requires setting visibility_timeout to a
        very small value (e.g. 5 s), dispatching a task longer than that,
        then killing the worker and observing redelivery.

        Steps to validate manually:
          1. Temporarily set visibility_timeout=5 in celeryconfig.py.
          2. Start worker: celery -A tasks worker --loglevel=info
          3. Dispatch: slow_task.delay(duration_seconds=30)
          4. Kill the worker (kill -9) after ~2 s (task is in-flight).
          5. Wait 5 s for visibility timeout to expire.
          6. Restart worker — observe the task being picked up again.

        Expected: task appears in worker logs twice (original + redelivered).
        This confirms Celery's Redis transport requeues tasks correctly.
        """
        pytest.skip(
            "Visibility timeout expiry test requires manual execution. "
            "See docstring for step-by-step instructions."
        )
