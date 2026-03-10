"""
Integration tests: task dispatch and result retrieval via Upstash Redis.

Requires:
  - UPSTASH_REDIS_URL set in .env
  - A running Celery worker:  celery -A tasks worker --loglevel=info

Run:
    pytest tests/test_dispatch.py -v --timeout=30 -m integration
"""
import time

import pytest

from tasks import process_transcript

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def need_redis(require_redis):
    """Auto-use fixture: skip all tests in this module if Redis is unavailable."""
    return require_redis


class TestTaskDispatch:
    def test_dispatch_and_retrieve_result(self):
        """Dispatch a transcript task and verify the result round-trips correctly."""
        async_result = process_transcript.delay(
            transcript_id="integ-t-001",
            user_id="integ-u-001",
            content="The quick brown fox jumps over the lazy dog",
        )

        # Block until result is ready (worker must be running).
        result = async_result.get(timeout=15)

        assert result["transcript_id"] == "integ-t-001"
        assert result["user_id"] == "integ-u-001"
        assert result["word_count"] == 9
        assert result["status"] == "processed"

    def test_result_is_stored_in_backend(self):
        """Verify that the result can be retrieved a second time from the backend."""
        async_result = process_transcript.delay(
            transcript_id="integ-t-002",
            user_id="integ-u-002",
            content="Hello world",
        )

        result_first = async_result.get(timeout=15)

        # Re-fetch by task ID — result should still be in the backend.
        from tasks import app
        stored = app.AsyncResult(async_result.id)
        result_second = stored.get(timeout=5)

        assert result_first == result_second

    def test_multiple_tasks_dispatched_concurrently(self):
        """Dispatch several tasks and collect all results."""
        payloads = [
            ("integ-t-batch-1", "integ-u-batch", "one two three"),
            ("integ-t-batch-2", "integ-u-batch", "alpha beta gamma delta"),
            ("integ-t-batch-3", "integ-u-batch", "single"),
        ]
        expected_word_counts = [3, 4, 1]

        results_handles = [
            process_transcript.delay(tid, uid, content)
            for tid, uid, content in payloads
        ]

        results = [r.get(timeout=30) for r in results_handles]

        for i, (result, expected_wc) in enumerate(zip(results, expected_word_counts)):
            assert result["word_count"] == expected_wc, (
                f"Batch task {i} word count mismatch"
            )
            assert result["status"] == "processed"

    def test_task_state_is_success_after_completion(self):
        """Verify Celery reports SUCCESS state after a task completes."""
        handle = process_transcript.delay(
            transcript_id="integ-t-003",
            user_id="integ-u-003",
            content="state check",
        )
        handle.get(timeout=15)
        assert handle.state == "SUCCESS"

    def test_large_content_round_trips(self):
        """Ensure large content is serialised and deserialised without truncation."""
        large_content = " ".join(f"word{i}" for i in range(1000))
        handle = process_transcript.delay(
            transcript_id="integ-t-large",
            user_id="integ-u-large",
            content=large_content,
        )
        result = handle.get(timeout=30)
        assert result["word_count"] == 1000
