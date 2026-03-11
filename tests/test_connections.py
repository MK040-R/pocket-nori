"""
tests/test_connections.py — Unit tests for conversation connections endpoint.

The detection algorithm itself is covered by route-level contract checks here:
- Conversation ownership is enforced before detection runs
- Endpoint returns the expected response shape from computed connections
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_ID = "user-connections-test"
_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "test@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db_for_conversation_exists(exists: bool = True) -> MagicMock:
    mock_conversations = MagicMock()
    mock_conversations.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        [{"id": "conv-1", "title": "Weekly Product Sync"}] if exists else []
    )

    mock_db = MagicMock()
    mock_db.table.return_value = mock_conversations
    return mock_db


@pytest.mark.unit
class TestConversationConnectionsEndpoint:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_computed_connections(self) -> None:
        mock_db = _make_db_for_conversation_exists(exists=True)
        expected_connections = [
            {
                "id": "connection-1",
                "linked_type": "topic",
                "label": "Shared topic thread",
                "summary": "Meetings are connected via shared topics.",
                "connected_conversation_id": "conv-2",
                "connected_conversation_title": "Engineering Planning",
                "connected_meeting_date": "2025-03-02T10:00:00+00:00",
                "shared_topics": ["Q3 roadmap"],
                "shared_entities": [],
                "shared_commitments": [],
            }
        ]
        with (
            patch("src.api.routes.conversations.get_client", return_value=mock_db),
            patch(
                "src.api.routes.conversations._compute_and_store_connections",
                return_value=expected_connections,
            ),
        ):
            response = client.get("/conversations/conv-1/connections")

        assert response.status_code == 200
        payload = response.json()
        assert "connections" in payload
        assert len(payload["connections"]) == 1
        assert payload["connections"][0]["id"] == "connection-1"
        assert payload["connections"][0]["connected_conversation_id"] == "conv-2"

    def test_returns_404_for_unknown_conversation(self) -> None:
        mock_db = _make_db_for_conversation_exists(exists=False)
        with (
            patch("src.api.routes.conversations.get_client", return_value=mock_db),
            patch("src.api.routes.conversations._compute_and_store_connections") as compute_mock,
        ):
            response = client.get("/conversations/missing/connections")

        assert response.status_code == 404
        compute_mock.assert_not_called()
