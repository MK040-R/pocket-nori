"""
Unit tests for Celery tasks — no Redis, no network, no worker process.

Uses ALWAYS_EAGER mode: tasks run synchronously in the calling process.
These tests verify task logic and input validation in isolation.
"""
import pytest

from tasks import failing_task, process_transcript, slow_task


# ---------------------------------------------------------------------------
# process_transcript
# ---------------------------------------------------------------------------

class TestProcessTranscriptUnit:
    def test_returns_expected_fields(self, eager_app):
        result = process_transcript.delay(
            transcript_id="t-001",
            user_id="u-abc",
            content="Hello world this is a test transcript",
        ).get()

        assert result["transcript_id"] == "t-001"
        assert result["user_id"] == "u-abc"
        assert result["word_count"] == 7
        assert result["status"] == "processed"

    def test_word_count_empty_content(self, eager_app):
        result = process_transcript.delay(
            transcript_id="t-002",
            user_id="u-abc",
            content="",
        ).get()
        # "".split() == [] → word_count 0
        assert result["word_count"] == 0

    def test_raises_on_missing_transcript_id(self, eager_app):
        with pytest.raises(ValueError, match="transcript_id"):
            process_transcript.delay(
                transcript_id="",
                user_id="u-abc",
                content="some content",
            ).get()

    def test_raises_on_missing_user_id(self, eager_app):
        with pytest.raises(ValueError, match="user_id"):
            process_transcript.delay(
                transcript_id="t-003",
                user_id="",
                content="some content",
            ).get()

    def test_user_isolation_reflected_in_result(self, eager_app):
        """Result always echoes back user_id — callers can assert ownership."""
        for uid in ("user-A", "user-B", "user-C"):
            result = process_transcript.delay(
                transcript_id="t-shared",
                user_id=uid,
                content="shared content",
            ).get()
            assert result["user_id"] == uid


# ---------------------------------------------------------------------------
# failing_task
# ---------------------------------------------------------------------------

class TestFailingTaskUnit:
    def test_succeeds_when_should_fail_false(self, eager_app):
        result = failing_task.delay(should_fail=False).get()
        assert result["success"] is True

    def test_raises_on_first_attempt_in_eager_mode(self, eager_app):
        """In eager mode retries raise immediately — verify the error surfaces."""
        with pytest.raises(RuntimeError, match="Intentional first-attempt failure"):
            failing_task.delay(should_fail=True).get()


# ---------------------------------------------------------------------------
# slow_task
# ---------------------------------------------------------------------------

class TestSlowTaskUnit:
    def test_returns_completed_true(self, eager_app):
        result = slow_task.delay(duration_seconds=0.0).get()
        assert result["completed"] is True
        assert result["duration"] == 0.0

    def test_duration_reflected_in_result(self, eager_app):
        result = slow_task.delay(duration_seconds=0.05).get()
        assert result["duration"] == 0.05
