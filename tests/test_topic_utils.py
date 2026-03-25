"""Unit tests for topic normalization and clustering helpers."""

from src.topic_utils import (
    clean_topic_label,
    cluster_topic_rows,
    is_placeholder_topic_label,
    is_semantic_merge_candidate,
    labels_match_lexically,
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


def test_labels_match_lexically_rejects_single_weak_overlap() -> None:
    assert not labels_match_lexically(
        "Sleep Tracking & Sleep Cycle Education",
        "Campaign event tracking setup",
    )


def test_semantic_merge_candidate_rejects_generic_tracking_overlap() -> None:
    assert not is_semantic_merge_candidate(
        "Sleep Tracking & Sleep Cycle Education",
        "Campaign event tracking setup",
        "Discussion about sleep cycles, REM/NREM, and how many cycles matter.",
        "Discussion about campaign attribution, signup events, and missing UTM tracking.",
    )


def test_semantic_merge_candidate_accepts_shared_initiative_context() -> None:
    assert is_semantic_merge_candidate(
        "Phase one rollout",
        "Consultant crawl expansion",
        "Discussed the PLG crawl rollout, batch planning, and consultant onboarding.",
        "Reviewed consultant crawl expansion, rollout sequence, and PLG ownership.",
    )


def test_semantic_merge_candidate_accepts_deictic_reference_with_summary_overlap() -> None:
    assert is_semantic_merge_candidate(
        "that rollout thing",
        "Enterprise rollout approval",
        "We discussed the enterprise rollout and leadership sign-off.",
        "Leadership approved the enterprise rollout for the next phase.",
    )
