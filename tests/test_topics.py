"""
tests/test_topics.py — Unit tests for grouped topics endpoints.

Tests cover grouped topic summaries, grouped detail payloads, and arc passthrough.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app
from src.topic_utils import TopicCluster

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-topics-test",
    "email": "test@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_RAW_TOPIC_ROWS = [
    {
        "id": "topic-1",
        "label": "Consultant Incentive Structure",
        "summary": "Compensation model discussion.",
        "status": "open",
        "key_quotes": ["We need to align incentive structure."],
        "conversation_id": "conv-1",
        "created_at": "2025-03-01T10:00:00+00:00",
        "meeting_date": "2025-03-01T10:00:00+00:00",
        "conversation_title": "Weekly Sync",
    },
    {
        "id": "topic-2",
        "label": "Consultant Incentive Structure",
        "summary": "Same thread revisited.",
        "status": "open",
        "key_quotes": ["Let's refine the same structure."],
        "conversation_id": "conv-2",
        "created_at": "2025-03-08T10:00:00+00:00",
        "meeting_date": "2025-03-08T10:00:00+00:00",
        "conversation_title": "Leadership Review",
    },
]

_FAKE_TOPIC_CLUSTER = TopicCluster(
    representative_id="topic-2",
    label="Consultant Incentive Structure",
    summary="Compensation model discussion.",
    key_quotes=[
        "We need to align incentive structure.",
        "Let's refine the same structure.",
    ],
    status="open",
    conversation_ids=["conv-1", "conv-2"],
    topic_ids=["topic-2", "topic-1"],
    latest_date="2025-03-08T10:00:00+00:00",
    rows=list(reversed(_RAW_TOPIC_ROWS)),
)

_FAKE_TOPIC_ARC = {
    "id": "arc-1",
    "topic_id": "topic-2",
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

    def test_returns_grouped_topic_summary_list(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics._load_topic_source_rows", return_value=_RAW_TOPIC_ROWS),
        ):
            response = client.get("/topics")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "topic-2"
        assert data[0]["label"] == "Consultant Incentive Structure"
        assert data[0]["conversation_count"] == 2

    def test_filters_placeholder_topics(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.topics._load_topic_source_rows",
                return_value=[
                    *_RAW_TOPIC_ROWS,
                    {
                        "id": "topic-3",
                        "label": "No substantive content available",
                        "summary": "placeholder",
                        "status": "open",
                        "key_quotes": [],
                        "conversation_id": "conv-3",
                        "created_at": "2025-03-09T10:00:00+00:00",
                        "meeting_date": "2025-03-09T10:00:00+00:00",
                        "conversation_title": "Placeholder",
                    },
                ],
            ),
        ):
            response = client.get("/topics")

        assert response.status_code == 200
        assert len(response.json()) == 1


@pytest.mark.unit
class TestTopicDetail:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_grouped_detail(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch("src.api.routes.topics._load_topic_cluster", return_value=_FAKE_TOPIC_CLUSTER),
        ):
            response = client.get("/topics/topic-1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "topic-2"
        assert payload["label"] == "Consultant Incentive Structure"
        assert len(payload["conversations"]) == 2
        assert payload["conversations"][0]["id"] == "conv-2"

    def test_returns_404_when_cluster_missing(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.topics._load_topic_cluster",
                side_effect=HTTPException(status_code=404, detail="Topic not found"),
            ),
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
            patch("src.api.routes.topics._build_and_store_topic_arc", return_value=_FAKE_TOPIC_ARC),
        ):
            response = client.get("/topics/topic-2/arc")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "arc-1"
        assert payload["conversation_count"] == 2

    def test_returns_404_when_topic_missing(self) -> None:
        with (
            patch("src.api.routes.topics.get_client", return_value=MagicMock()),
            patch(
                "src.api.routes.topics._build_and_store_topic_arc",
                side_effect=HTTPException(status_code=404, detail="Topic not found"),
            ),
        ):
            response = client.get("/topics/missing/arc")

        assert response.status_code == 404
