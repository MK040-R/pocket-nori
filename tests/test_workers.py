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

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.calendar_client import CalendarEvent
from src.workers.tasks import generate_brief, process_transcript, schedule_recurring_briefs

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

    @staticmethod
    def _make_db_mock(
        *,
        conversation_exists: bool = True,
        include_context: bool = True,
    ) -> MagicMock:
        db = MagicMock()

        conversations_table = MagicMock()
        conversations_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [
                {
                    "id": "c-001",
                    "title": "Weekly Sync",
                    "meeting_date": "2026-03-11T10:00:00+00:00",
                    "calendar_event_id": "evt-001",
                }
            ]
            if conversation_exists
            else []
        )

        topics_table = MagicMock()

        def _topics_select_router(columns: str) -> MagicMock:
            if columns == "id, label":
                query = MagicMock()
                query.eq.return_value.eq.return_value.execute.return_value.data = (
                    [{"id": "topic-1", "label": "Q2 Launch"}] if include_context else []
                )
                return query

            query = MagicMock()
            query.eq.return_value.in_.return_value.execute.return_value.data = (
                [{"conversation_id": "c-001"}] if include_context else []
            )
            return query

        topics_table.select.side_effect = _topics_select_router

        topic_arcs_table = MagicMock()
        topic_arcs_table.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = (
            [
                {
                    "id": "arc-1",
                    "topic_id": "topic-1",
                    "summary": "Launch blockers were reviewed.",
                    "trend": "stable",
                    "created_at": "2026-03-10T10:00:00+00:00",
                }
            ]
            if include_context
            else []
        )

        commitments_table = MagicMock()
        commitments_table.select.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = (
            [
                {
                    "id": "commit-1",
                    "text": "Murali will publish the launch brief.",
                    "owner": "Murali",
                    "due_date": "2026-03-12",
                    "conversation_id": "c-001",
                }
            ]
            if include_context
            else []
        )

        linked_items_table = MagicMock()
        linked_items_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [{"connection_id": "conn-1"}] if include_context else []
        )

        connections_table = MagicMock()
        connections_table.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = (
            [
                {
                    "id": "conn-1",
                    "label": "Shared launch thread",
                    "summary": "Product and GTM syncs both discussed launch risks.",
                    "linked_type": "conversation",
                    "created_at": "2026-03-10T11:00:00+00:00",
                }
            ]
            if include_context
            else []
        )

        briefs_table = MagicMock()
        briefs_table.insert.return_value.execute.return_value.data = [{"id": "brief-1"}]

        brief_topic_links_table = MagicMock()
        brief_topic_links_table.insert.return_value.execute.return_value = MagicMock()

        brief_commitment_links_table = MagicMock()
        brief_commitment_links_table.insert.return_value.execute.return_value = MagicMock()

        brief_connection_links_table = MagicMock()
        brief_connection_links_table.insert.return_value.execute.return_value = MagicMock()

        def _table_router(name: str) -> MagicMock:
            if name == "conversations":
                return conversations_table
            if name == "topics":
                return topics_table
            if name == "topic_arcs":
                return topic_arcs_table
            if name == "commitments":
                return commitments_table
            if name == "connection_linked_items":
                return linked_items_table
            if name == "connections":
                return connections_table
            if name == "briefs":
                return briefs_table
            if name == "brief_topic_arc_links":
                return brief_topic_links_table
            if name == "brief_commitment_links":
                return brief_commitment_links_table
            if name == "brief_connection_links":
                return brief_connection_links_table
            raise AssertionError(f"Unexpected table lookup: {name}")

        db.table.side_effect = _table_router
        return db

    def test_returns_expected_fields(self, eager_app: Any) -> None:
        db = self._make_db_mock()
        with (
            patch("src.workers.tasks.get_client", return_value=db),
            patch(
                "src.workers.tasks.llm_client.generate_brief",
                return_value="Generated brief content.",
            ) as mock_generate,
        ):
            result = cast(
                dict[str, Any],
                generate_brief.delay(
                    conversation_id="c-001",
                    user_id="u-abc",
                    user_jwt="jwt-token",
                ).get(),
            )

        mock_generate.assert_called_once()
        assert result["brief_id"] == "brief-1"
        assert result["conversation_id"] == "c-001"
        assert result["user_id"] == "u-abc"
        assert result["status"] == "generated"
        assert result["topic_arc_count"] == 1
        assert result["commitment_count"] == 1
        assert result["connection_count"] == 1

    def test_raises_on_missing_conversation_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="conversation_id"):
            generate_brief.delay(
                conversation_id="",
                user_id="u-abc",
                user_jwt="jwt-token",
            ).get()

    def test_raises_on_missing_user_id(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="user_id"):
            generate_brief.delay(
                conversation_id="c-001",
                user_id="",
                user_jwt="jwt-token",
            ).get()

    def test_raises_on_missing_user_jwt(self, eager_app: Any) -> None:
        with pytest.raises(ValueError, match="user_jwt"):
            generate_brief.delay(
                conversation_id="c-001",
                user_id="u-abc",
                user_jwt="",
            ).get()

    def test_raises_when_conversation_not_owned_by_user(self, eager_app: Any) -> None:
        db = self._make_db_mock(conversation_exists=False)
        with patch("src.workers.tasks.get_client", return_value=db):
            with pytest.raises(RuntimeError, match="not found"):
                generate_brief.delay(
                    conversation_id="c-001",
                    user_id="u-abc",
                    user_jwt="jwt-token",
                ).get()

    def test_skips_llm_when_no_context(self, eager_app: Any) -> None:
        db = self._make_db_mock(include_context=False)
        with (
            patch("src.workers.tasks.get_client", return_value=db),
            patch("src.workers.tasks.llm_client.generate_brief") as mock_generate,
        ):
            result = cast(
                dict[str, Any],
                generate_brief.delay(
                    conversation_id="c-001",
                    user_id="u-abc",
                    user_jwt="jwt-token",
                ).get(),
            )

        mock_generate.assert_not_called()
        assert result["status"] == "generated"
        assert result["topic_arc_count"] == 0
        assert result["commitment_count"] == 0
        assert result["connection_count"] == 0


@pytest.mark.unit
class TestScheduleRecurringBriefsUnit:
    @staticmethod
    def _make_db_mock(*, existing_brief_rows: list[dict[str, Any]] | None = None) -> MagicMock:
        existing_brief_rows = existing_brief_rows or []
        db = MagicMock()

        conversations_table = MagicMock()
        conversations_table.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
            {
                "id": "conv-anchor",
                "title": "Weekly Sync",
                "meeting_date": "2026-03-10T10:00:00+00:00",
                "calendar_event_id": "evt-past",
            }
        ]

        briefs_table = MagicMock()
        briefs_table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = existing_brief_rows

        def _table_router(name: str) -> MagicMock:
            if name == "conversations":
                return conversations_table
            if name == "briefs":
                return briefs_table
            raise AssertionError(f"Unexpected table lookup: {name}")

        db.table.side_effect = _table_router
        return db

    def test_schedules_brief_for_recurring_event_with_history(self, eager_app: Any) -> None:
        now = datetime.now(tz=UTC)
        upcoming_event = CalendarEvent(
            event_id="evt-upcoming",
            title="Weekly Sync",
            start_time=now + timedelta(minutes=30),
            recurring_event_id="series-1",
            is_recurring=True,
            attendees=[],
        )
        past_event = CalendarEvent(
            event_id="evt-past",
            title="Weekly Sync",
            start_time=now - timedelta(days=7),
            recurring_event_id="series-1",
            is_recurring=True,
            attendees=[],
        )

        db = self._make_db_mock()
        with (
            patch("src.workers.tasks.get_client", return_value=db),
            patch("src.workers.tasks.refresh_access_token_sync", return_value="access-token"),
            patch(
                "src.workers.tasks.list_calendar_events_sync",
                side_effect=[[upcoming_event], [past_event]],
            ),
            patch("src.workers.tasks.generate_brief.apply_async") as mock_apply_async,
        ):
            result = cast(
                dict[str, Any],
                schedule_recurring_briefs.delay(
                    user_id="u-abc",
                    user_jwt="jwt-token",
                    google_refresh_token="refresh-token",
                ).get(),
            )

        mock_apply_async.assert_called_once()
        assert result["status"] == "scheduled"
        assert result["scheduled_count"] == 1
        assert result["skipped_missing_history"] == 0

    def test_skips_when_recurring_series_has_no_prior_indexed_session(self, eager_app: Any) -> None:
        now = datetime.now(tz=UTC)
        upcoming_event = CalendarEvent(
            event_id="evt-upcoming",
            title="Weekly Sync",
            start_time=now + timedelta(minutes=30),
            recurring_event_id="series-1",
            is_recurring=True,
            attendees=[],
        )

        db = self._make_db_mock()
        with (
            patch("src.workers.tasks.get_client", return_value=db),
            patch("src.workers.tasks.refresh_access_token_sync", return_value="access-token"),
            patch(
                "src.workers.tasks.list_calendar_events_sync",
                side_effect=[[upcoming_event], []],
            ),
            patch("src.workers.tasks.generate_brief.apply_async") as mock_apply_async,
        ):
            result = cast(
                dict[str, Any],
                schedule_recurring_briefs.delay(
                    user_id="u-abc",
                    user_jwt="jwt-token",
                    google_refresh_token="refresh-token",
                ).get(),
            )

        mock_apply_async.assert_not_called()
        assert result["scheduled_count"] == 0
        assert result["skipped_missing_history"] == 1


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
                "user_jwt": "jwt-integration",
            }
        )
        assert async_result.id is not None, "Task dispatch should return a task ID"
