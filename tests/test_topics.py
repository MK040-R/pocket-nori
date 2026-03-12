"""Unit tests for durable topic cluster routes."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app
from src.topic_cluster_store import StoredTopicCluster

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-topics-test",
    "email": "test@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_FAKE_CLUSTER = StoredTopicCluster(
    id="cluster-1",
    label="Consultant Incentive Structure",
    summary="Compensation model discussion.",
    status="open",
    first_mentioned_at="2025-03-01T10:00:00+00:00",
    last_mentioned_at="2025-03-08T10:00:00+00:00",
    conversation_ids=["conv-1", "conv-2"],
    topic_ids=["topic-2", "topic-1"],
    key_quotes=[
        "We need to align incentive structure.",
        "Let's refine the same structure.",
    ],
    rows=[
        {
            "id": "topic-2",
            "conversation_id": "conv-2",
            "conversation_title": "Leadership Review",
            "meeting_date": "2025-03-08T10:00:00+00:00",
            "summary": "Same thread revisited.",
            "status": "open",
            "key_quotes": ["Let's refine the same structure."],
        },
        {
            "id": "topic-1",
            "conversation_id": "conv-1",
            "conversation_title": "Weekly Sync",
            "meeting_date": "2025-03-01T10:00:00+00:00",
            "summary": "Compensation model discussion.",
            "status": "open",
            "key_quotes": ["We need to align incentive structure."],
        },
    ],
)

_FAKE_TOPIC_ARC = {
    "id": "arc-1",
    "topic_id": "cluster-1",
    "label": "Consultant Incentive Structure",
    "summary": "Consultant Incentive Structure appears across 2 meetings from 2025-03-01 to 2025-03-08.",
    "status": "open",
    "trend": "stable",
    "conversation_count": 2,
    "arc_points": [
        {
            "topic_id": "topic-1",
            "conversation_id": "conv-1",
            "conversation_title": "Weekly Sync",
            "occurred_at": "2025-03-01T10:00:00+00:00",
            "summary": "Compensation model discussion.",
            "topic_status": "open",
            "citation_segment_id": "seg-1",
            "transcript_offset_seconds": 42,
            "citation_snippet": "We need to align incentive structure.",
        }
    ],
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
class TestTopicsList:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_cluster_summary_list(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.load_topic_clusters", return_value=[_FAKE_CLUSTER]),
        ):
            response = client.get("/topics")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "cluster-1"
        assert data[0]["label"] == "Consultant Incentive Structure"
        assert data[0]["conversation_count"] == 2

    def test_passes_min_conversations_filter(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.load_topic_clusters", return_value=[]) as mock_load,
        ):
            response = client.get("/topics?min_conversations=1")

        assert response.status_code == 200
        mock_load.assert_called_once()
        assert mock_load.call_args.kwargs["min_conversations"] == 1


@pytest.mark.unit
class TestTopicDetail:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_cluster_detail(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.resolve_topic_cluster_id", return_value="cluster-1"),
            patch("src.api.routes.topics.load_topic_cluster", return_value=_FAKE_CLUSTER),
        ):
            response = client.get("/topics/cluster-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "cluster-1"
        assert payload["label"] == "Consultant Incentive Structure"
        assert len(payload["conversations"]) == 2
        assert payload["conversations"][0]["id"] == "conv-2"

    def test_raw_topic_id_falls_back_to_cluster(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.resolve_topic_cluster_id", return_value="cluster-1"),
            patch("src.api.routes.topics.load_topic_cluster", return_value=_FAKE_CLUSTER),
        ):
            response = client.get("/topics/topic-1")

        assert response.status_code == 200
        assert response.json()["id"] == "cluster-1"

    def test_returns_404_when_cluster_missing(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.resolve_topic_cluster_id", return_value=None),
            patch("src.api.routes.topics.load_topic_cluster", return_value=None),
        ):
            response = client.get("/topics/missing")

        assert response.status_code == 404


@pytest.mark.unit
class TestTopicArc:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_topic_arc_payload(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.resolve_topic_cluster_id", return_value="cluster-1"),
            patch(
                "src.api.routes.topics.upsert_topic_arc_for_cluster", return_value=_FAKE_TOPIC_ARC
            ),
        ):
            response = client.get("/topics/cluster-1/arc")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "arc-1"
        assert payload["topic_id"] == "cluster-1"
        assert payload["conversation_count"] == 2

    def test_returns_404_when_topic_missing(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics.resolve_topic_cluster_id", return_value=None),
        ):
            response = client.get("/topics/missing/arc")

        assert response.status_code == 404


@pytest.mark.unit
class TestTopicRecluster:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_queues_recluster_job(self) -> None:
        fake_result = MagicMock()
        fake_result.id = "job-123"
        with patch(
            "src.api.routes.topics.recluster_topics_for_user.delay", return_value=fake_result
        ):
            response = client.post("/topics/recluster")

        assert response.status_code == 202
        assert response.json() == {"job_id": "job-123", "status": "queued"}
