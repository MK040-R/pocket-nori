"""
tests/test_calendar.py — Unit tests for calendar today briefing endpoint.

Covers:
- Google Calendar event fetch integration in GET /calendar/today
- conversation ↔ calendar_event_id linking by meeting time
- open commitments enrichment with conversation titles
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.calendar_client import CalendarEvent
from src.main import app

client = TestClient(app)

_FAKE_USER_ID = "user-calendar-test"

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "calendar-test@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db_mock(
    *,
    user_index_row: dict[str, Any],
    unlinked_conversations: list[dict[str, Any]] | None = None,
    commitments: list[dict[str, Any]] | None = None,
    conversation_titles: list[dict[str, Any]] | None = None,
    recent_activity_rows: list[dict[str, Any]] | None = None,
    connection_rows: list[dict[str, Any]] | None = None,
    connection_links: list[dict[str, Any]] | None = None,
    topic_rows: list[dict[str, Any]] | None = None,
    related_conversation_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    user_index = MagicMock()
    user_index.select.return_value.eq.return_value.execute.return_value.data = [user_index_row]
    user_index.update.return_value.eq.return_value.execute.return_value = MagicMock()

    commitment_rows = commitments or []
    commitments_table = MagicMock()
    (
        commitments_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = commitment_rows

    connections_table = MagicMock()
    (
        connections_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = connection_rows or []

    connection_links_table = MagicMock()
    (
        connection_links_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data
    ) = connection_links or []

    topics_table = MagicMock()
    topics_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = (
        topic_rows or []
    )

    conversations_table = MagicMock()

    unlinked_rows = unlinked_conversations or []
    title_rows = conversation_titles or []
    activity_rows = recent_activity_rows or []
    connection_conversations = related_conversation_rows or []

    def _select_router(columns: str) -> MagicMock:
        if columns == "id, meeting_date, calendar_event_id":
            query = MagicMock()
            query.eq.return_value.is_.return_value.gte.return_value.lte.return_value.execute.return_value.data = unlinked_rows
            return query
        if columns == "id, title, meeting_date, status":
            query = MagicMock()
            query.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = activity_rows
            return query
        if columns == "id, title, meeting_date":
            query = MagicMock()
            query.eq.return_value.in_.return_value.execute.return_value.data = (
                connection_conversations
            )
            return query
        query = MagicMock()
        query.eq.return_value.in_.return_value.execute.return_value.data = title_rows
        return query

    conversations_table.select.side_effect = _select_router
    conversations_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "user_index":
            return user_index
        if name == "commitments":
            return commitments_table
        if name == "connections":
            return connections_table
        if name == "connection_linked_items":
            return connection_links_table
        if name == "topics":
            return topics_table
        return conversations_table

    db.table.side_effect = _table_router
    return db


class TestCalendarTodayEndpoint:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_upcoming_meetings_and_open_commitments(self) -> None:
        now = datetime.now(tz=UTC)
        upcoming = CalendarEvent(
            event_id="evt-upcoming",
            title="Weekly Sync",
            start_time=now + timedelta(minutes=45),
            attendees=["Murali <murali@example.com>", "Alex <alex@example.com>"],
        )
        old_event = CalendarEvent(
            event_id="evt-past",
            title="Earlier Meeting",
            start_time=now - timedelta(hours=2),
            attendees=["Past attendee <past@example.com>"],
        )

        db = _make_db_mock(
            user_index_row={
                "google_access_token": "stale-access-token",
                "google_refresh_token": "refresh-token",
            },
            unlinked_conversations=[],
            commitments=[
                {
                    "id": "commit-1",
                    "text": "Ship Phase 4 sync",
                    "owner": "Murali",
                    "due_date": None,
                    "conversation_id": "conv-1",
                }
            ],
            conversation_titles=[{"id": "conv-1", "title": "Roadmap Review"}],
            recent_activity_rows=[
                {
                    "id": "conv-2",
                    "title": "Design Review",
                    "meeting_date": now.isoformat(),
                    "status": "indexed",
                }
            ],
            connection_rows=[
                {
                    "id": "conn-1",
                    "label": "Roadmap continuity",
                    "summary": "The roadmap planning thread spans multiple meetings.",
                    "linked_type": "conversation",
                    "created_at": now.isoformat(),
                }
            ],
            connection_links=[
                {
                    "connection_id": "conn-1",
                    "linked_id": "conv-2",
                }
            ],
            related_conversation_rows=[
                {
                    "id": "conv-2",
                    "title": "Design Review",
                    "meeting_date": now.isoformat(),
                }
            ],
        )

        with (
            patch("src.api.routes.calendar.get_client", return_value=db),
            patch(
                "src.api.routes.calendar.refresh_access_token",
                new=AsyncMock(return_value="fresh-access-token"),
            ),
            patch(
                "src.api.routes.calendar.list_calendar_events",
                new=AsyncMock(return_value=[old_event, upcoming]),
            ),
        ):
            response = client.get("/calendar/today")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload["upcoming_meetings"]) == 1
        assert payload["upcoming_meetings"][0]["id"] == "evt-upcoming"
        assert payload["upcoming_meetings"][0]["title"] == "Weekly Sync"
        assert payload["open_commitments"][0]["conversation_title"] == "Roadmap Review"
        assert payload["open_commitments"][0]["text"] == "Ship Phase 4 sync"
        assert payload["recent_activity"][0]["conversation_id"] == "conv-2"
        assert payload["recent_connections"][0]["id"] == "conn-1"
        assert (
            payload["recent_connections"][0]["related_conversations"][0]["conversation_id"]
            == "conv-2"
        )

    def test_links_unlinked_conversations_to_calendar_event(self) -> None:
        meeting_time = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)

        db = _make_db_mock(
            user_index_row={
                "google_access_token": "stale-access-token",
                "google_refresh_token": "refresh-token",
            },
            unlinked_conversations=[
                {
                    "id": "conv-123",
                    "meeting_date": meeting_time.isoformat(),
                    "calendar_event_id": None,
                }
            ],
            commitments=[],
            conversation_titles=[],
        )

        today_events: list[CalendarEvent] = []
        sync_events = [
            CalendarEvent(
                event_id="evt-123",
                title="Matched Event",
                start_time=meeting_time + timedelta(minutes=20),
                attendees=["Murali <murali@example.com>"],
            )
        ]

        with (
            patch("src.api.routes.calendar.get_client", return_value=db),
            patch(
                "src.api.routes.calendar.refresh_access_token",
                new=AsyncMock(return_value="fresh-access-token"),
            ),
            patch(
                "src.api.routes.calendar.list_calendar_events",
                new=AsyncMock(side_effect=[today_events, sync_events]),
            ),
        ):
            response = client.get("/calendar/today")

        assert response.status_code == 200

        conversations_table = db.table("conversations")
        conversations_table.update.assert_called_with({"calendar_event_id": "evt-123"})

    def test_returns_400_when_refresh_token_missing(self) -> None:
        db = _make_db_mock(
            user_index_row={
                "google_access_token": "stale-access-token",
                "google_refresh_token": None,
            }
        )

        with patch("src.api.routes.calendar.get_client", return_value=db):
            response = client.get("/calendar/today")

        assert response.status_code == 400
        assert "Calendar access not authorised" in response.json()["detail"]

    def test_returns_400_on_calendar_permission_error(self) -> None:
        db = _make_db_mock(
            user_index_row={
                "google_access_token": "stale-access-token",
                "google_refresh_token": "refresh-token",
            }
        )

        with (
            patch("src.api.routes.calendar.get_client", return_value=db),
            patch(
                "src.api.routes.calendar.refresh_access_token",
                new=AsyncMock(return_value="fresh-access-token"),
            ),
            patch(
                "src.api.routes.calendar.list_calendar_events",
                new=AsyncMock(side_effect=PermissionError("invalid token")),
            ),
        ):
            response = client.get("/calendar/today")

        assert response.status_code == 400
        assert "Google Calendar access denied" in response.json()["detail"]
