"""
tests/test_search.py — Unit tests for the search endpoint.

Tests cover input validation, user isolation, and the DB query path.
No real OpenAI or Supabase calls — all external dependencies are patched.

Run:
    pytest tests/test_search.py -v -m unit
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_JWT = "fake.jwt.token"
_FAKE_USER_ID = "user-search-test"

# Minimal decoded JWT payload returned by get_current_user
_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "test@example.com",
    "_raw_jwt": _FAKE_JWT,
}


def _override_auth() -> None:
    """Install the fake user dependency override."""
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    """Remove the dependency override."""
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchInputValidation:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_empty_query_rejected(self) -> None:
        """Empty q string must fail validation (min_length=1)."""
        response = client.post("/search", json={"q": ""})
        assert response.status_code == 422

    def test_limit_too_large_rejected(self) -> None:
        """limit > 50 must fail validation."""
        response = client.post("/search", json={"q": "hello", "limit": 99})
        assert response.status_code == 422

    def test_missing_q_rejected(self) -> None:
        response = client.post("/search", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchHappyPath:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def _fake_db_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "segment_id": "seg-1",
                "text": "We should ship by Friday.",
                "conversation_id": "conv-1",
                "conversation_title": "Weekly Sync",
                "meeting_date": "2025-03-01T10:00:00+00:00",
                "score": 0.92,
            }
        ]

    def test_returns_results_list(self) -> None:
        """Happy path: embedding succeeds, DB returns rows, response is a list."""
        fake_rows = self._fake_db_rows()

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = fake_rows
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post("/search", json={"q": "shipping deadline"})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["segment_id"] == "seg-1"
        assert data[0]["score"] == 0.92

    def test_empty_results_when_no_segments(self) -> None:
        """When no segments have embeddings, returns empty list."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post("/search", json={"q": "anything"})

        assert response.status_code == 200
        assert response.json() == []

    def test_default_limit_is_10(self) -> None:
        """When no limit is specified, the DB query should use limit=10."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            client.post("/search", json={"q": "test"})

        # The execute call's last parameter should be limit=10
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]  # positional: (sql, params)
        assert params[-1] == 10  # last param is LIMIT


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchErrorHandling:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_502_when_embedding_fails(self) -> None:
        """If OpenAI embedding call fails, return 502."""
        with patch(
            "src.api.routes.search.llm_client.embed_texts",
            side_effect=RuntimeError("OpenAI down"),
        ):
            response = client.post("/search", json={"q": "something"})

        assert response.status_code == 502

    def test_db_connection_closed_after_query(self) -> None:
        """psycopg2 connection must be closed even on success."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            client.post("/search", json={"q": "test"})

        mock_conn.close.assert_called_once()

    def test_user_id_passed_to_query(self) -> None:
        """The validated user_id must appear in the SQL parameters (isolation check)."""
        captured_params: list[Any] = []

        def capture_execute(sql: str, params: Any) -> None:
            captured_params.extend(params)

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = capture_execute
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            client.post("/search", json={"q": "isolation test"})

        # user_id must appear at least twice in query params (two WHERE clauses)
        user_id_count = sum(1 for p in captured_params if p == _FAKE_USER_ID)
        assert user_id_count >= 2, (
            f"Expected user_id to appear ≥2 times in SQL params, got {user_id_count}"
        )
