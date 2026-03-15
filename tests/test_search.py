"""
tests/test_search.py — Unit tests for the search and ask endpoints.

Tests cover input validation, user isolation, multi-table search, and the /ask endpoint.
No real OpenAI, Anthropic, or Supabase calls — all external dependencies are patched.

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

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": _FAKE_USER_ID,
    "email": "test@example.com",
    "_raw_jwt": _FAKE_JWT,
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_mock_conn(rows: list[dict[str, Any]]) -> MagicMock:
    """Build a mock psycopg2 connection that returns `rows` from cursor.fetchall()."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


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
        response = client.post("/search", json={"q": ""})
        assert response.status_code == 422

    def test_limit_too_large_rejected(self) -> None:
        response = client.post("/search", json={"q": "hello", "limit": 99})
        assert response.status_code == 422

    def test_missing_q_rejected(self) -> None:
        response = client.post("/search", json={})
        assert response.status_code == 422

    def test_invalid_date_from_rejected(self) -> None:
        response = client.post("/search", json={"q": "test", "date_from": "not-a-date"})
        assert response.status_code == 422

    def test_invalid_date_to_rejected(self) -> None:
        response = client.post("/search", json={"q": "test", "date_to": "2025/01/01"})
        assert response.status_code == 422

    def test_valid_date_range_accepted(self) -> None:
        mock_conn = _make_mock_conn([])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post(
                "/search", json={"q": "test", "date_from": "2025-01-01", "date_to": "2025-12-31"}
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Happy path — multi-table results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchHappyPath:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def _fake_topic_row(self) -> dict[str, Any]:
        return {
            "result_id": "cluster-1",
            "title": "AWS Migration",
            "text": "Ongoing work to migrate infrastructure to AWS.",
            "conversation_id": "conv-1",
            "conversation_title": "Infra Sync",
            "meeting_date": "2025-03-01T10:00:00+00:00",
            "score": 0.91,
        }

    def _fake_segment_row(self) -> dict[str, Any]:
        return {
            "result_id": "seg-1",
            "text": "We should ship by Friday.",
            "conversation_id": "conv-1",
            "conversation_title": "Weekly Sync",
            "meeting_date": "2025-03-01T10:00:00+00:00",
            "score": 0.72,
        }

    def test_returns_results_list(self) -> None:
        mock_conn = _make_mock_conn([self._fake_topic_row()])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post("/search", json={"q": "AWS migration"})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_result_has_result_id_and_result_type(self) -> None:
        """Results must include result_id and result_type fields."""
        mock_conn = _make_mock_conn([self._fake_topic_row()])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post("/search", json={"q": "AWS"})

        assert response.status_code == 200
        data = response.json()
        if data:
            assert "result_id" in data[0]
            assert "result_type" in data[0]

    def test_empty_results_when_nothing_embedded(self) -> None:
        mock_conn = _make_mock_conn([])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            response = client.post("/search", json={"q": "anything"})

        assert response.status_code == 200
        assert response.json() == []

    def test_default_limit_applied(self) -> None:
        mock_conn = _make_mock_conn([])
        captured_params: list[Any] = []

        original_execute = mock_conn.cursor.return_value.execute

        def capture_execute(sql: str, params: Any) -> None:
            captured_params.extend(params)
            original_execute(sql, params)

        mock_conn.cursor.return_value.execute.side_effect = capture_execute

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            client.post("/search", json={"q": "test"})

        # Default limit=10 must appear somewhere in the params
        assert 10 in captured_params


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
        """If embedding fails, return 502."""
        with patch(
            "src.api.routes.search.llm_client.embed_texts",
            side_effect=RuntimeError("OpenAI down"),
        ):
            response = client.post("/search", json={"q": "something"})

        assert response.status_code == 502

    def test_partial_failure_returns_available_results(self) -> None:
        """If some index searches fail, the others still return results."""
        # First call succeeds (topic search), subsequent calls fail
        call_count = 0

        def side_effect_conn() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_conn(
                    [
                        {
                            "result_id": "cluster-1",
                            "title": "Topic A",
                            "text": "Summary A",
                            "conversation_id": "conv-1",
                            "conversation_title": "Sync",
                            "meeting_date": "2025-03-01T10:00:00+00:00",
                            "score": 0.85,
                        }
                    ]
                )
            raise RuntimeError("DB error")

        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", side_effect=side_effect_conn),
        ):
            response = client.post("/search", json={"q": "test"})

        assert response.status_code == 200

    def test_db_connections_closed_after_query(self) -> None:
        """psycopg2 connections must be closed after each search helper."""
        mock_conn = _make_mock_conn([])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
        ):
            client.post("/search", json={"q": "test"})

        # 4 helpers (topic clusters, entities, meeting digests, segments) → 4 connections
        assert mock_conn.close.call_count == 4

    def test_user_id_passed_to_query(self) -> None:
        """The validated user_id must appear in all SQL parameters (isolation check)."""
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

        # user_id must appear multiple times across all four helpers
        user_id_count = sum(1 for p in captured_params if p == _FAKE_USER_ID)
        assert user_id_count >= 4, (
            f"Expected user_id to appear ≥4 times across all search helpers, got {user_id_count}"
        )


# ---------------------------------------------------------------------------
# Date range filters
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchDateFilters:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_date_from_in_sql_params(self) -> None:
        """date_from value must appear in the SQL parameters."""
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
            client.post("/search", json={"q": "budget", "date_from": "2025-01-01"})

        assert "2025-01-01" in captured_params

    def test_date_to_in_sql_params(self) -> None:
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
            client.post("/search", json={"q": "budget", "date_to": "2025-12-31"})

        assert "2025-12-31" in captured_params


# ---------------------------------------------------------------------------
# /search/ask endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAskEndpoint:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def _fake_answer_result(self) -> Any:
        from src.llm_client import AnswerResult, CitationRef

        return AnswerResult(
            answer="The AWS migration is blocked on IAM permissions [1].",
            citations=[
                CitationRef(
                    result_id="cluster-1",
                    result_type="topic",
                    conversation_id="conv-1",
                    conversation_title="Infra Sync",
                    meeting_date="2025-03-01T10:00:00+00:00",
                    snippet="IAM permissions are the main blocker.",
                )
            ],
        )

    def test_ask_returns_answer_and_citations(self) -> None:
        mock_conn = _make_mock_conn(
            [
                {
                    "result_id": "cluster-1",
                    "title": "AWS Migration",
                    "text": "Migration is blocked on IAM.",
                    "conversation_id": "conv-1",
                    "conversation_title": "Infra Sync",
                    "meeting_date": "2025-03-01T10:00:00+00:00",
                    "score": 0.88,
                }
            ]
        )
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
            patch(
                "src.api.routes.search.llm_client.answer_question",
                return_value=self._fake_answer_result(),
            ),
        ):
            response = client.post(
                "/search/ask", json={"q": "What is the status of the AWS migration?"}
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "citations" in data
        assert isinstance(data["citations"], list)

    def test_ask_empty_context_returns_graceful_message(self) -> None:
        """When search returns no results, answer gracefully without calling Claude."""
        mock_conn = _make_mock_conn([])
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
            patch("src.api.routes.search.llm_client.answer_question") as mock_answer,
        ):
            response = client.post("/search/ask", json={"q": "something obscure"})

        assert response.status_code == 200
        data = response.json()
        assert "don't have enough context" in data["answer"].lower()
        mock_answer.assert_not_called()

    def test_ask_claude_failure_returns_502(self) -> None:
        mock_conn = _make_mock_conn(
            [
                {
                    "result_id": "cluster-1",
                    "title": "Topic",
                    "text": "Some content.",
                    "conversation_id": "conv-1",
                    "conversation_title": "Meeting",
                    "meeting_date": "2025-03-01T10:00:00+00:00",
                    "score": 0.85,
                }
            ]
        )
        with (
            patch("src.api.routes.search.llm_client.embed_texts", return_value=[[0.1] * 1536]),
            patch("src.api.routes.search.get_direct_connection", return_value=mock_conn),
            patch(
                "src.api.routes.search.llm_client.answer_question",
                side_effect=RuntimeError("Claude unavailable"),
            ),
        ):
            response = client.post("/search/ask", json={"q": "anything"})

        assert response.status_code == 502

    def test_ask_user_isolation(self) -> None:
        """user_id must appear in SQL params for /ask context retrieval."""
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
            client.post("/search/ask", json={"q": "isolation test"})

        user_id_count = sum(1 for p in captured_params if p == _FAKE_USER_ID)
        assert user_id_count >= 4

    def test_ask_empty_query_rejected(self) -> None:
        response = client.post("/search/ask", json={"q": ""})
        assert response.status_code == 422
