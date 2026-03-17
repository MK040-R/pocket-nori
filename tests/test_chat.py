"""Unit tests for chat endpoints (POST /chat, GET /chat/sessions, etc.)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER: dict[str, Any] = {
    "sub": "user-chat-test",
    "email": "chat@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(
    *,
    sessions: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock Supabase client for chat tests."""
    db = MagicMock()

    session_data = sessions or []
    message_data = messages or []

    session_chain = MagicMock()
    # For select queries (list sessions)
    session_chain.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
        data=session_data
    )
    # For select with single eq (verify ownership)
    session_chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=session_data)
    )
    # For insert
    session_chain.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "new-session-id", "title": "New chat"}]
    )
    # For update
    session_chain.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=session_data[:1] if session_data else [])
    )
    # For delete
    session_chain.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )

    message_chain = MagicMock()
    # For select (get messages, ordered)
    message_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
        data=message_data
    )
    # For select with limit (history)
    message_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=message_data
    )
    # For insert
    message_chain.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-msg-id"}])

    def _table_dispatch(name: str) -> MagicMock:
        if name == "chat_sessions":
            return session_chain
        if name == "chat_messages":
            return message_chain
        return MagicMock()

    db.table.side_effect = _table_dispatch
    return db


# ---------------------------------------------------------------------------
# GET /chat/sessions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_sessions_returns_200() -> None:
    """Happy path: returns list of sessions."""
    _override_auth()
    try:
        sessions = [
            {
                "id": "s1",
                "title": "Test chat",
                "created_at": "2026-03-17T10:00:00Z",
                "updated_at": "2026-03-17T10:05:00Z",
            }
        ]
        db = _make_db(sessions=sessions, messages=[{"content": "Hello"}])
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.get("/chat/sessions")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["id"] == "s1"
        assert body[0]["title"] == "Test chat"
        assert "last_message_preview" in body[0]
    finally:
        _clear_auth()


@pytest.mark.unit
def test_list_sessions_empty() -> None:
    """No sessions → empty list."""
    _override_auth()
    try:
        db = _make_db(sessions=[], messages=[])
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.get("/chat/sessions")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        _clear_auth()


@pytest.mark.unit
def test_list_sessions_unauthenticated() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.get("/chat/sessions")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /chat/sessions/{id}/messages
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_session_messages_returns_200() -> None:
    """Happy path: returns messages for a session."""
    _override_auth()
    try:
        sessions = [{"id": "s1"}]
        messages = [
            {
                "id": "m1",
                "role": "user",
                "content": "What did we discuss?",
                "citations": [],
                "created_at": "2026-03-17T10:00:00Z",
            },
            {
                "id": "m2",
                "role": "assistant",
                "content": "You discussed roadmap planning.",
                "citations": [{"result_id": "r1", "conversation_id": "c1"}],
                "created_at": "2026-03-17T10:00:01Z",
            },
        ]
        db = _make_db(sessions=sessions, messages=messages)
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.get("/chat/sessions/s1/messages")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["role"] == "user"
        assert body[1]["role"] == "assistant"
    finally:
        _clear_auth()


@pytest.mark.unit
def test_get_session_messages_not_found() -> None:
    """Unknown session → 404."""
    _override_auth()
    try:
        db = _make_db(sessions=[], messages=[])
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.get("/chat/sessions/nonexistent/messages")

        assert response.status_code == 404
    finally:
        _clear_auth()


# ---------------------------------------------------------------------------
# DELETE /chat/sessions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_delete_session_returns_204() -> None:
    """Happy path: deletes session and returns 204."""
    _override_auth()
    try:
        sessions = [{"id": "s1"}]
        db = _make_db(sessions=sessions)
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.delete("/chat/sessions/s1")

        assert response.status_code == 204
    finally:
        _clear_auth()


@pytest.mark.unit
def test_delete_session_not_found() -> None:
    """Unknown session → 404."""
    _override_auth()
    try:
        db = _make_db(sessions=[])
        with patch("src.api.routes.chat.get_client", return_value=db):
            response = client.delete("/chat/sessions/nonexistent")

        assert response.status_code == 404
    finally:
        _clear_auth()


# ---------------------------------------------------------------------------
# POST /chat (SSE streaming)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chat_post_creates_session_and_streams() -> None:
    """POST /chat with no session_id creates a new session and streams SSE."""
    _override_auth()
    try:
        db = _make_db(sessions=[], messages=[])
        with (
            patch("src.api.routes.chat.get_client", return_value=db),
            patch("src.api.routes.chat.get_direct_connection") as mock_conn,
            patch("src.api.routes.chat.llm_client") as mock_llm,
        ):
            # Mock vector search to return empty (no context)
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value.__enter__ = MagicMock(
                return_value=mock_cursor
            )
            mock_conn.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)

            mock_llm.embed_texts.return_value = [[0.1] * 1536]
            mock_llm.stream_chat_response.return_value = iter(["Hello", ", how can", " I help?"])
            mock_llm.generate_chat_title.return_value = "Test Chat"

            response = client.post(
                "/chat",
                json={"message": "What did we discuss last week?"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        # SSE body should contain session, delta, citations, and done events
        body = response.text
        assert "event: session" in body
        assert "event: delta" in body
        assert "event: citations" in body
        assert "event: done" in body
    finally:
        _clear_auth()


@pytest.mark.unit
def test_chat_post_empty_message_returns_422() -> None:
    """Empty message → 422."""
    _override_auth()
    try:
        response = client.post("/chat", json={"message": ""})
        assert response.status_code == 422
    finally:
        _clear_auth()


@pytest.mark.unit
def test_chat_post_unauthenticated() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.post("/chat", json={"message": "test"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# LLM client functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stream_chat_response_yields_chunks() -> None:
    """stream_chat_response yields text chunks from the streaming API."""
    from unittest.mock import MagicMock

    mock_stream = MagicMock()
    mock_stream.text_stream = iter(["Hello", " world"])
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)

    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.stream.return_value = mock_stream
        from src.llm_client import stream_chat_response

        chunks = list(
            stream_chat_response(
                conversation_history=[],
                context_results=[],
                user_message="test question",
            )
        )

    assert chunks == ["Hello", " world"]


@pytest.mark.unit
def test_generate_chat_title_returns_short_title() -> None:
    """generate_chat_title returns a short title string."""
    from anthropic.types import TextBlock

    fake_block = MagicMock(spec=TextBlock)
    fake_block.text = "  Roadmap Discussion  "

    fake_response = MagicMock()
    fake_response.content = [fake_block]

    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.create.return_value = fake_response
        from src.llm_client import generate_chat_title

        result = generate_chat_title("What did we discuss about the roadmap?")

    assert result == "Roadmap Discussion"
