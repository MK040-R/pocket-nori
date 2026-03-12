"""
tests/test_briefs.py — Unit tests for brief endpoints.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_ID = "user-briefs-test"
_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "briefs@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_brief_db(
    *,
    brief_rows: list[dict[str, Any]],
    latest_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    latest_rows = latest_rows or []

    briefs_table = MagicMock()

    def _briefs_select_router(columns: str) -> MagicMock:
        if columns == "id, conversation_id, calendar_event_id, content, generated_at":
            query = MagicMock()
            query.eq.return_value.eq.return_value.execute.return_value.data = brief_rows
            return query

        query = MagicMock()
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value.execute.return_value.data = latest_rows
        return query

    briefs_table.select.side_effect = _briefs_select_router

    brief_topic_links = MagicMock()
    brief_topic_links.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"topic_arc_id": "arc-1"}
    ]

    brief_commitment_links = MagicMock()
    brief_commitment_links.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"commitment_id": "commit-1"}
    ]

    brief_connection_links = MagicMock()
    brief_connection_links.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"connection_id": "conn-1"}
    ]

    topic_arcs_table = MagicMock()
    topic_arcs_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {
            "id": "arc-1",
            "topic_id": "topic-1",
            "cluster_id": "cluster-1",
            "summary": "Budget thread",
            "trend": "stable",
        }
    ]

    topics_table = MagicMock()
    topics_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {"id": "topic-1"}
    ]

    commitments_table = MagicMock()
    commitments_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {
            "id": "commit-1",
            "text": "Ship the deck",
            "owner": "Murali",
            "due_date": None,
            "status": "open",
        }
    ]

    connections_table = MagicMock()
    connections_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {
            "id": "conn-1",
            "label": "Shared launch thread",
            "summary": "Launch appears in product and GTM syncs",
            "linked_type": "conversation",
        }
    ]

    topic_segment_links = MagicMock()
    topic_segment_links.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {"segment_id": "seg-1"}
    ]

    commitment_segment_links = MagicMock()
    commitment_segment_links.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {"segment_id": "seg-2"}
    ]

    transcript_segments = MagicMock()
    transcript_segments.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = [
        {
            "id": "seg-1",
            "conversation_id": "conv-1",
            "speaker_id": "Murali",
            "start_ms": 1200,
            "text": "We should align the Q2 budget.",
        },
        {
            "id": "seg-2",
            "conversation_id": "conv-1",
            "speaker_id": "Alex",
            "start_ms": 2200,
            "text": "I will ship the deck by Friday.",
        },
    ]

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "briefs":
            return briefs_table
        if name == "brief_topic_arc_links":
            return brief_topic_links
        if name == "brief_commitment_links":
            return brief_commitment_links
        if name == "brief_connection_links":
            return brief_connection_links
        if name == "topic_arcs":
            return topic_arcs_table
        if name == "topics":
            return topics_table
        if name == "commitments":
            return commitments_table
        if name == "connections":
            return connections_table
        if name == "topic_segment_links":
            return topic_segment_links
        if name == "commitment_segment_links":
            return commitment_segment_links
        if name == "transcript_segments":
            return transcript_segments
        raise AssertionError(f"Unexpected table: {name}")

    db.table.side_effect = _table_router
    return db


class TestBriefRoutes:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_get_brief_returns_full_payload(self) -> None:
        db = _make_brief_db(
            brief_rows=[
                {
                    "id": "brief-1",
                    "conversation_id": "conv-1",
                    "calendar_event_id": "evt-1",
                    "content": "This is the generated brief.",
                    "generated_at": "2026-03-11T08:00:00+00:00",
                }
            ]
        )

        with patch("src.api.routes.briefs.get_client", return_value=db):
            response = client.get("/briefs/brief-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "brief-1"
        assert payload["conversation_id"] == "conv-1"
        assert payload["calendar_event_id"] == "evt-1"
        assert len(payload["topic_arcs"]) == 1
        assert len(payload["commitments"]) == 1
        assert len(payload["connections"]) == 1
        assert len(payload["citations"]) == 2

    def test_get_brief_returns_404_when_missing(self) -> None:
        db = _make_brief_db(brief_rows=[])

        with patch("src.api.routes.briefs.get_client", return_value=db):
            response = client.get("/briefs/brief-missing")

        assert response.status_code == 404
        assert response.json()["detail"] == "Brief not found"

    def test_get_latest_by_calendar_event(self) -> None:
        db = _make_brief_db(
            brief_rows=[],
            latest_rows=[
                {
                    "id": "brief-latest",
                    "generated_at": "2026-03-11T08:00:00+00:00",
                    "content": "Brief preview text for the upcoming recurring session.",
                }
            ],
        )

        with patch("src.api.routes.briefs.get_client", return_value=db):
            response = client.get("/briefs/latest?calendar_event_id=evt-123")

        assert response.status_code == 200
        payload = response.json()
        assert payload["brief_id"] == "brief-latest"
        assert payload["generated_at"] == "2026-03-11T08:00:00+00:00"
        assert "Brief preview text" in payload["preview"]
