"""Unit tests for durable topic cluster assignment heuristics."""

from unittest.mock import MagicMock, patch

import pytest

from src.topic_cluster_store import (
    StoredTopicCluster,
    assign_cluster_for_topic,
    stabilize_reclustered_cluster_ids,
)


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


@pytest.mark.unit
def test_stabilize_reclustered_cluster_ids_reuses_best_matching_previous_id() -> None:
    db = MagicMock()
    topic_clusters_table = MagicMock()
    topics_table = MagicMock()

    def table_router(name: str) -> MagicMock:
        if name == "topic_clusters":
            return topic_clusters_table
        if name == "topics":
            return topics_table
        return MagicMock()

    db.table.side_effect = table_router
    previous_clusters = [
        StoredTopicCluster(
            id="old-sleep",
            label="Sleep Tracking & Sleep Cycle Education",
            summary="Sleep cycles and REM/NREM explanation.",
            status="resolved",
            first_mentioned_at="2026-02-13T12:00:00+00:00",
            last_mentioned_at="2026-02-13T12:00:00+00:00",
            conversation_ids=["conv-sleep"],
            topic_ids=["topic-sleep"],
            key_quotes=[],
            rows=[],
        ),
        StoredTopicCluster(
            id="old-analytics",
            label="Campaign event tracking setup",
            summary="Meta Pixel and UTM setup.",
            status="open",
            first_mentioned_at="2026-02-10T12:00:00+00:00",
            last_mentioned_at="2026-02-10T12:00:00+00:00",
            conversation_ids=["conv-analytics"],
            topic_ids=["topic-analytics"],
            key_quotes=[],
            rows=[],
        ),
    ]
    rebuilt_clusters = [
        StoredTopicCluster(
            id="new-sleep",
            label="Sleep Tracking & Sleep Cycle Education",
            summary="Sleep cycles and REM/NREM explanation.",
            status="resolved",
            first_mentioned_at="2026-02-13T12:00:00+00:00",
            last_mentioned_at="2026-02-13T12:00:00+00:00",
            conversation_ids=["conv-sleep"],
            topic_ids=["topic-sleep"],
            key_quotes=[],
            rows=[],
        ),
        StoredTopicCluster(
            id="new-analytics",
            label="Campaign event tracking setup",
            summary="Meta Pixel and UTM setup.",
            status="open",
            first_mentioned_at="2026-02-10T12:00:00+00:00",
            last_mentioned_at="2026-02-10T12:00:00+00:00",
            conversation_ids=["conv-analytics"],
            topic_ids=["topic-analytics"],
            key_quotes=[],
            rows=[],
        ),
    ]

    with patch(
        "src.topic_cluster_store.load_topic_clusters",
        return_value=rebuilt_clusters,
    ):
        final_cluster_ids = stabilize_reclustered_cluster_ids(db, "user-1", previous_clusters)

    assert final_cluster_ids == {"old-sleep", "old-analytics"}
    inserted_ids = [
        call.args[0]["id"] for call in topic_clusters_table.insert.call_args_list if call.args
    ]
    assert set(inserted_ids) == {"old-sleep", "old-analytics"}
    updated_cluster_ids = [
        call.args[0]["cluster_id"]
        for call in topics_table.update.call_args_list
        if call.args and "cluster_id" in call.args[0]
    ]
    assert set(updated_cluster_ids) == {"old-sleep", "old-analytics"}
