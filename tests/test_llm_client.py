"""Unit tests for llm_client helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.llm_client import AnswerResult, TopicResult, check_entity_merge, check_topic_merge


def _mock_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


@pytest.mark.unit
def test_topic_result_defaults_is_background_false() -> None:
    result = TopicResult(
        label="Crawl strategy",
        summary="Focused on rollout sequencing.",
        status="open",
        key_quotes=[],
    )

    assert result.is_background is False


@pytest.mark.unit
def test_check_topic_merge_returns_true_on_yes() -> None:
    mock_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _mock_response("YES"))
    )
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
    ):
        assert (
            check_topic_merge(
                "Crawl strategy",
                "Rollout sequencing and ownership.",
                "Phase one rollout",
                "The first phase of the crawl initiative.",
            )
            is True
        )


@pytest.mark.unit
def test_check_topic_merge_returns_false_on_no() -> None:
    mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: _mock_response("NO")))
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
    ):
        assert (
            check_topic_merge(
                "Crawl strategy",
                "Rollout sequencing and ownership.",
                "Customer support handoff",
                "Support workflow details.",
            )
            is False
        )


@pytest.mark.unit
def test_check_entity_merge_returns_true_on_yes() -> None:
    mock_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _mock_response("YES"))
    )
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
    ):
        assert check_entity_merge("Nabil", "person", "Nabil Mansouri", "person") is True


@pytest.mark.unit
def test_check_entity_merge_returns_false_on_no() -> None:
    mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: _mock_response("NO")))
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
    ):
        assert check_entity_merge("Acme", "company", "Acme Analytics", "product") is False


# ---------------------------------------------------------------------------
# generate_meeting_digest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_generate_meeting_digest_returns_string() -> None:
    mock_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **_: _mock_response("Meeting covered AWS migration and budget review.")
        )
    )
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
    ):
        from src.llm_client import generate_meeting_digest

        result = generate_meeting_digest(
            topics=[{"label": "AWS Migration", "summary": "Blocked on IAM."}],
            commitments=[{"text": "Fix IAM", "owner": "John", "due_date": "2025-04-01"}],
            entities=[{"name": "John", "type": "person"}],
        )

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_generate_meeting_digest_empty_input_returns_empty() -> None:
    """If no extracted data is available, return empty string without calling LLM."""
    from src.llm_client import generate_meeting_digest

    with patch("src.llm_client._raw_client") as mock_raw:
        result = generate_meeting_digest(topics=[], commitments=[], entities=[])

    assert result == ""
    mock_raw.assert_not_called()


@pytest.mark.unit
def test_generate_meeting_digest_does_not_log_content(caplog: pytest.LogCaptureFixture) -> None:
    """Digest generation must not log meeting content."""
    mock_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _mock_response("Short digest."))
    )
    with (
        patch("src.llm_client._raw_client", return_value=mock_client),
        patch("src.llm_client.TextBlock", SimpleNamespace),
        caplog.at_level("DEBUG", logger="src.llm_client"),
    ):
        from src.llm_client import generate_meeting_digest

        generate_meeting_digest(
            topics=[{"label": "Secret Initiative", "summary": "Confidential content here."}],
            commitments=[],
            entities=[],
        )

    for record in caplog.records:
        assert "Confidential content here" not in record.message
        assert "Secret Initiative" not in record.message


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_answer_question_returns_answer_result() -> None:
    from types import SimpleNamespace

    # Mock returns _InstructorAnswer (index-based) — server resolves to CitationRef
    fake_instructor_answer = SimpleNamespace(
        answer="The migration is blocked on IAM [1].",
        cited_indices=[1],
    )

    mock_instructor = MagicMock()
    mock_instructor.messages.create.return_value = fake_instructor_answer

    with patch("src.llm_client._instructor_client", return_value=mock_instructor):
        from src.llm_client import answer_question

        result = answer_question(
            question="What is blocking the AWS migration?",
            context_results=[
                {
                    "result_id": "cluster-1",
                    "result_type": "topic",
                    "title": "AWS Migration",
                    "text": "IAM is blocking the migration.",
                    "conversation_id": "conv-1",
                    "conversation_title": "Infra Sync",
                    "meeting_date": "2025-03-01",
                    "score": 0.88,
                }
            ],
        )

    assert isinstance(result, AnswerResult)
    assert isinstance(result.answer, str)
    assert isinstance(result.citations, list)
    assert result.citations[0].result_id == "cluster-1"
    assert result.citations[0].snippet == "IAM is blocking the migration."


@pytest.mark.unit
def test_answer_question_empty_context_returns_gracefully() -> None:
    """answer_question must not call LLM when context is empty."""
    from src.llm_client import answer_question

    with patch("src.llm_client._instructor_client") as mock_inst:
        result = answer_question(question="anything", context_results=[])

    mock_inst.assert_not_called()
    assert "don't have enough context" in result.answer.lower()
    assert result.citations == []


@pytest.mark.unit
def test_answer_question_does_not_log_context(caplog: pytest.LogCaptureFixture) -> None:
    """Context (meeting content) must not appear in any log record."""
    fake_result = SimpleNamespace(answer="Short answer.", cited_indices=[])
    mock_instructor = MagicMock()
    mock_instructor.messages.create.return_value = fake_result

    with (
        patch("src.llm_client._instructor_client", return_value=mock_instructor),
        caplog.at_level("DEBUG", logger="src.llm_client"),
    ):
        from src.llm_client import answer_question

        answer_question(
            question="test question",
            context_results=[
                {
                    "result_id": "seg-1",
                    "result_type": "segment",
                    "title": "Weekly Sync",
                    "text": "CONFIDENTIAL_MEETING_TEXT_XYZ",
                    "conversation_id": "conv-1",
                    "conversation_title": "Weekly Sync",
                    "meeting_date": "2025-03-01",
                    "score": 0.75,
                }
            ],
        )

    for record in caplog.records:
        assert "CONFIDENTIAL_MEETING_TEXT_XYZ" not in record.message
