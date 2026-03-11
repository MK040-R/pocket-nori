"""
tests/test_topics.py — Unit tests for topics endpoints.

Tests cover the list shape (TopicSummary), the detail shape (conversations array),
and 404 behaviour. No real Supabase calls — all DB access is patched.

Run:
    pytest tests/test_topics.py -v -m unit
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_ID = "user-topics-test"

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "test@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_FAKE_TOPIC_ROW = {
    "id": "topic-1",
    "label": "Q3 Budget",
    "conversation_id": "conv-1",
    "created_at": "2025-03-01T10:00:00+00:00",
}

_FAKE_TOPIC_DETAIL_ROW = {
    "id": "topic-1",
    "label": "Q3 Budget",
    "summary": "The team discussed the Q3 budget allocation.",
    "key_quotes": ["We need to cut 10%", "Headcount is frozen"],
    "conversation_id": "conv-1",
}

_FAKE_CONVERSATION = {
    "id": "conv-1",
    "title": "Weekly Sync",
    "meeting_date": "2025-03-01T10:00:00+00:00",
}

_FAKE_TOPIC_ARC = {
    "id": "arc-1",
    "topic_id": "topic-1",
    "label": "Q3 Budget",
    "summary": "Q3 Budget appears across 2 meetings from 2025-03-01 to 2025-03-08.",
    "status": "open",
    "trend": "stable",
    "conversation_count": 2,
    "arc_points": [
        {
            "topic_id": "topic-1",
            "conversation_id": "conv-1",
            "conversation_title": "Weekly Sync",
            "occurred_at": "2025-03-01T10:00:00+00:00",
            "summary": "Budget allocation discussed.",
            "topic_status": "open",
            "citation_segment_id": "seg-1",
            "transcript_offset_seconds": 42,
            "citation_snippet": "We need to cut 10%.",
        }
    ],
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_list_db(topics: list[dict[str, Any]], conversations: list[dict[str, Any]]) -> MagicMock:
    """Mock DB for GET /topics."""
    mock_topics = MagicMock()
    mock_topics.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = topics

    mock_conversations = MagicMock()
    mock_conversations.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = conversations

    mock_db = MagicMock()

    def _table(name: str) -> MagicMock:
        return mock_topics if name == "topics" else mock_conversations

    mock_db.table.side_effect = _table
    return mock_db


def _make_detail_db(topic: list[dict[str, Any]], conversation: list[dict[str, Any]]) -> MagicMock:
    """Mock DB for GET /topics/{id}."""
    mock_topics = MagicMock()
    mock_topics.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        topic
    )

    mock_conversations = MagicMock()
    mock_conversations.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = conversation

    mock_db = MagicMock()

    def _table(name: str) -> MagicMock:
        return mock_topics if name == "topics" else mock_conversations

    mock_db.table.side_effect = _table
    return mock_db


# ---------------------------------------------------------------------------
# GET /topics — list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTopicsListHappyPath:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_topic_summary_list(self) -> None:
        """GET /topics returns a list (not empty)."""
        mock_db = _make_list_db([_FAKE_TOPIC_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_empty_when_no_topics(self) -> None:
        mock_db = _make_list_db([], [])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics")
        assert response.status_code == 200
        assert response.json() == []

    def test_summary_shape(self) -> None:
        """Response items have TopicSummary fields: id, label, conversation_count, latest_date."""
        mock_db = _make_list_db([_FAKE_TOPIC_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics")
        item = response.json()[0]
        assert "id" in item
        assert "label" in item
        assert "conversation_count" in item
        assert "latest_date" in item
        # Must NOT have old flat fields
        assert "conversation_id" not in item
        assert "summary" not in item

    def test_latest_date_from_conversation(self) -> None:
        """latest_date is the conversation's meeting_date."""
        mock_db = _make_list_db([_FAKE_TOPIC_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics")
        assert response.json()[0]["latest_date"] == "2025-03-01T10:00:00+00:00"

    def test_conversation_count_is_one(self) -> None:
        """Each topic row has conversation_count=1 (single conversation per topic)."""
        mock_db = _make_list_db([_FAKE_TOPIC_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics")
        assert response.json()[0]["conversation_count"] == 1


# ---------------------------------------------------------------------------
# GET /topics/{id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTopicsDetail:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_topic_detail(self) -> None:
        """GET /topics/{id} returns a single topic object."""
        mock_db = _make_detail_db([_FAKE_TOPIC_DETAIL_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/topic-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "topic-1"
        assert data["label"] == "Q3 Budget"

    def test_detail_has_conversations_array(self) -> None:
        """Detail response has conversations: [{id, title, meeting_date}] array."""
        mock_db = _make_detail_db([_FAKE_TOPIC_DETAIL_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/topic-1")
        data = response.json()
        assert "conversations" in data
        assert isinstance(data["conversations"], list)
        assert len(data["conversations"]) == 1
        conv = data["conversations"][0]
        assert conv["id"] == "conv-1"
        assert conv["title"] == "Weekly Sync"
        assert "meeting_date" in conv

    def test_detail_has_key_quotes(self) -> None:
        """Detail response includes key_quotes list."""
        mock_db = _make_detail_db([_FAKE_TOPIC_DETAIL_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/topic-1")
        data = response.json()
        assert "key_quotes" in data
        assert isinstance(data["key_quotes"], list)

    def test_detail_no_flat_conversation_fields(self) -> None:
        """Old flat fields (conversation_id, conversation_title, meeting_date at root) are gone."""
        mock_db = _make_detail_db([_FAKE_TOPIC_DETAIL_ROW], [_FAKE_CONVERSATION])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/topic-1")
        data = response.json()
        assert "conversation_id" not in data
        assert "conversation_title" not in data

    def test_404_when_topic_not_found(self) -> None:
        """Returns 404 when the topic doesn't exist or belongs to another user."""
        mock_db = _make_detail_db([], [])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/nonexistent")
        assert response.status_code == 404

    def test_empty_conversations_when_no_conversation(self) -> None:
        """If conversation was deleted, conversations array is empty (no crash)."""
        mock_db = _make_detail_db([_FAKE_TOPIC_DETAIL_ROW], [])
        with patch("src.api.routes.topics.get_client", return_value=mock_db):
            response = client.get("/topics/topic-1")
        assert response.status_code == 200
        assert response.json()["conversations"] == []


# ---------------------------------------------------------------------------
# GET /topics/{id}/arc — timeline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTopicArc:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_topic_arc_payload(self) -> None:
        mock_db = MagicMock()
        with (
            patch("src.api.routes.topics.get_client", return_value=mock_db),
            patch("src.api.routes.topics._build_and_store_topic_arc", return_value=_FAKE_TOPIC_ARC),
        ):
            response = client.get("/topics/topic-1/arc")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "arc-1"
        assert data["topic_id"] == "topic-1"
        assert data["conversation_count"] == 2
        assert len(data["arc_points"]) == 1

    def test_returns_404_when_topic_missing(self) -> None:
        mock_db = MagicMock()
        with (
            patch("src.api.routes.topics.get_client", return_value=mock_db),
            patch(
                "src.api.routes.topics._build_and_store_topic_arc",
                side_effect=HTTPException(status_code=404, detail="Topic not found"),
            ),
        ):
            response = client.get("/topics/nonexistent/arc")

        assert response.status_code == 404
