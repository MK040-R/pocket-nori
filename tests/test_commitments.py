"""
tests/test_commitments.py — Unit tests for commitments endpoints.

Tests cover input validation, user isolation, filter params, and the PATCH
status update path. No real Supabase calls — all DB access is patched.

Run:
    pytest tests/test_commitments.py -v -m unit
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.api.deps import get_current_user

client = TestClient(app)

_FAKE_JWT = "fake.jwt.token"
_FAKE_USER_ID = "user-commitments-test"

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "test@example.com",
    "_raw_jwt": _FAKE_JWT,
}

_FAKE_COMMITMENT = {
    "id": "commit-1",
    "text": "Alex will send the proposal by Friday",
    "owner": "Alex",
    "due_date": "2025-03-07",
    "status": "open",
    "conversation_id": "conv-1",
}

_FAKE_CONVERSATION = {"id": "conv-1", "title": "Weekly Sync"}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_list_db(commitments: list, conversations: list) -> MagicMock:
    """Mock DB for GET /commitments — two-table query."""
    mock_commitments = MagicMock()
    mock_commitments.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = commitments

    mock_conversations = MagicMock()
    mock_conversations.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = conversations

    mock_db = MagicMock()

    def _table(name: str) -> MagicMock:
        return mock_commitments if name == "commitments" else mock_conversations

    mock_db.table.side_effect = _table
    return mock_db


def _make_patch_db(exists: bool, updated: list, conv_title: str = "Weekly Sync") -> MagicMock:
    """Mock DB for PATCH /commitments/{id}."""
    mock_commitments = MagicMock()
    # ownership check: .select().eq().eq().execute()
    mock_commitments.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        [{"id": "commit-1"}] if exists else []
    )
    # update: .update().eq().eq().execute()
    mock_commitments.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = updated

    mock_conversations = MagicMock()
    mock_conversations.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        [{"id": "conv-1", "title": conv_title}] if updated else []
    )

    mock_db = MagicMock()

    def _table(name: str) -> MagicMock:
        return mock_commitments if name == "commitments" else mock_conversations

    mock_db.table.side_effect = _table
    return mock_db


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommitmentsInputValidation:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_invalid_filter_status_rejected(self) -> None:
        """filter_status must be 'open' or 'resolved'."""
        mock_db = _make_list_db([], [])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments?filter_status=invalid")
        assert response.status_code == 422

    def test_invalid_status_param_rejected(self) -> None:
        """?status= must also be 'open' or 'resolved'."""
        mock_db = _make_list_db([], [])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments?status=bad")
        assert response.status_code == 422

    def test_invalid_patch_status_rejected(self) -> None:
        """PATCH body status must be 'open' or 'resolved'."""
        mock_db = _make_patch_db(exists=True, updated=[])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.patch("/commitments/commit-1", json={"status": "done"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /commitments — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommitmentsListHappyPath:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_commitment_list(self) -> None:
        """Happy path: returns a list with conversation_title joined in."""
        mock_db = _make_list_db([_FAKE_COMMITMENT], [_FAKE_CONVERSATION])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "commit-1"
        assert data[0]["conversation_title"] == "Weekly Sync"

    def test_empty_list_when_no_commitments(self) -> None:
        mock_db = _make_list_db([], [])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments")
        assert response.status_code == 200
        assert response.json() == []

    def test_filter_status_param_accepted(self) -> None:
        """?status= (Codex frontend convention) is accepted."""
        mock_db = _make_list_db([_FAKE_COMMITMENT], [_FAKE_CONVERSATION])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments?status=open")
        assert response.status_code == 200

    def test_filter_status_query_accepted(self) -> None:
        """?filter_status= (original convention) is still accepted."""
        mock_db = _make_list_db([_FAKE_COMMITMENT], [_FAKE_CONVERSATION])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments?filter_status=open")
        assert response.status_code == 200

    def test_response_shape(self) -> None:
        """Response includes all required fields."""
        mock_db = _make_list_db([_FAKE_COMMITMENT], [_FAKE_CONVERSATION])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.get("/commitments")
        item = response.json()[0]
        assert "id" in item
        assert "text" in item
        assert "owner" in item
        assert "status" in item
        assert "conversation_id" in item
        assert "conversation_title" in item


# ---------------------------------------------------------------------------
# PATCH /commitments/{id}
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommitmentsPatch:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_patch_returns_updated_commitment(self) -> None:
        """Successful PATCH returns the updated commitment."""
        updated = {**_FAKE_COMMITMENT, "status": "resolved", "conversation_id": "conv-1"}
        mock_db = _make_patch_db(exists=True, updated=[updated])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.patch("/commitments/commit-1", json={"status": "resolved"})
        assert response.status_code == 200
        assert response.json()["status"] == "resolved"

    def test_patch_404_when_not_found(self) -> None:
        """Returns 404 when commitment doesn't belong to the user."""
        mock_db = _make_patch_db(exists=False, updated=[])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.patch("/commitments/nonexistent", json={"status": "resolved"})
        assert response.status_code == 404

    def test_patch_resolved_then_open(self) -> None:
        """Can re-open a resolved commitment."""
        updated = {**_FAKE_COMMITMENT, "status": "open", "conversation_id": "conv-1"}
        mock_db = _make_patch_db(exists=True, updated=[updated])
        with patch("src.api.routes.commitments.get_client", return_value=mock_db):
            response = client.patch("/commitments/commit-1", json={"status": "open"})
        assert response.status_code == 200
        assert response.json()["status"] == "open"
