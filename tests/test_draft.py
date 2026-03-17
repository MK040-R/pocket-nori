"""Unit tests for POST /commitments/{id}/draft and generate_commitment_draft."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER: dict[str, Any] = {
    "sub": "user-draft-test",
    "email": "draft@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_SAMPLE_COMMITMENT = {
    "id": "commit-1",
    "text": "Send the updated pricing deck to Sarah",
    "owner": "Sarah",
    "conversation_id": "conv-1",
    "action_type": "commitment",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(
    *,
    commitments: list[dict[str, Any]] | None = None,
    conversations: list[dict[str, Any]] | None = None,
    segment_links: list[dict[str, Any]] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a chainable mock Supabase client for draft tests."""
    db = MagicMock()

    commit_data = commitments or []
    conv_data = conversations or []
    link_data = segment_links or []
    seg_data = segments or []

    commit_chain = MagicMock()
    commit_chain.execute.return_value = MagicMock(data=commit_data)
    for m in (
        "select",
        "eq",
        "neq",
        "order",
        "range",
        "limit",
        "in_",
        "insert",
        "update",
        "delete",
        "ilike",
        "or_",
    ):
        getattr(commit_chain, m).return_value = commit_chain

    conv_chain = MagicMock()
    conv_chain.execute.return_value = MagicMock(data=conv_data)
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_"):
        getattr(conv_chain, m).return_value = conv_chain

    link_chain = MagicMock()
    link_chain.execute.return_value = MagicMock(data=link_data)
    for m in ("select", "eq", "limit"):
        getattr(link_chain, m).return_value = link_chain

    seg_chain = MagicMock()
    seg_chain.execute.return_value = MagicMock(data=seg_data)
    for m in ("select", "eq", "in_", "order"):
        getattr(seg_chain, m).return_value = seg_chain

    def _table_dispatch(name: str) -> MagicMock:
        if name == "commitments":
            return commit_chain
        if name == "conversations":
            return conv_chain
        if name == "commitment_segment_links":
            return link_chain
        if name == "transcript_segments":
            return seg_chain
        return MagicMock()

    db.table.side_effect = _table_dispatch
    return db


# ---------------------------------------------------------------------------
# POST /commitments/{id}/draft
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_draft_returns_200_with_email() -> None:
    """Happy path: generates email draft."""
    _override_auth()
    try:
        from src.llm_client import DraftResult

        db = _make_db(
            commitments=[_SAMPLE_COMMITMENT],
            conversations=[{"title": "Weekly Sync", "meeting_date": "2026-03-15"}],
            segment_links=[{"segment_id": "seg-1"}],
            segments=[{"speaker_id": "Alice", "text": "I'll send the deck by Friday."}],
        )
        mock_draft = DraftResult(
            subject="Updated Pricing Deck",
            body="Hi Sarah,\n\nFollowing up from our Weekly Sync...",
            recipient_suggestion="Sarah",
        )
        with (
            patch("src.api.routes.commitments.get_client", return_value=db),
            patch("src.api.routes.commitments.llm_client") as mock_llm,
        ):
            mock_llm.generate_commitment_draft.return_value = mock_draft
            response = client.post(
                "/commitments/commit-1/draft",
                json={"format": "email"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["subject"] == "Updated Pricing Deck"
        assert "Sarah" in body["body"]
        assert body["recipient_suggestion"] == "Sarah"
        assert body["format"] == "email"
        assert body["commitment_text"] == _SAMPLE_COMMITMENT["text"]
    finally:
        _clear_auth()


@pytest.mark.unit
def test_draft_message_format() -> None:
    """Message format returns empty subject."""
    _override_auth()
    try:
        from src.llm_client import DraftResult

        db = _make_db(
            commitments=[_SAMPLE_COMMITMENT],
            conversations=[{"title": "Sync", "meeting_date": "2026-03-15"}],
        )
        mock_draft = DraftResult(
            subject="",
            body="Hey, just following up on the deck.",
            recipient_suggestion="Sarah",
        )
        with (
            patch("src.api.routes.commitments.get_client", return_value=db),
            patch("src.api.routes.commitments.llm_client") as mock_llm,
        ):
            mock_llm.generate_commitment_draft.return_value = mock_draft
            response = client.post(
                "/commitments/commit-1/draft",
                json={"format": "message"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["subject"] == ""
        assert body["format"] == "message"
    finally:
        _clear_auth()


@pytest.mark.unit
def test_draft_commitment_not_found() -> None:
    """Unknown commitment → 404."""
    _override_auth()
    try:
        db = _make_db(commitments=[])
        with patch("src.api.routes.commitments.get_client", return_value=db):
            response = client.post(
                "/commitments/nonexistent/draft",
                json={"format": "email"},
            )

        assert response.status_code == 404
    finally:
        _clear_auth()


@pytest.mark.unit
def test_draft_invalid_format() -> None:
    """Invalid format → 422."""
    _override_auth()
    try:
        db = _make_db(commitments=[_SAMPLE_COMMITMENT])
        with patch("src.api.routes.commitments.get_client", return_value=db):
            response = client.post(
                "/commitments/commit-1/draft",
                json={"format": "pdf"},
            )

        assert response.status_code == 422
    finally:
        _clear_auth()


@pytest.mark.unit
def test_draft_llm_failure_returns_502() -> None:
    """LLM failure → 502."""
    _override_auth()
    try:
        db = _make_db(
            commitments=[_SAMPLE_COMMITMENT],
            conversations=[{"title": "Sync", "meeting_date": "2026-03-15"}],
        )
        with (
            patch("src.api.routes.commitments.get_client", return_value=db),
            patch("src.api.routes.commitments.llm_client") as mock_llm,
        ):
            mock_llm.generate_commitment_draft.side_effect = RuntimeError("API down")
            response = client.post(
                "/commitments/commit-1/draft",
                json={"format": "email"},
            )

        assert response.status_code == 502
    finally:
        _clear_auth()


@pytest.mark.unit
def test_draft_unauthenticated() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.post("/commitments/x/draft", json={"format": "email"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# LLM: generate_commitment_draft
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_generate_commitment_draft_returns_structured_result() -> None:
    """generate_commitment_draft returns a DraftResult via instructor."""
    from src.llm_client import DraftResult

    mock_result = DraftResult(
        subject="Follow Up: Pricing Deck",
        body="Hi Sarah, following up...",
        recipient_suggestion="Sarah",
    )

    with patch("src.llm_client._instructor_client") as mock_instructor:
        mock_instructor.return_value.messages.create.return_value = mock_result
        from src.llm_client import generate_commitment_draft

        result = generate_commitment_draft(
            commitment_text="Send pricing deck",
            owner="Sarah",
            meeting_title="Weekly Sync",
            meeting_date="2026-03-15",
            transcript_context="Alice said she'd send the deck.",
            format="email",
        )

    assert result.subject == "Follow Up: Pricing Deck"
    assert result.recipient_suggestion == "Sarah"
