"""
tests/test_extract.py — Unit tests for the extract_from_conversation Celery task.

All tests use pytest-mock to patch external services (Supabase, LLM calls).
No network calls, no credentials needed.

Run:
    pytest tests/test_extract.py -v -m unit
"""

import uuid
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.workers.extract import extract_from_conversation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(text: str = "Hello world.") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "speaker_id": "speaker_0",
        "start_ms": 0,
        "text": text,
    }


def _make_db_mock(
    segments: list[dict[str, Any]] | None = None,
    conversation_exists: bool = True,
) -> MagicMock:
    db = MagicMock()

    # conversations ownership check
    if conversation_exists:
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "conv-1", "user_id": "user-1"}
        ]
    else:
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    # transcript_segments load
    # We need a more specific mock — use side_effect to differentiate calls
    return db


def _make_full_db_mock(
    segments: list[dict[str, Any]],
    user_id: str = "user-1",
    topic_count: int = 0,
    commitment_count: int = 0,
) -> MagicMock:
    """Return a mock DB that simulates a full happy-path run."""
    db = MagicMock()

    def select_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
        """Route select() calls by what table() was called with."""
        return MagicMock()

    # We use a stateful approach: patch each table call by tracking order.
    # Simpler: just make insert/update/select always succeed.

    # conversations check returns a row
    conv_mock = MagicMock()
    conv_mock.execute.return_value.data = [{"id": "conv-1", "user_id": user_id}]

    # transcript_segments returns provided segments
    seg_mock = MagicMock()
    seg_mock.execute.return_value.data = segments

    # user_index returns existing counts
    index_mock = MagicMock()
    index_mock.execute.return_value.data = [
        {"topic_count": topic_count, "commitment_count": commitment_count}
    ]

    # Route by table name
    def table_router(table_name: str) -> MagicMock:
        m = MagicMock()
        if table_name == "conversations":
            # select().eq().eq().execute()
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"id": "conv-1", "user_id": user_id}
            ]
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif table_name == "transcript_segments":
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = segments
        elif table_name == "user_index":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"topic_count": topic_count, "commitment_count": commitment_count}
            ]
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        else:
            # topics, commitments, entities, *_segment_links — all inserts succeed
            m.insert.return_value.execute.return_value.data = [{"id": str(uuid.uuid4())}]
        return m

    db.table.side_effect = table_router
    return db


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractInputValidation:
    def _run(
        self,
        eager_extract: Any,
        conversation_id: str = "conv-1",
        user_id: str = "user-1",
        user_jwt: str = "jwt-token",
    ) -> dict[str, Any]:
        result = extract_from_conversation.delay(
            conversation_id=conversation_id,
            user_id=user_id,
            user_jwt=user_jwt,
        ).get()
        return cast(dict[str, Any], result)

    def test_raises_on_empty_conversation_id(self, eager_extract: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run(eager_extract, conversation_id="")

    def test_raises_on_empty_user_id(self, eager_extract: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run(eager_extract, user_id="")

    def test_raises_on_empty_user_jwt(self, eager_extract: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run(eager_extract, user_jwt="")


# ---------------------------------------------------------------------------
# Ownership check tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractOwnershipCheck:
    def test_raises_when_conversation_not_found(self, eager_extract: Any) -> None:
        """RuntimeError raised when the conversation doesn't belong to the user."""
        with patch("src.workers.extract.get_client") as mock_get_client:
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            mock_get_client.return_value = db

            with pytest.raises(RuntimeError, match="not found"):
                extract_from_conversation.delay(
                    conversation_id="nonexistent",
                    user_id="user-1",
                    user_jwt="jwt",
                ).get()


# ---------------------------------------------------------------------------
# No segments — graceful early return
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractNoSegments:
    def test_returns_zeros_when_no_segments(self, eager_extract: Any) -> None:
        """When no segments exist, task marks conversation indexed and returns zeros."""
        with patch("src.workers.extract.get_client") as mock_get_client:
            db = _make_full_db_mock(segments=[])
            mock_get_client.return_value = db

            result = extract_from_conversation.delay(
                conversation_id="conv-1",
                user_id="user-1",
                user_jwt="jwt",
            ).get()

        assert result["topic_count"] == 0
        assert result["commitment_count"] == 0
        assert result["entity_count"] == 0


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractHappyPath:
    def test_full_extraction_returns_correct_counts(self, eager_extract: Any) -> None:
        """Happy path: 2 topics, 1 commitment, 3 entities extracted and stored."""
        from src.llm_client import (
            CommitmentList,
            CommitmentResult,
            EntityList,
            EntityResult,
            TopicList,
            TopicResult,
        )

        segments = [_make_segment("We discussed the Q3 roadmap.")]

        mock_topics = TopicList(
            topics=[
                TopicResult(
                    label="Q3 Roadmap", summary="Discussed Q3 plans.", status="open", key_quotes=[]
                ),
                TopicResult(
                    label="Budget",
                    summary="Budget allocation reviewed.",
                    status="resolved",
                    key_quotes=[],
                ),
            ]
        )
        mock_commitments = CommitmentList(
            commitments=[
                CommitmentResult(
                    text="Send Q3 plan by Friday", owner="Alice", due_date=None, status="open"
                ),
            ]
        )
        mock_entities = EntityList(
            entities=[
                EntityResult(name="Alice", type="person", mentions=3),
                EntityResult(name="Q3 Roadmap", type="project", mentions=5),
                EntityResult(name="Farz", type="product", mentions=2),
            ]
        )

        with (
            patch("src.workers.extract.get_client") as mock_get_client,
            patch("src.workers.extract.llm_client.extract_topics", return_value=mock_topics),
            patch(
                "src.workers.extract.llm_client.extract_commitments", return_value=mock_commitments
            ),
            patch("src.workers.extract.llm_client.extract_entities", return_value=mock_entities),
        ):
            db = _make_full_db_mock(segments=segments)
            mock_get_client.return_value = db

            result = extract_from_conversation.delay(
                conversation_id="conv-1",
                user_id="user-1",
                user_jwt="jwt",
            ).get()

        assert result["conversation_id"] == "conv-1"
        assert result["topic_count"] == 2
        assert result["commitment_count"] == 1
        assert result["entity_count"] == 3

    def test_user_id_isolation_in_all_inserts(self, eager_extract: Any) -> None:
        """All inserted rows must carry the correct user_id."""
        from src.llm_client import CommitmentList, EntityList, TopicList, TopicResult

        expected_user_id = "user-isolation-check"
        inserted_rows: list[dict[str, Any]] = []

        def capture_insert(data: Any) -> MagicMock:
            if isinstance(data, dict):
                inserted_rows.append(data)
            elif isinstance(data, list):
                inserted_rows.extend(data)
            m = MagicMock()
            m.execute.return_value.data = [{"id": str(uuid.uuid4())}]
            return m

        mock_topics = TopicList(
            topics=[
                TopicResult(label="Topic A", summary="Summary.", status="open", key_quotes=[]),
            ]
        )
        mock_commitments = CommitmentList(commitments=[])
        mock_entities = EntityList(entities=[])

        segments = [_make_segment("Hello.")]

        with (
            patch("src.workers.extract.get_client") as mock_get_client,
            patch("src.workers.extract.llm_client.extract_topics", return_value=mock_topics),
            patch(
                "src.workers.extract.llm_client.extract_commitments", return_value=mock_commitments
            ),
            patch("src.workers.extract.llm_client.extract_entities", return_value=mock_entities),
        ):
            db = _make_full_db_mock(segments=segments, user_id=expected_user_id)

            # Override insert to capture calls
            original_side_effect = db.table.side_effect

            def table_router_with_capture(table_name: str) -> MagicMock:
                m = cast(MagicMock, original_side_effect(table_name))
                if table_name not in ("conversations", "transcript_segments", "user_index"):
                    m.insert.side_effect = capture_insert
                return m

            db.table.side_effect = table_router_with_capture
            mock_get_client.return_value = db

            extract_from_conversation.delay(
                conversation_id="conv-1",
                user_id=expected_user_id,
                user_jwt="jwt",
            ).get()

        for row in inserted_rows:
            if "user_id" in row:
                assert row["user_id"] == expected_user_id, f"Row inserted with wrong user_id: {row}"
