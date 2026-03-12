"""Unit tests for llm_client helpers."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.llm_client import TopicResult, check_topic_merge


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
