"""Unit tests for dashboard index stats."""

from types import SimpleNamespace
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


def _make_chain(data: list[dict[str, Any]]) -> MagicMock:
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=data)
    for method_name in ("select", "eq"):
        getattr(chain, method_name).return_value = chain
    return chain


def _make_db(index_row: dict[str, Any], entity_rows: list[dict[str, Any]] | None = None) -> MagicMock:
    user_index_table = _make_chain([index_row])
    entities_table = _make_chain(entity_rows or [])

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "user_index":
            return user_index_table
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

    def test_returns_stored_counts_when_entity_count_is_present(self) -> None:
        db = _make_db(
            {
                "conversation_count": 7,
                "topic_count": 2,
                "commitment_count": 5,
                "entity_count": 3,
                "last_updated": "2026-03-12T10:00:00+00:00",
            }
        )

        with patch("src.api.routes.index_stats.get_client", return_value=db):
            response = client.get("/index/stats")

        assert response.status_code == 200
        assert response.json() == {
            "conversation_count": 7,
            "topic_count": 2,
            "commitment_count": 5,
            "entity_count": 3,
            "last_updated_at": "2026-03-12T10:00:00+00:00",
        }

    def test_falls_back_to_entity_nodes_when_entity_count_is_missing(self) -> None:
        db = _make_db(
            {
                "conversation_count": 7,
                "topic_count": 0,
                "commitment_count": 5,
                "last_updated": "2026-03-12T10:00:00+00:00",
            }
        )

        with (
            patch("src.api.routes.index_stats.get_client", return_value=db),
            patch("src.api.routes.index_stats.load_topic_clusters", return_value=_CLUSTERS),
            patch(
                "src.api.routes.index_stats.load_entity_nodes",
                return_value=[
                    SimpleNamespace(id="entity-node-1"),
                    SimpleNamespace(id="entity-node-2"),
                    SimpleNamespace(id="entity-node-3"),
                ],
            ),
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
