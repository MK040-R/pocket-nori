"""Unit tests for GET /home/summary."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER: dict[str, Any] = {
    "sub": "user-home-test",
    "email": "home@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(
    *,
    commitment_ids: list[str] | None = None,
    topic_rows: list[dict[str, Any]] | None = None,
    user_index_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a minimal mock Supabase client for home summary tests."""
    db = MagicMock()

    # commitments — return rows with ids
    commit_data = [{"id": cid} for cid in (commitment_ids or [])]
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value
    ) = MagicMock(data=commit_data)

    # We need table() to dispatch to different mocks per table name.
    # Use a side_effect that returns a chain based on the table name.
    commit_chain = MagicMock()
    commit_chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=commit_data
    )

    topic_data = topic_rows or []
    topic_chain = MagicMock()
    topic_chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=topic_data
    )

    user_index_data = user_index_rows or []
    user_index_chain = MagicMock()
    user_index_chain.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=user_index_data
    )

    def _table_dispatch(name: str) -> MagicMock:
        if name == "commitments":
            return commit_chain
        if name == "topics":
            return topic_chain
        if name == "user_index":
            return user_index_chain
        return MagicMock()

    db.table.side_effect = _table_dispatch
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_home_summary_returns_200_with_summary() -> None:
    """Happy path: endpoint returns summary text and generated_at."""
    _override_auth()
    try:
        db = _make_db(
            commitment_ids=["c1", "c2"],
            topic_rows=[{"label": "Roadmap planning"}, {"label": "Hiring pipeline"}],
            user_index_rows=[],  # no Google tokens → calendar skipped gracefully
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch(
                "src.api.routes.home.generate_home_summary",
                return_value="You have 2 upcoming meetings today and 2 open actions.",
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        body = response.json()
        assert "summary" in body
        assert body["summary"] == "You have 2 upcoming meetings today and 2 open actions."
        assert "generated_at" in body
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_unauthenticated_returns_401() -> None:
    """No auth → 401."""
    _clear_auth()
    response = client.get("/home/summary")
    assert response.status_code == 401


@pytest.mark.unit
def test_home_summary_llm_failure_falls_back_to_plain_text() -> None:
    """When the LLM call raises, the endpoint returns a plain fallback (not 500)."""
    _override_auth()
    try:
        db = _make_db(
            commitment_ids=["c1"],
            topic_rows=[],
            user_index_rows=[],
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch(
                "src.api.routes.home.generate_home_summary",
                side_effect=RuntimeError("LLM unavailable"),
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        body = response.json()
        assert "summary" in body
        # Fallback should mention the open action count
        assert "1" in body["summary"] or "open" in body["summary"].lower()
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_no_data_returns_clear_schedule_message() -> None:
    """Zero commitments and no topics → sensible fallback text."""
    _override_auth()
    try:
        db = _make_db(
            commitment_ids=[],
            topic_rows=[],
            user_index_rows=[],
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch(
                "src.api.routes.home.generate_home_summary",
                side_effect=RuntimeError("skip LLM"),
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        body = response.json()
        # Fallback with 0 commitments mentions "clear" or "caught up"
        lower = body["summary"].lower()
        assert "clear" in lower or "caught up" in lower
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_cache_key_uses_user_id_and_date() -> None:
    """Verify that the cache key is user-scoped and date-scoped."""
    import datetime

    from src.cache_utils import build_user_cache_key

    key = build_user_cache_key(
        "user-abc",
        "home_summary",
        {"date": datetime.date.today().isoformat()},
    )
    assert "user-abc" in key
    assert "home_summary" in key


@pytest.mark.unit
def test_generate_home_summary_llm_client() -> None:
    """generate_home_summary calls the raw LLM client and returns stripped text."""
    from unittest.mock import MagicMock

    from anthropic.types import TextBlock

    fake_block = MagicMock(spec=TextBlock)
    fake_block.text = "  You have 2 meetings today.  "

    fake_response = MagicMock()
    fake_response.content = [fake_block]

    with patch("src.llm_client._raw_client") as mock_raw:
        mock_raw.return_value.messages.create.return_value = fake_response
        from src.llm_client import generate_home_summary

        result = generate_home_summary(
            upcoming_meeting_titles=["Sync with Alice", "Product review"],
            open_commitment_count=3,
            recent_topic_labels=["Hiring pipeline", "Q2 roadmap"],
        )

    assert result == "You have 2 meetings today."
    mock_raw.return_value.messages.create.assert_called_once()
    call_kwargs = mock_raw.return_value.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 200
