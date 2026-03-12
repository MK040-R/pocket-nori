"""Unit tests for durable topic cluster assignment heuristics."""

from unittest.mock import MagicMock, patch

import pytest

from src.topic_cluster_store import assign_cluster_for_topic


@pytest.mark.unit
def test_assign_cluster_skips_semantic_merge_for_weak_single_token_overlap() -> None:
    topic_row = {
        "label": "Sleep Tracking & Sleep Cycle Education",
        "summary": "Discussion about REM/NREM sleep cycles and how to count completed cycles.",
        "status": "open",
        "meeting_date": "2026-02-13T12:00:00+00:00",
    }
    clusters = [
        {
            "id": "cluster-analytics",
            "canonical_label": "Campaign event tracking setup",
            "canonical_summary": "Discussion about Meta Pixel, UTM attribution, and signup event tracking.",
            "last_mentioned_at": "2026-02-10T12:00:00+00:00",
        }
    ]

    with (
        patch("src.topic_cluster_store.llm_client.check_topic_merge") as mock_merge,
        patch(
            "src.topic_cluster_store._create_cluster",
            return_value={"id": "cluster-sleep"},
        ),
    ):
        cluster_id = assign_cluster_for_topic(
            MagicMock(),
            "user-1",
            topic_row=topic_row,
            clusters=clusters,
        )

    assert cluster_id == "cluster-sleep"
    mock_merge.assert_not_called()
