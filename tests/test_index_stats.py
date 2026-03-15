"""Unit tests for live dashboard index stats."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app
from src.topic_cluster_store import StoredTopicCluster

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-index-test",
    "email": "index@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db() -> MagicMock:
    user_index_table = MagicMock()
    user_index_table.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "conversation_count": 0,
            "topic_count": 0,
            "commitment_count": 0,
            "last_updated": "2026-03-12T10:00:00+00:00",
        }
    ]

    conversations_table = MagicMock()
    conversations_table.select.return_value.eq.return_value.execute.return_value.count = 7

    commitments_table = MagicMock()
    commitments_table.select.return_value.eq.return_value.execute.return_value.count = 5

    entities_table = MagicMock()
    entities_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"name": "Opus", "type": "product", "mentions": 3, "conversation_id": "conv-1"},
        {"name": "Opus", "type": "company", "mentions": 2, "conversation_id": "conv-2"},
        {"name": "N8", "type": "product", "mentions": 1, "conversation_id": "conv-3"},
        {"name": "N8N", "type": "product", "mentions": 4, "conversation_id": "conv-4"},
        {
            "name": "Nabil Mansouri",
            "type": "person",
            "mentions": 2,
            "conversation_id": "conv-5",
        },
        {"name": "Nabil", "type": "person", "mentions": 1, "conversation_id": "conv-6"},
    ]

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "user_index":
            return user_index_table
        if name == "conversations":
            return conversations_table
        if name == "commitments":
            return commitments_table
        if name == "entities":
            return entities_table
        raise AssertionError(f"Unexpected table lookup: {name}")

    db.table.side_effect = _table_router
    return db


_CLUSTERS = [
    StoredTopicCluster(
        id="cluster-1",
        label="Crawl strategy",
        summary="Planning the crawl work",
        status="open",
        first_mentioned_at="2026-03-10T10:00:00+00:00",
        last_mentioned_at="2026-03-11T10:00:00+00:00",
        conversation_ids=["conv-1", "conv-2"],
        topic_ids=["topic-1", "topic-2"],
        key_quotes=[],
        rows=[],
    ),
    StoredTopicCluster(
        id="cluster-2",
        label="Consultant onboarding",
        summary="Separate thread",
        status="open",
        first_mentioned_at="2026-03-09T10:00:00+00:00",
        last_mentioned_at="2026-03-09T10:00:00+00:00",
        conversation_ids=["conv-3"],
        topic_ids=["topic-3"],
        key_quotes=[],
        rows=[],
    ),
]


@pytest.mark.unit
class TestIndexStats:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_live_counts_with_grouped_topics(self) -> None:
        with (
            patch("src.api.routes.index_stats.get_client", return_value=_make_db()),
            patch("src.api.routes.index_stats.load_topic_clusters", return_value=_CLUSTERS),
        ):
            response = client.get("/index/stats")

        assert response.status_code == 200
        assert response.json() == {
            "conversation_count": 7,
            "topic_count": 2,
            "commitment_count": 5,
            "entity_count": 3,
            "last_updated_at": "2026-03-12T10:00:00+00:00",
        }

    def test_returns_404_when_index_missing(self) -> None:
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        with patch("src.api.routes.index_stats.get_client", return_value=db):
            response = client.get("/index/stats")

        assert response.status_code == 404
