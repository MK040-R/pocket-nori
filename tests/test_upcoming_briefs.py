"""Unit tests for GET /briefs/upcoming."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER: dict[str, Any] = {
    "sub": "user-upcoming-test",
    "email": "upcoming@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(
    *,
    user_index_rows: list[dict[str, Any]] | None = None,
    brief_rows: list[dict[str, Any]] | None = None,
    commitment_rows: list[dict[str, Any]] | None = None,
    topic_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a chainable mock Supabase client."""
    db = MagicMock()

    user_data = user_index_rows or []
    brief_data = brief_rows or []
    commit_data = commitment_rows or []
    topic_data = topic_rows or []

    user_chain = MagicMock()
    user_chain.execute.return_value = MagicMock(data=user_data)
    for m in ("select", "eq"):
        getattr(user_chain, m).return_value = user_chain

    brief_chain = MagicMock()
    brief_chain.execute.return_value = MagicMock(data=brief_data)
    for m in ("select", "eq", "order", "limit"):
        getattr(brief_chain, m).return_value = brief_chain

    commit_chain = MagicMock()
    commit_chain.execute.return_value = MagicMock(data=commit_data)
    for m in ("select", "eq", "limit"):
        getattr(commit_chain, m).return_value = commit_chain

    topic_chain = MagicMock()
    topic_chain.execute.return_value = MagicMock(data=topic_data)
    for m in ("select", "eq", "order", "limit"):
        getattr(topic_chain, m).return_value = topic_chain

    def _table_dispatch(name: str) -> MagicMock:
        if name == "user_index":
            return user_chain
        if name == "briefs":
            return brief_chain
        if name == "commitments":
            return commit_chain
        if name == "topics":
            return topic_chain
        return MagicMock()

    db.table.side_effect = _table_dispatch
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upcoming_returns_empty_when_no_calendar_tokens() -> None:
    """No Google tokens → empty list."""
    _override_auth()
    try:
        db = _make_db(user_index_rows=[])
        with patch("src.api.routes.briefs.get_client", return_value=db):
            response = client.get("/briefs/upcoming")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        _clear_auth()


@pytest.mark.unit
def test_upcoming_returns_empty_when_no_refresh_token() -> None:
    """Has user_index row but no refresh token → empty list."""
    _override_auth()
    try:
        db = _make_db(user_index_rows=[{"google_access_token": "abc", "google_refresh_token": ""}])
        with patch("src.api.routes.briefs.get_client", return_value=db):
            response = client.get("/briefs/upcoming")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        _clear_auth()


@pytest.mark.unit
def test_upcoming_returns_events_when_calendar_available() -> None:
    """Calendar events available → returns upcoming briefs."""
    _override_auth()
    try:
        from datetime import UTC, datetime, timedelta

        from src.calendar_client import CalendarEvent

        future_time = datetime.now(tz=UTC) + timedelta(minutes=20)
        mock_event = CalendarEvent(
            event_id="evt-1",
            title="Product Review",
            start_time=future_time,
            end_time=future_time + timedelta(hours=1),
            attendees=["alice@example.com"],
        )

        db = _make_db(
            user_index_rows=[{"google_access_token": "token", "google_refresh_token": "refresh"}],
            brief_rows=[],
            commitment_rows=[{"id": "c1"}, {"id": "c2"}],
            topic_rows=[{"id": "t1"}],
        )

        with (
            patch("src.api.routes.briefs.get_client", return_value=db),
            patch(
                "src.calendar_client.list_calendar_events",
                return_value=[mock_event],
            ),
            patch("src.drive_client.refresh_access_token", return_value="refreshed-token"),
        ):
            response = client.get("/briefs/upcoming")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["event_title"] == "Product Review"
        assert body[0]["calendar_event_id"] == "evt-1"
        assert body[0]["open_commitments_count"] == 2
        assert body[0]["related_topic_count"] == 1
        assert body[0]["brief_id"] is None  # no brief generated yet
    finally:
        _clear_auth()


@pytest.mark.unit
def test_upcoming_unauthenticated() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.get("/briefs/upcoming")
    assert response.status_code == 401
