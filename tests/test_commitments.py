"""Unit tests for commitments endpoints."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-commitments-test",
    "email": "test@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_FAKE_COMMITMENT = {
    "id": "commit-1",
    "text": "Alex will send the proposal by Friday",
    "owner": "Alex",
    "due_date": "2025-03-07",
    "status": "open",
    "conversation_id": "conv-1",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_list_db(
    *,
    commitments: list[dict[str, Any]] | None = None,
    conversations: list[dict[str, Any]] | None = None,
    topics: list[dict[str, Any]] | None = None,
    topic_clusters: list[dict[str, Any]] | None = None,
) -> MagicMock:
    commitments_table = MagicMock()
    base_query = commitments_table.select.return_value.eq.return_value.order.return_value
    query_variants = [
        base_query,
        base_query.eq.return_value,
        base_query.or_.return_value,
        base_query.ilike.return_value,
        base_query.eq.return_value.ilike.return_value,
        base_query.or_.return_value.ilike.return_value,
    ]
    for variant in query_variants:
        variant.execute.return_value.data = commitments or []
        variant.range.return_value.execute.return_value.data = commitments or []

    conversations_table = MagicMock()
    conversations_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = (
        conversations or []
    )

    topics_table = MagicMock()
    topics_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = (
        topics or []
    )
    topic_clusters_table = MagicMock()
    topic_clusters_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = (
        topic_clusters or []
    )

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "commitments":
            return commitments_table
        if name == "topics":
            return topics_table
        if name == "topic_clusters":
            return topic_clusters_table
        return conversations_table

    db.table.side_effect = _table_router
    return db


def _make_patch_db(updated: list[dict[str, Any]], exists: bool = True) -> MagicMock:
    commitments_table = MagicMock()
    commitments_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        [{"id": "commit-1"}] if exists else []
    )
    commitments_table.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = updated

    conversations_table = MagicMock()
    conversations_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "conv-1", "title": "Weekly Sync", "meeting_date": "2025-03-01T10:00:00+00:00"}
    ]

    topics_table = MagicMock()
    topics_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "topic-1",
            "cluster_id": "cluster-1",
            "label": "Proposal follow-up",
            "conversation_id": "conv-1",
        }
    ]
    topic_clusters_table = MagicMock()
    topic_clusters_table.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
        {"id": "cluster-1", "canonical_label": "Proposal follow-up"}
    ]

    db = MagicMock()

    def _table_router(name: str) -> MagicMock:
        if name == "commitments":
            return commitments_table
        if name == "topics":
            return topics_table
        if name == "topic_clusters":
            return topic_clusters_table
        return conversations_table

    db.table.side_effect = _table_router
    return db


@pytest.mark.unit
class TestCommitmentsList:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_rejects_invalid_status_filter(self) -> None:
        with patch("src.api.routes.commitments.get_client", return_value=_make_list_db()):
            response = client.get("/commitments?status=bad")

        assert response.status_code == 422

    def test_rejects_invalid_date_range(self) -> None:
        with patch("src.api.routes.commitments.get_client", return_value=_make_list_db()):
            response = client.get(
                "/commitments?meeting_date_from=2025-03-08T00:00:00+00:00&meeting_date_to=2025-03-01T00:00:00+00:00"
            )

        assert response.status_code == 422

    def test_returns_enriched_commitment_fields(self) -> None:
        db = _make_list_db(
            commitments=[_FAKE_COMMITMENT],
            conversations=[
                {
                    "id": "conv-1",
                    "title": "Weekly Sync",
                    "meeting_date": "2025-03-01T10:00:00+00:00",
                }
            ],
            topics=[
                {
                    "id": "topic-1",
                    "cluster_id": "cluster-1",
                    "label": "Proposal follow-up",
                    "conversation_id": "conv-1",
                }
            ],
            topic_clusters=[{"id": "cluster-1", "canonical_label": "Proposal follow-up"}],
        )
        with patch("src.api.routes.commitments.get_client", return_value=db):
            response = client.get("/commitments")

        assert response.status_code == 200
        payload = response.json()[0]
        assert payload["conversation_title"] == "Weekly Sync"
        assert payload["meeting_date"] == "2025-03-01T10:00:00+00:00"
        assert payload["topic_labels"] == ["Proposal follow-up"]

    def test_filters_by_topic_in_python_layer(self) -> None:
        db = _make_list_db(
            commitments=[_FAKE_COMMITMENT],
            conversations=[
                {
                    "id": "conv-1",
                    "title": "Weekly Sync",
                    "meeting_date": "2025-03-01T10:00:00+00:00",
                }
            ],
            topics=[
                {
                    "id": "topic-1",
                    "cluster_id": "cluster-1",
                    "label": "Proposal follow-up",
                    "conversation_id": "conv-1",
                }
            ],
            topic_clusters=[{"id": "cluster-1", "canonical_label": "Proposal follow-up"}],
        )
        with patch("src.api.routes.commitments.get_client", return_value=db):
            matching = client.get("/commitments?topic=proposal")
            non_matching = client.get("/commitments?topic=pricing")

        assert matching.status_code == 200
        assert len(matching.json()) == 1
        assert non_matching.status_code == 200
        assert non_matching.json() == []


@pytest.mark.unit
class TestCommitmentsPatch:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_patch_returns_enriched_commitment(self) -> None:
        updated = {**_FAKE_COMMITMENT, "status": "resolved"}
        with patch("src.api.routes.commitments.get_client", return_value=_make_patch_db([updated])):
            response = client.patch("/commitments/commit-1", json={"status": "resolved"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "resolved"
        assert payload["meeting_date"] == "2025-03-01T10:00:00+00:00"
        assert payload["topic_labels"] == ["Proposal follow-up"]

    def test_patch_returns_404_when_missing(self) -> None:
        with patch(
            "src.api.routes.commitments.get_client", return_value=_make_patch_db([], exists=False)
        ):
            response = client.patch("/commitments/missing", json={"status": "resolved"})

        assert response.status_code == 404
