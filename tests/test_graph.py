"""Unit tests for graph routes."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-graph-test",
    "email": "graph@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
class TestGraphRoutes:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_neighbors_returns_graph_edges(self) -> None:
        with (
            patch("src.api.routes.graph.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.graph.get_neighbors",
                return_value=[
                    {
                        "edge_id": "edge-1",
                        "source": {"type": "topic_node", "id": "topic-1", "label": "Q3 pricing"},
                        "target": {"type": "entity_node", "id": "entity-1", "label": "Acme"},
                        "relation_type": "discussed_in_context",
                        "confidence": 0.88,
                        "evidence_count": 2,
                        "first_seen_at": "2026-03-24T10:00:00+00:00",
                        "last_seen_at": "2026-03-25T10:00:00+00:00",
                        "evidence": [
                            {
                                "edge_id": "edge-1",
                                "conversation_id": "conv-1",
                                "segment_id": "seg-1",
                                "snippet": "We discussed pricing with Acme.",
                            }
                        ],
                    }
                ],
            ),
        ):
            response = client.get("/graph/neighbors/topic_node/topic-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["node_type"] == "topic_node"
        assert payload["node_id"] == "topic-1"
        assert payload["edges"][0]["relation_type"] == "discussed_in_context"

    def test_subgraph_returns_nodes_and_edges(self) -> None:
        with (
            patch("src.api.routes.graph.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.graph.get_subgraph_for_conversation",
                return_value={
                    "nodes": [
                        {"type": "topic_node", "id": "topic-1", "label": "Q3 pricing"},
                        {"type": "entity_node", "id": "entity-1", "label": "Acme"},
                    ],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source_type": "topic_node",
                            "source_id": "topic-1",
                            "target_type": "entity_node",
                            "target_id": "entity-1",
                            "relation_type": "discussed_in_context",
                            "confidence": 0.88,
                            "evidence_count": 1,
                            "evidence": [
                                {
                                    "conversation_id": "conv-1",
                                    "segment_id": "seg-1",
                                    "snippet": "Pricing came up with Acme.",
                                }
                            ],
                        }
                    ],
                },
            ),
        ):
            response = client.get("/graph/subgraph?conversation_id=conv-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["conversation_id"] == "conv-1"
        assert len(payload["nodes"]) == 2
        assert payload["edges"][0]["id"] == "edge-1"

    def test_path_returns_path_payload(self) -> None:
        with (
            patch("src.api.routes.graph.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.graph.find_path",
                return_value={
                    "nodes": [
                        {"type": "entity_node", "id": "entity-1", "label": "Acme"},
                        {"type": "topic_node", "id": "topic-1", "label": "Q3 pricing"},
                    ],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source_type": "topic_node",
                            "source_id": "topic-1",
                            "target_type": "entity_node",
                            "target_id": "entity-1",
                            "relation_type": "discussed_in_context",
                            "confidence": 0.88,
                            "evidence_count": 1,
                        }
                    ],
                },
            ),
        ):
            response = client.get("/graph/path?from_id=entity-1&to_id=topic-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["from_id"] == "entity-1"
        assert payload["to_id"] == "topic-1"
        assert len(payload["nodes"]) == 2
        assert payload["edges"][0]["id"] == "edge-1"
