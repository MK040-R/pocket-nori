"""
tests/test_workers.py — Production test suite for Celery task logic.

Promoted from spikes/spike5_celery_redis/tests/test_tasks_unit.py.

Unit tests use eager (synchronous) execution and require no broker or
network access.  Integration tests require UPSTASH_REDIS_URL to be set.

Run unit tests only:
    pytest tests/test_workers.py -v -m unit

Run integration tests (requires Upstash credentials):
    pytest tests/test_workers.py -v -m integration --timeout=30
"""

from typing import Any

import pytest

from src.workers.tasks import generate_brief, process_transcript

# ---------------------------------------------------------------------------
# process_transcript — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessTranscriptUnit:
    """Verifies process_transcript logic using eager (synchronous) Celery."""

    def test_returns_expected_fields(self, eager_app: Any) -> None:
        result = process_transcript.delay(
            transcript_id="t-001",
            user_id="u-abc",
            raw_text="Hello world this is a test transcript",
        ).get()

        assert result["transcript_id"] == "t-001"
        assert result["user_id"] == "u-abc"
        assert result["status"] == "queued"

    def test_raises_on_missing_transcript_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="transcript_id"):
            process_transcript.delay(
                transcript_id="",
                user_id="u-abc",
                raw_text="some content",
            ).get()

    def test_raises_on_missing_user_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="user_id"):
            process_transcript.delay(
                transcript_id="t-003",
                user_id="",
                raw_text="some content",
            ).get()

    def test_user_id_echoed_in_result(self, eager_app: Any) -> None:
        """Result always echoes back user_id — callers can assert ownership."""
        for uid in ("user-A", "user-B", "user-C"):
            result = process_transcript.delay(
                transcript_id="t-shared",
                user_id=uid,
                raw_text="shared content",
            ).get()
            assert result["user_id"] == uid

    def test_transcript_id_echoed_in_result(self, eager_app: Any) -> None:
        result = process_transcript.delay(
            transcript_id="t-xyz",
            user_id="u-abc",
            raw_text="content",
        ).get()
        assert result["transcript_id"] == "t-xyz"


# ---------------------------------------------------------------------------
# generate_brief — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateBriefUnit:
    """Verifies generate_brief logic using eager (synchronous) Celery."""

    def test_returns_expected_fields(self, eager_app: Any) -> None:
        result = generate_brief.delay(
            conversation_id="c-001",
            user_id="u-abc",
        ).get()

        assert result["conversation_id"] == "c-001"
        assert result["user_id"] == "u-abc"
        assert result["status"] == "queued"

    def test_raises_on_missing_conversation_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="conversation_id"):
            generate_brief.delay(
                conversation_id="",
                user_id="u-abc",
            ).get()

    def test_raises_on_missing_user_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="user_id"):
            generate_brief.delay(
                conversation_id="c-001",
                user_id="",
            ).get()

    def test_user_id_echoed_in_result(self, eager_app: Any) -> None:
        """Result always echoes back user_id — callers can assert ownership."""
        for uid in ("user-A", "user-B", "user-C"):
            result = generate_brief.delay(
                conversation_id="c-shared",
                user_id=uid,
            ).get()
            assert result["user_id"] == uid

    def test_conversation_id_echoed_in_result(self, eager_app: Any) -> None:
        result = generate_brief.delay(
            conversation_id="c-xyz",
            user_id="u-abc",
        ).get()
        assert result["conversation_id"] == "c-xyz"


# ---------------------------------------------------------------------------
# Integration tests — require a live Redis connection
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProcessTranscriptIntegration:
    """Dispatch process_transcript to a real Celery worker via Upstash Redis."""

    def test_task_dispatches_successfully(self, require_redis: str) -> None:
        """Verify the task can be enqueued without raising.

        Full end-to-end result retrieval requires a running worker process;
        this test only verifies that dispatch does not error.
        """
        async_result = process_transcript.apply_async(
            kwargs={
                "transcript_id": "t-integration-001",
                "user_id": "u-integration",
                "raw_text": "Integration test transcript content.",
            }
        )
        assert async_result.id is not None, "Task dispatch should return a task ID"


@pytest.mark.integration
class TestGenerateBriefIntegration:
    """Dispatch generate_brief to a real Celery worker via Upstash Redis."""

    def test_task_dispatches_successfully(self, require_redis: str) -> None:
        """Verify the task can be enqueued without raising."""
        async_result = generate_brief.apply_async(
            kwargs={
                "conversation_id": "c-integration-001",
                "user_id": "u-integration",
            }
        )
        assert async_result.id is not None, "Task dispatch should return a task ID"
