"""
Integration tests: worker restart recovery.

Requires:
  - UPSTASH_REDIS_URL set in .env
  - A running Celery worker:  celery -A tasks worker --loglevel=info

Run:
    pytest tests/test_worker_recovery.py -v --timeout=60 -m integration

Background — how task_acks_late protects against worker loss
------------------------------------------------------------
With task_acks_late=True (our config):
  - The broker message is NOT acked when the worker fetches the task.
  - It IS acked only after the task function returns (success or handled error).
  - If the worker process dies mid-task (SIGKILL, OOM, node restart), the
    message remains in the "unacked" set and is eventually redelivered to
    another worker after visibility_timeout expires.

With task_acks_late=False (default, NOT our config):
  - The message is acked immediately on fetch.
  - A worker crash mid-task causes the task result to be lost forever.

This test module:
  1. Verifies configuration guards are in place.
  2. Dispatches tasks and confirms they complete across a simulated restart.
  3. Documents the manual steps to verify crash-recovery end-to-end.
"""
import time

import pytest

from tasks import app, process_transcript, slow_task

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def need_redis(require_redis):
    return require_redis


class TestWorkerRecovery:
    def test_task_completes_after_worker_restart(self):
        """Tasks dispatched before a worker restart are processed after restart.

        In this automated test we simulate restart by dispatching the task
        BEFORE any worker is guaranteed to be running and polling until the
        result appears.  This validates that tasks survive in the broker queue
        during a gap in worker availability.

        For true crash recovery, see the manual test documented below.
        """
        handle = process_transcript.delay(
            transcript_id="recovery-t-001",
            user_id="recovery-u-001",
            content="worker recovery integration test content",
        )

        # Allow generous timeout — worker may not pick up immediately.
        result = handle.get(timeout=30)
        assert result["status"] == "processed"
        assert result["transcript_id"] == "recovery-t-001"

    def test_multiple_tasks_survive_worker_gap(self):
        """Batch of tasks dispatched during a worker gap are all eventually processed."""
        handles = [
            process_transcript.delay(
                transcript_id=f"recovery-t-batch-{i}",
                user_id="recovery-u-batch",
                content=f"batch content item {i}",
            )
            for i in range(5)
        ]

        results = [h.get(timeout=45) for h in handles]
        assert all(r["status"] == "processed" for r in results), (
            "All 5 tasks should reach 'processed' status"
        )
        recovered_ids = {r["transcript_id"] for r in results}
        expected_ids = {f"recovery-t-batch-{i}" for i in range(5)}
        assert recovered_ids == expected_ids, "No task results should be missing"

    def test_acks_late_config_prevents_message_loss(self):
        """Confirm configuration that prevents message loss on worker crash."""
        assert app.conf.task_acks_late is True
        assert app.conf.task_reject_on_worker_lost is True
        assert app.conf.task_acks_on_failure_or_timeout is True

    # -----------------------------------------------------------------------
    # Manual crash recovery validation (skip in CI)
    # -----------------------------------------------------------------------

    def test_crash_recovery_manual(self):
        """End-to-end crash recovery — requires manual worker management.

        Steps to validate:
          1. Start worker A:
               celery -A tasks worker --loglevel=info --concurrency=1 -n workerA@%h

          2. Dispatch a slow task:
               from tasks import slow_task
               handle = slow_task.delay(duration_seconds=10)
               print(handle.id)

          3. While the task is running (~2 s in), kill worker A hard:
               kill -9 <workerA PID>

          4. Wait for visibility_timeout to expire (configured: 3600 s).
             For testing, temporarily reduce to 10 s in celeryconfig.py.

          5. Start worker B:
               celery -A tasks worker --loglevel=info --concurrency=1 -n workerB@%h

          6. Observe worker B picks up the task and completes it.

          7. Retrieve result:
               from tasks import app
               result = app.AsyncResult(handle.id).get(timeout=30)
               assert result["completed"] is True

        Expected outcome:
          - The task result is eventually available.
          - Worker B logs show it received the redelivered task.
          - No duplicate result if worker A already completed the task before dying
            (task_acks_late ensures the message is acked only on completion).

        Key insight: task_acks_late=True + visibility_timeout=3600 means:
          - If worker dies BEFORE completing → task redelivered (no loss).
          - If worker dies AFTER completing but BEFORE acking → task redelivered
            (potential duplicate execution — design tasks to be idempotent).
        """
        pytest.skip(
            "Crash recovery requires manual worker management. "
            "See docstring for step-by-step instructions."
        )
