"""Unit tests for Home routes."""

from datetime import UTC, datetime, timedelta
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


class _FakeTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._count_requested = False

    def select(self, *_args: Any, count: str | None = None, **_kwargs: Any) -> "_FakeTable":
        self._count_requested = count == "exact"
        return self

    def eq(self, field: str, value: Any) -> "_FakeTable":
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field: str, values: list[Any]) -> "_FakeTable":
        self._filters.append(("in", field, values))
        return self

    def order(self, field: str, desc: bool = False) -> "_FakeTable":
        self._order = (field, desc)
        return self

    def limit(self, limit: int) -> "_FakeTable":
        self._limit = limit
        return self

    def execute(self) -> MagicMock:
        rows = list(self._rows)
        for operator, field, value in self._filters:
            if operator == "eq":
                rows = [row for row in rows if row.get(field) == value]
            elif operator == "in":
                rows = [row for row in rows if row.get(field) in value]

        total_count = len(rows)
        if self._order is not None:
            field, desc = self._order
            rows.sort(key=lambda row: row.get(field) or "", reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]

        result = MagicMock()
        result.data = rows
        result.count = total_count if self._count_requested else None
        return result


class _FakeDB:
    def __init__(self, table_rows: dict[str, list[dict[str, Any]]]) -> None:
        self._table_rows = table_rows

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._table_rows.get(name, []))


def _make_db(
    *,
    commitments: list[dict[str, Any]] | None = None,
    conversations: list[dict[str, Any]] | None = None,
    topics: list[dict[str, Any]] | None = None,
    briefs: list[dict[str, Any]] | None = None,
) -> _FakeDB:
    return _FakeDB(
        {
            "commitments": commitments or [],
            "conversations": conversations or [],
            "topics": topics or [],
            "briefs": briefs or [],
        }
    )


@pytest.mark.unit
def test_home_summary_returns_200_with_summary() -> None:
    _override_auth()
    try:
        db = _make_db(
            commitments=[
                {"id": "c1", "status": "open", "user_id": _FAKE_USER["sub"]},
                {"id": "c2", "status": "open", "user_id": _FAKE_USER["sub"]},
            ],
            topics=[
                {
                    "label": "Roadmap planning",
                    "user_id": _FAKE_USER["sub"],
                    "created_at": "2026-03-01",
                },
                {
                    "label": "Hiring pipeline",
                    "user_id": _FAKE_USER["sub"],
                    "created_at": "2026-03-02",
                },
            ],
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch("src.api.routes.home._load_dashboard_calendar_events", return_value=[]),
            patch(
                "src.api.routes.home.generate_home_summary",
                return_value="You have 2 upcoming meetings today and 2 open actions.",
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        body = response.json()
        assert body["summary"] == "You have 2 upcoming meetings today and 2 open actions."
        assert "generated_at" in body
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_unauthenticated_returns_401() -> None:
    _clear_auth()
    response = client.get("/home/summary")
    assert response.status_code == 401


@pytest.mark.unit
def test_home_summary_llm_failure_falls_back_to_plain_text() -> None:
    _override_auth()
    try:
        db = _make_db(
            commitments=[{"id": "c1", "status": "open", "user_id": _FAKE_USER["sub"]}],
            topics=[],
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch("src.api.routes.home._load_dashboard_calendar_events", return_value=[]),
            patch(
                "src.api.routes.home.generate_home_summary",
                side_effect=RuntimeError("LLM unavailable"),
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        assert "open" in response.json()["summary"].lower()
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_no_data_returns_clear_schedule_message() -> None:
    _override_auth()
    try:
        db = _make_db()
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch("src.api.routes.home._load_dashboard_calendar_events", return_value=[]),
            patch(
                "src.api.routes.home.generate_home_summary",
                side_effect=RuntimeError("skip LLM"),
            ),
        ):
            response = client.get("/home/summary")

        assert response.status_code == 200
        lower = response.json()["summary"].lower()
        assert "clear" in lower or "caught up" in lower
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_dashboard_returns_aggregated_payload() -> None:
    _override_auth()
    try:
        from src.api.routes.index_stats import IndexStats
        from src.calendar_client import CalendarEvent

        user_id = _FAKE_USER["sub"]
        future_time = datetime.now(tz=UTC) + timedelta(minutes=20)
        event = CalendarEvent(
            event_id="evt-1",
            title="Product Review",
            start_time=future_time,
            end_time=future_time + timedelta(hours=1),
            attendees=["alice@example.com"],
        )
        db = _make_db(
            commitments=[
                {
                    "id": "commit-1",
                    "text": "Send revised proposal",
                    "owner": "Murali",
                    "due_date": None,
                    "conversation_id": "conv-1",
                    "status": "open",
                    "action_type": "commitment",
                    "created_at": "2026-03-24T09:00:00+00:00",
                    "user_id": user_id,
                },
                {
                    "id": "follow-1",
                    "text": "Follow up with design",
                    "owner": "Murali",
                    "due_date": None,
                    "conversation_id": "conv-1",
                    "status": "open",
                    "action_type": "follow_up",
                    "created_at": "2026-03-24T08:00:00+00:00",
                    "user_id": user_id,
                },
            ],
            conversations=[
                {"id": "conv-1", "title": "Weekly product sync", "user_id": user_id},
            ],
            topics=[
                {"label": "Roadmap", "user_id": user_id, "created_at": "2026-03-24T07:00:00+00:00"},
            ],
            briefs=[
                {
                    "id": "brief-1",
                    "conversation_id": "conv-1",
                    "calendar_event_id": "evt-1",
                    "content": "Agenda and prior context for the product review.",
                    "generated_at": "2026-03-24T06:00:00+00:00",
                    "user_id": user_id,
                }
            ],
        )
        with (
            patch("src.api.routes.home.get_client", return_value=db),
            patch("src.api.routes.home._load_dashboard_calendar_events", return_value=[event]),
            patch(
                "src.api.routes.home.load_index_stats_snapshot",
                return_value=IndexStats(
                    conversation_count=9,
                    topic_count=4,
                    commitment_count=6,
                    entity_count=3,
                    last_updated_at="2026-03-24T08:30:00+00:00",
                ),
            ),
            patch(
                "src.api.routes.home.generate_home_summary",
                return_value="You have a product review coming up and 2 open actions in flight.",
            ),
        ):
            response = client.get("/home/dashboard")

        assert response.status_code == 200
        body = response.json()
        assert body["today"]["upcoming_meetings"][0]["title"] == "Product Review"
        assert body["stats"]["conversation_count"] == 9
        assert (
            body["summary"]["summary"]
            == "You have a product review coming up and 2 open actions in flight."
        )
        assert body["prep_push"]["brief_id"] == "brief-1"
        assert body["actions"]["commitment"][0]["conversation_title"] == "Weekly product sync"
        assert body["actions"]["follow_up"][0]["text"] == "Follow up with design"
    finally:
        _clear_auth()


@pytest.mark.unit
def test_home_summary_cache_key_uses_user_id_and_date() -> None:
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
