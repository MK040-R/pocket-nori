"""Unit tests for meeting category features (filter + PATCH + auto-classify)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER: dict[str, Any] = {
    "sub": "user-category-test",
    "email": "cat@example.com",
    "_raw_jwt": "fake.jwt.token",
}

_SAMPLE_CONVERSATION = {
    "id": "conv-1",
    "title": "Weekly Product Sync",
    "source": "google_drive",
    "meeting_date": "2026-03-15",
    "duration_seconds": 3600,
    "status": "indexed",
    "category": "team",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(
    *,
    conversations: list[dict[str, Any]] | None = None,
    topics: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock Supabase client for conversation category tests.

    Uses a MagicMock() that auto-chains — any chained method call returns
    a new MagicMock(), and .execute() always returns the configured data.
    """
    db = MagicMock()
    conv_data = conversations or []
    topic_data = topics or []

    # Build a chainable mock where .execute() always returns conv_data
    conv_chain = MagicMock()
    conv_chain.execute.return_value = MagicMock(data=conv_data)
    # Make every method in the chain return the same chain so any combination works
    for method in ("select", "eq", "neq", "order", "range", "update", "delete", "in_"):
        getattr(conv_chain, method).return_value = conv_chain

    topic_chain = MagicMock()
    topic_chain.execute.return_value = MagicMock(data=topic_data)
    for method in ("select", "eq", "neq", "order", "range", "in_", "limit"):
        getattr(topic_chain, method).return_value = topic_chain

    def _table_dispatch(name: str) -> MagicMock:
        if name == "conversations":
            return conv_chain
        if name == "topics":
            return topic_chain
        return MagicMock()

    db.table.side_effect = _table_dispatch
    return db


# ---------------------------------------------------------------------------
# GET /conversations?category=
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_conversations_with_category_filter() -> None:
    """Category filter returns only matching conversations."""
    _override_auth()
    try:
        db = _make_db(conversations=[_SAMPLE_CONVERSATION])
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.get("/conversations?category=team")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["category"] == "team"
    finally:
        _clear_auth()


@pytest.mark.unit
def test_list_conversations_invalid_category_returns_422() -> None:
    """Invalid category value → 422."""
    _override_auth()
    try:
        db = _make_db()
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.get("/conversations?category=invalid")

        assert response.status_code == 422
    finally:
        _clear_auth()


@pytest.mark.unit
def test_list_conversations_includes_category_field() -> None:
    """Response includes category field (even when null)."""
    _override_auth()
    try:
        conv_no_category = {**_SAMPLE_CONVERSATION, "category": None}
        db = _make_db(conversations=[conv_no_category])
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.get("/conversations")

        assert response.status_code == 200
        body = response.json()
        assert "category" in body[0]
        assert body[0]["category"] is None
    finally:
        _clear_auth()


# ---------------------------------------------------------------------------
# PATCH /conversations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_patch_conversation_category() -> None:
    """PATCH updates category and returns updated conversation."""
    _override_auth()
    try:
        updated = {**_SAMPLE_CONVERSATION, "category": "client"}
        db = _make_db(conversations=[updated])
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.patch(
                "/conversations/conv-1",
                json={"category": "client"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["category"] == "client"
    finally:
        _clear_auth()


@pytest.mark.unit
def test_patch_conversation_invalid_category() -> None:
    """Invalid category → 422."""
    _override_auth()
    try:
        db = _make_db(conversations=[_SAMPLE_CONVERSATION])
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.patch(
                "/conversations/conv-1",
                json={"category": "not-valid"},
            )

        assert response.status_code == 422
    finally:
        _clear_auth()


@pytest.mark.unit
def test_patch_conversation_not_found() -> None:
    """Unknown conversation → 404."""
    _override_auth()
    try:
        db = _make_db(conversations=[])
        with patch("src.api.routes.conversations.get_client", return_value=db):
            response = client.patch(
                "/conversations/nonexistent",
                json={"category": "team"},
            )

        assert response.status_code == 404
    finally:
        _clear_auth()


@pytest.mark.unit
def test_patch_conversation_unauthenticated() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.patch("/conversations/conv-1", json={"category": "team"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# classify_meeting_category (llm_client)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classify_meeting_category_returns_valid_category() -> None:
    """classify_meeting_category returns a valid category string."""
    from anthropic.types import TextBlock

    fake_block = MagicMock(spec=TextBlock)
    fake_block.text = "team"

    fake_response = MagicMock()
    fake_response.content = [fake_block]

    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.create.return_value = fake_response
        from src.llm_client import classify_meeting_category

        result = classify_meeting_category(
            title="Weekly Team Standup",
            topic_labels=["Sprint progress", "Blockers"],
            entity_names=["Alice", "Bob"],
        )

    assert result == "team"


@pytest.mark.unit
def test_classify_meeting_category_returns_none_on_invalid() -> None:
    """Invalid LLM output → None."""
    from anthropic.types import TextBlock

    fake_block = MagicMock(spec=TextBlock)
    fake_block.text = "random_garbage"

    fake_response = MagicMock()
    fake_response.content = [fake_block]

    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.create.return_value = fake_response
        from src.llm_client import classify_meeting_category

        result = classify_meeting_category(
            title="Test",
            topic_labels=[],
            entity_names=[],
        )

    assert result is None


@pytest.mark.unit
def test_classify_meeting_category_returns_none_on_exception() -> None:
    """LLM failure → None (non-fatal)."""
    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.create.side_effect = RuntimeError("API down")
        from src.llm_client import classify_meeting_category

        result = classify_meeting_category(
            title="Test",
            topic_labels=[],
            entity_names=[],
        )

    assert result is None
