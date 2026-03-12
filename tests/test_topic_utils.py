"""Unit tests for topic normalization and clustering helpers."""

from src.topic_utils import (
    clean_topic_label,
    cluster_topic_rows,
    is_placeholder_topic_label,
    sanitize_topic_rows,
)


def test_placeholder_topic_labels_are_detected() -> None:
    assert is_placeholder_topic_label("No substantive content available")
    assert is_placeholder_topic_label("No extractable transcript content")


def test_clean_topic_label_collapses_whitespace() -> None:
    assert clean_topic_label("  Crawl   strategy   task list  ") == "Crawl strategy task list"


def test_sanitize_topic_rows_drops_placeholders_and_exact_duplicates() -> None:
    rows = [
        {"label": "No substantive content available", "conversation_id": "conv-1"},
        {"label": "Consultant Incentive Structure", "conversation_id": "conv-1"},
        {"label": "consultant incentive structure", "conversation_id": "conv-1"},
        {"label": "Consultant Incentive Structure", "conversation_id": "conv-2"},
    ]

    sanitized = sanitize_topic_rows(rows)

    assert len(sanitized) == 2
    assert sanitized[0]["label"] == "Consultant Incentive Structure"


def test_cluster_topic_rows_groups_exact_duplicates_across_conversations() -> None:
    rows = [
        {
            "id": "topic-1",
            "label": "Consultant Incentive Structure",
            "summary": "Thread 1",
            "status": "open",
            "key_quotes": [],
            "conversation_id": "conv-1",
            "created_at": "2025-03-01T10:00:00+00:00",
            "meeting_date": "2025-03-01T10:00:00+00:00",
        },
        {
            "id": "topic-2",
            "label": "Consultant Incentive Structure",
            "summary": "Thread 2",
            "status": "open",
            "key_quotes": [],
            "conversation_id": "conv-2",
            "created_at": "2025-03-08T10:00:00+00:00",
            "meeting_date": "2025-03-08T10:00:00+00:00",
        },
    ]

    clusters = cluster_topic_rows(rows)

    assert len(clusters) == 1
    assert clusters[0].conversation_ids == ["conv-1", "conv-2"]
    assert clusters[0].representative_id == "topic-2"


def test_cluster_topic_rows_groups_recurring_crawl_thread() -> None:
    rows = [
        {
            "id": "topic-1",
            "label": "Phase One crawl strategy task list",
            "summary": "Thread 1",
            "status": "open",
            "key_quotes": [],
            "conversation_id": "conv-1",
            "created_at": "2025-03-01T10:00:00+00:00",
            "meeting_date": "2025-03-01T10:00:00+00:00",
        },
        {
            "id": "topic-2",
            "label": "Phased expansion of crawl batches",
            "summary": "Thread 2",
            "status": "open",
            "key_quotes": [],
            "conversation_id": "conv-2",
            "created_at": "2025-03-08T10:00:00+00:00",
            "meeting_date": "2025-03-08T10:00:00+00:00",
        },
    ]

    clusters = cluster_topic_rows(rows)

    assert len(clusters) == 1
    assert len(clusters[0].conversation_ids) == 2
