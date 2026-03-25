"""Durable topic cluster helpers.

This module owns:
- topic cluster assignment at ingestion/backfill time
- cluster metadata refresh from member topic rows
- stored cluster loading for read routes
- cluster-id resolution from raw topic ids

No LLM calls are allowed from read routes. Semantic merge checks happen only
through assign_cluster_for_topic() during ingestion/backfill.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src import llm_client
from src.topic_utils import (
    clean_topic_label,
    is_placeholder_topic_label,
    is_semantic_merge_candidate,
    labels_match_lexically,
    normalize_topic_label,
    topic_overlap_score,
)


@dataclass(slots=True)
class TopicClusterSnapshot:
    canonical_label: str
    canonical_summary: str
    status: str
    first_mentioned_at: str
    last_mentioned_at: str
    key_quotes: list[str]


@dataclass(slots=True)
class StoredTopicCluster:
    id: str
    label: str
    summary: str
    status: str
    first_mentioned_at: str
    last_mentioned_at: str
    conversation_ids: list[str]
    topic_ids: list[str]
    key_quotes: list[str]
    rows: list[dict[str, Any]]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _sort_key_for_row(row: dict[str, Any]) -> tuple[datetime, str]:
    created_at = _parse_datetime(row.get("meeting_date") or row.get("created_at"))
    return (
        created_at or datetime.min.replace(tzinfo=UTC),
        str(row.get("id") or ""),
    )


def _label_recency(rows: list[dict[str, Any]], label: str) -> datetime:
    for row in rows:
        if clean_topic_label(str(row.get("label") or "")) == label:
            return _sort_key_for_row(row)[0]
    return datetime.min.replace(tzinfo=UTC)


def _datetime_sort_score(value: datetime) -> float:
    if value == datetime.min.replace(tzinfo=UTC):
        return float("-inf")
    return value.timestamp()


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(tz=UTC).isoformat()
    return value.isoformat()


def _format_date_label(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if not parsed:
        return "unknown date"
    return parsed.date().isoformat()


def _build_cluster_snapshot(rows: list[dict[str, Any]]) -> TopicClusterSnapshot:
    sorted_rows = sorted(rows, key=_sort_key_for_row, reverse=True)
    label_counts = Counter(clean_topic_label(str(row.get("label") or "")) for row in sorted_rows)
    candidate_labels = sorted(
        (label for label in label_counts if label),
        key=lambda label: (
            -label_counts[label],
            len(label),
            -_datetime_sort_score(_label_recency(sorted_rows, label)),
        ),
    )
    canonical_label = (
        candidate_labels[0]
        if candidate_labels
        else clean_topic_label(str(sorted_rows[0].get("label") or ""))
    )

    summary = ""
    canonical_label_rows = [
        row
        for row in sorted_rows
        if clean_topic_label(str(row.get("label") or "")) == canonical_label
        and str(row.get("summary") or "").strip()
    ]
    if canonical_label_rows:
        summary = str(canonical_label_rows[0].get("summary") or "").strip()
    else:
        for row in sorted_rows:
            summary = str(row.get("summary") or "").strip()
            if summary:
                break

    statuses = {str(row.get("status") or "open") for row in sorted_rows}
    status = "resolved" if statuses == {"resolved"} else "open"

    timestamps = [
        _parse_datetime(row.get("meeting_date") or row.get("created_at")) for row in sorted_rows
    ]
    values = [value for value in timestamps if value is not None]
    first_mentioned_at = _serialize_datetime(min(values) if values else None)
    last_mentioned_at = _serialize_datetime(max(values) if values else None)

    key_quotes: list[str] = []
    for row in sorted_rows:
        for quote in row.get("key_quotes") or []:
            quote_text = str(quote).strip()
            if quote_text and quote_text not in key_quotes:
                key_quotes.append(quote_text)
            if len(key_quotes) >= 4:
                break
        if len(key_quotes) >= 4:
            break

    return TopicClusterSnapshot(
        canonical_label=canonical_label,
        canonical_summary=summary,
        status=status,
        first_mentioned_at=first_mentioned_at,
        last_mentioned_at=last_mentioned_at,
        key_quotes=key_quotes,
    )


def _load_cluster_rows(
    db: Any,
    user_id: str,
    cluster_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.table("topic_clusters")
        .select(
            "id, canonical_label, canonical_summary, mention_count, status, first_mentioned_at, "
            "last_mentioned_at, created_at, updated_at"
        )
        .eq("user_id", user_id)
    )
    if cluster_ids is not None:
        if not cluster_ids:
            return []
        query = query.in_("id", cluster_ids)
    return query.order("last_mentioned_at", desc=True).execute().data or []


def _load_topic_member_rows(
    db: Any,
    user_id: str,
    cluster_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.table("topics")
        .select("id, cluster_id, label, summary, status, key_quotes, conversation_id, created_at")
        .eq("user_id", user_id)
    )
    if cluster_ids is not None:
        if not cluster_ids:
            return []
        query = query.in_("cluster_id", cluster_ids)
    else:
        query = query.not_.is_("cluster_id", "null")

    topic_rows = query.order("created_at", desc=True).execute().data or []
    if not topic_rows:
        return []

    conversation_ids = sorted(
        {str(row["conversation_id"]) for row in topic_rows if row.get("conversation_id")}
    )
    conversations: list[dict[str, Any]] = []
    if conversation_ids:
        conversations = (
            db.table("conversations")
            .select("id, title, meeting_date")
            .eq("user_id", user_id)
            .in_("id", conversation_ids)
            .execute()
        ).data or []
    conversation_map = {str(row["id"]): row for row in conversations if row.get("id")}

    return [
        {
            **row,
            "meeting_date": conversation_map.get(str(row.get("conversation_id") or ""), {}).get(
                "meeting_date"
            ),
            "conversation_title": conversation_map.get(
                str(row.get("conversation_id") or ""),
                {},
            ).get("title", ""),
        }
        for row in topic_rows
    ]


def _build_stored_cluster(
    cluster_row: dict[str, Any],
    member_rows: list[dict[str, Any]],
) -> StoredTopicCluster:
    snapshot = _build_cluster_snapshot(member_rows)
    conversation_ids = sorted(
        {str(row.get("conversation_id") or "") for row in member_rows if row.get("conversation_id")}
    )
    topic_ids = [str(row.get("id") or "") for row in member_rows if row.get("id")]
    return StoredTopicCluster(
        id=str(cluster_row.get("id") or ""),
        label=str(cluster_row.get("canonical_label") or snapshot.canonical_label),
        summary=str(cluster_row.get("canonical_summary") or snapshot.canonical_summary),
        status=str(cluster_row.get("status") or snapshot.status),
        first_mentioned_at=str(
            cluster_row.get("first_mentioned_at") or snapshot.first_mentioned_at
        ),
        last_mentioned_at=str(cluster_row.get("last_mentioned_at") or snapshot.last_mentioned_at),
        conversation_ids=conversation_ids,
        topic_ids=topic_ids,
        key_quotes=snapshot.key_quotes,
        rows=sorted(member_rows, key=_sort_key_for_row, reverse=True),
    )


def load_topic_clusters(
    db: Any,
    user_id: str,
    *,
    min_conversations: int = 1,
    limit: int | None = None,
    offset: int = 0,
) -> list[StoredTopicCluster]:
    cluster_rows = _load_cluster_rows(db, user_id)
    if not cluster_rows:
        return []

    cluster_ids = [str(row.get("id") or "") for row in cluster_rows if row.get("id")]
    member_rows = _load_topic_member_rows(db, user_id, cluster_ids)
    rows_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in member_rows:
        cluster_id = str(row.get("cluster_id") or "")
        if cluster_id:
            rows_by_cluster[cluster_id].append(row)

    clusters: list[StoredTopicCluster] = []
    for cluster_row in cluster_rows:
        cluster_id = str(cluster_row.get("id") or "")
        members = rows_by_cluster.get(cluster_id, [])
        if not members:
            continue
        cluster = _build_stored_cluster(cluster_row, members)
        if len(cluster.conversation_ids) < min_conversations:
            continue
        clusters.append(cluster)

    clusters.sort(
        key=lambda cluster: (
            _parse_datetime(cluster.last_mentioned_at) or datetime.min.replace(tzinfo=UTC),
            cluster.label.lower(),
        ),
        reverse=True,
    )
    visible = clusters[offset:]
    if limit is not None:
        visible = visible[:limit]
    return visible


def resolve_topic_cluster_id(db: Any, user_id: str, topic_or_cluster_id: str) -> str | None:
    cluster_rows = (
        db.table("topic_clusters")
        .select("id")
        .eq("user_id", user_id)
        .eq("id", topic_or_cluster_id)
        .execute()
    ).data or []
    if cluster_rows:
        return str(cluster_rows[0].get("id") or "")

    topic_rows = (
        db.table("topics")
        .select("cluster_id")
        .eq("user_id", user_id)
        .eq("id", topic_or_cluster_id)
        .execute()
    ).data or []
    if topic_rows and topic_rows[0].get("cluster_id"):
        return str(topic_rows[0]["cluster_id"])
    return None


def load_topic_cluster(
    db: Any,
    user_id: str,
    topic_or_cluster_id: str,
) -> StoredTopicCluster | None:
    cluster_id = resolve_topic_cluster_id(db, user_id, topic_or_cluster_id)
    if not cluster_id:
        return None
    clusters = load_topic_clusters(db, user_id, min_conversations=1)
    for cluster in clusters:
        if cluster.id == cluster_id:
            return cluster
    return None


def _cluster_identity_candidates(
    rebuilt_clusters: list[StoredTopicCluster],
    previous_clusters: list[StoredTopicCluster],
) -> list[tuple[int, int, int, float, str, str]]:
    candidates: list[tuple[int, int, int, float, str, str]] = []
    for rebuilt in rebuilt_clusters:
        rebuilt_topic_ids = {topic_id for topic_id in rebuilt.topic_ids if topic_id}
        if not rebuilt_topic_ids:
            continue
        rebuilt_label = normalize_topic_label(rebuilt.label)
        rebuilt_last = _parse_datetime(rebuilt.last_mentioned_at) or datetime.min.replace(
            tzinfo=UTC
        )
        for previous in previous_clusters:
            previous_topic_ids = {topic_id for topic_id in previous.topic_ids if topic_id}
            overlap = len(rebuilt_topic_ids & previous_topic_ids)
            if overlap == 0:
                continue
            exact_label = int(rebuilt_label == normalize_topic_label(previous.label))
            lexical_score = topic_overlap_score(rebuilt.label, previous.label)
            recency_score = _datetime_sort_score(rebuilt_last)
            candidates.append(
                (
                    overlap,
                    exact_label,
                    lexical_score,
                    recency_score,
                    rebuilt.id,
                    previous.id,
                )
            )
    candidates.sort(reverse=True)
    return candidates


def _insert_cluster_with_id(
    db: Any,
    user_id: str,
    *,
    cluster_id: str,
    cluster: StoredTopicCluster,
) -> None:
    (
        db.table("topic_clusters")
        .insert(
            {
                "id": cluster_id,
                "user_id": user_id,
                "canonical_label": cluster.label,
                "canonical_summary": cluster.summary,
                "mention_count": len(cluster.topic_ids),
                "status": cluster.status,
                "first_mentioned_at": cluster.first_mentioned_at,
                "last_mentioned_at": cluster.last_mentioned_at,
            }
        )
        .execute()
    )


def stabilize_reclustered_cluster_ids(
    db: Any,
    user_id: str,
    previous_clusters: list[StoredTopicCluster],
) -> set[str]:
    """Reuse prior cluster ids where rebuilt clusters clearly descend from them.

    Reclustering currently clears and rebuilds cluster rows. Without an explicit
    reconciliation pass, old topic URLs break after every rebuild. This helper
    preserves ids when a rebuilt cluster shares underlying topic rows with a
    prior cluster, using overlap-first greedy assignment.
    """

    rebuilt_clusters = load_topic_clusters(db, user_id, min_conversations=1)
    if not rebuilt_clusters:
        return set()
    if not previous_clusters:
        return {cluster.id for cluster in rebuilt_clusters}

    rebuilt_by_id = {cluster.id: cluster for cluster in rebuilt_clusters}
    final_cluster_ids = set(rebuilt_by_id)
    assigned_rebuilt: set[str] = set()
    assigned_previous: set[str] = set()

    for _, _, _, _, rebuilt_id, previous_id in _cluster_identity_candidates(
        rebuilt_clusters,
        previous_clusters,
    ):
        if rebuilt_id in assigned_rebuilt or previous_id in assigned_previous:
            continue
        if rebuilt_id == previous_id:
            assigned_rebuilt.add(rebuilt_id)
            assigned_previous.add(previous_id)
            continue

        rebuilt_cluster = rebuilt_by_id.get(rebuilt_id)
        if rebuilt_cluster is None:
            continue

        _insert_cluster_with_id(
            db,
            user_id,
            cluster_id=previous_id,
            cluster=rebuilt_cluster,
        )
        (
            db.table("topics")
            .update({"cluster_id": previous_id})
            .eq("user_id", user_id)
            .eq("cluster_id", rebuilt_id)
            .execute()
        )
        (db.table("topic_clusters").delete().eq("user_id", user_id).eq("id", rebuilt_id).execute())

        assigned_rebuilt.add(rebuilt_id)
        assigned_previous.add(previous_id)
        final_cluster_ids.discard(rebuilt_id)
        final_cluster_ids.add(previous_id)

    return final_cluster_ids


def _create_cluster(
    db: Any,
    user_id: str,
    *,
    label: str,
    summary: str,
    status: str,
    mentioned_at: str,
) -> dict[str, Any]:
    inserted = (
        db.table("topic_clusters")
        .insert(
            {
                "user_id": user_id,
                "canonical_label": label,
                "canonical_summary": summary,
                "mention_count": 1,
                "status": status,
                "first_mentioned_at": mentioned_at,
                "last_mentioned_at": mentioned_at,
            }
        )
        .execute()
    ).data or []
    if not inserted:
        raise RuntimeError("Failed to create topic cluster")
    return dict(inserted[0])


def load_cluster_registry(db: Any, user_id: str) -> list[dict[str, Any]]:
    return _load_cluster_rows(db, user_id)


def _find_lexical_cluster_id(
    label: str,
    clusters: list[dict[str, Any]],
) -> str | None:
    lexical_candidates = sorted(
        (
            cluster
            for cluster in clusters
            if labels_match_lexically(label, cluster.get("canonical_label"))
        ),
        key=lambda cluster: (
            topic_overlap_score(label, str(cluster.get("canonical_label") or "")),
            _parse_datetime(str(cluster.get("last_mentioned_at") or ""))
            or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    if not lexical_candidates:
        return None
    return str(lexical_candidates[0]["id"])


def _find_semantic_cluster_id(
    label: str,
    summary: str,
    clusters: list[dict[str, Any]],
    *,
    max_semantic_candidates: int = 8,
    semantic_budget: dict[str, int] | None = None,
) -> str | None:
    semantic_candidates = sorted(
        (
            cluster
            for cluster in clusters
            if is_semantic_merge_candidate(
                label,
                cluster.get("canonical_label"),
                summary,
                str(cluster.get("canonical_summary") or ""),
            )
        ),
        key=lambda cluster: (
            topic_overlap_score(label, str(cluster.get("canonical_label") or "")),
            _parse_datetime(str(cluster.get("last_mentioned_at") or ""))
            or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )[:max_semantic_candidates]

    for candidate in semantic_candidates:
        if semantic_budget is not None:
            limit = semantic_budget.get("limit", 0)
            used = semantic_budget.get("used", 0)
            if used >= limit:
                return None
            semantic_budget["used"] = used + 1
        if llm_client.check_topic_merge(
            label,
            summary,
            str(candidate.get("canonical_label") or ""),
            str(candidate.get("canonical_summary") or ""),
        ):
            return str(candidate.get("id") or "")
    return None


def assign_cluster_for_topic(
    db: Any,
    user_id: str,
    *,
    topic_row: dict[str, Any],
    clusters: list[dict[str, Any]],
    enable_semantic: bool = True,
    max_semantic_candidates: int = 8,
    semantic_budget: dict[str, int] | None = None,
) -> str:
    label = clean_topic_label(str(topic_row.get("label") or ""))
    summary = str(topic_row.get("summary") or "").strip()
    status = str(topic_row.get("status") or "open")
    mentioned_at = str(topic_row.get("meeting_date") or topic_row.get("created_at") or "")

    lexical_cluster_id = _find_lexical_cluster_id(label, clusters)
    if lexical_cluster_id:
        return lexical_cluster_id

    if enable_semantic:
        semantic_cluster_id = _find_semantic_cluster_id(
            label,
            summary,
            clusters,
            max_semantic_candidates=max_semantic_candidates,
            semantic_budget=semantic_budget,
        )
        if semantic_cluster_id:
            return semantic_cluster_id

    created = _create_cluster(
        db,
        user_id,
        label=label,
        summary=summary,
        status=status,
        mentioned_at=mentioned_at or datetime.now(tz=UTC).isoformat(),
    )
    clusters.append(created)
    return str(created.get("id") or "")


def refresh_cluster_metadata(
    db: Any,
    user_id: str,
    cluster_id: str,
) -> StoredTopicCluster | None:
    member_rows = _load_topic_member_rows(db, user_id, [cluster_id])
    if not member_rows:
        (db.table("topic_clusters").delete().eq("user_id", user_id).eq("id", cluster_id).execute())
        return None

    snapshot = _build_cluster_snapshot(member_rows)
    updated_rows = (
        db.table("topic_clusters")
        .update(
            {
                "canonical_label": snapshot.canonical_label,
                "canonical_summary": snapshot.canonical_summary,
                "mention_count": len(member_rows),
                "status": snapshot.status,
                "first_mentioned_at": snapshot.first_mentioned_at,
                "last_mentioned_at": snapshot.last_mentioned_at,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        .eq("user_id", user_id)
        .eq("id", cluster_id)
        .execute()
    ).data or []
    cluster_row = updated_rows[0] if updated_rows else {"id": cluster_id}
    return _build_stored_cluster(cluster_row, member_rows)


def refresh_clusters_metadata(
    db: Any,
    user_id: str,
    cluster_ids: set[str] | list[str],
) -> list[StoredTopicCluster]:
    refreshed: list[StoredTopicCluster] = []
    for cluster_id in sorted({cluster_id for cluster_id in cluster_ids if cluster_id}):
        cluster = refresh_cluster_metadata(db, user_id, cluster_id)
        if cluster is not None:
            refreshed.append(cluster)
    return refreshed


def clear_user_topic_clusters(db: Any, user_id: str) -> None:
    (db.table("topics").update({"cluster_id": None}).eq("user_id", user_id).execute())
    (db.table("topic_arcs").delete().eq("user_id", user_id).execute())
    (db.table("topic_clusters").delete().eq("user_id", user_id).execute())


def purge_placeholder_topics(db: Any, user_id: str) -> int:
    rows = (db.table("topics").select("id, label").eq("user_id", user_id).execute()).data or []
    placeholder_ids = [
        str(row.get("id") or "")
        for row in rows
        if row.get("id") and is_placeholder_topic_label(row.get("label"))
    ]
    if not placeholder_ids:
        return 0
    (db.table("topics").delete().eq("user_id", user_id).in_("id", placeholder_ids).execute())
    return len(placeholder_ids)


def load_recluster_source_rows(db: Any, user_id: str) -> list[dict[str, Any]]:
    topic_rows = (
        db.table("topics")
        .select("id, label, summary, status, key_quotes, conversation_id, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    ).data or []
    if not topic_rows:
        return []

    conversation_ids = sorted(
        {str(row["conversation_id"]) for row in topic_rows if row.get("conversation_id")}
    )
    conversation_rows: list[dict[str, Any]] = []
    if conversation_ids:
        conversation_rows = (
            db.table("conversations")
            .select("id, title, meeting_date")
            .eq("user_id", user_id)
            .in_("id", conversation_ids)
            .execute()
        ).data or []
    conversation_map = {str(row["id"]): row for row in conversation_rows if row.get("id")}

    return [
        {
            **row,
            "label": clean_topic_label(str(row.get("label") or "")),
            "meeting_date": conversation_map.get(str(row.get("conversation_id") or ""), {}).get(
                "meeting_date"
            ),
            "conversation_title": conversation_map.get(
                str(row.get("conversation_id") or ""),
                {},
            ).get("title", ""),
        }
        for row in topic_rows
        if row.get("id")
        and clean_topic_label(str(row.get("label") or ""))
        and not is_placeholder_topic_label(row.get("label"))
    ]


def assign_clusters_to_existing_topics(
    db: Any,
    user_id: str,
    topic_rows: list[dict[str, Any]],
    *,
    enable_semantic: bool = True,
    semantic_budget: dict[str, int] | None = None,
) -> set[str]:
    clusters = load_cluster_registry(db, user_id)
    affected_cluster_ids: set[str] = set()
    for row in topic_rows:
        cluster_id = assign_cluster_for_topic(
            db,
            user_id,
            topic_row=row,
            clusters=clusters,
            enable_semantic=enable_semantic,
            semantic_budget=semantic_budget,
        )
        affected_cluster_ids.add(cluster_id)
        row["cluster_id"] = cluster_id
        (
            db.table("topics")
            .update({"cluster_id": cluster_id})
            .eq("user_id", user_id)
            .eq("id", str(row.get("id") or ""))
            .execute()
        )
    return affected_cluster_ids


def _select_recent_topic_rows(
    topic_rows: list[dict[str, Any]],
    *,
    max_recent_conversations: int,
    lookback_days: int,
) -> list[dict[str, Any]]:
    if not topic_rows:
        return []

    cutoff = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    recent_rows: list[dict[str, Any]] = []
    selected_conversations: set[str] = set()

    for row in sorted(topic_rows, key=_sort_key_for_row, reverse=True):
        occurred_at = _parse_datetime(row.get("meeting_date") or row.get("created_at"))
        if occurred_at is None or occurred_at < cutoff:
            continue
        conversation_id = str(row.get("conversation_id") or "")
        if (
            conversation_id
            and conversation_id not in selected_conversations
            and len(selected_conversations) >= max_recent_conversations
        ):
            continue
        if conversation_id:
            selected_conversations.add(conversation_id)
        recent_rows.append(row)
    return recent_rows


def merge_recent_topic_rows_semantically(
    db: Any,
    user_id: str,
    topic_rows: list[dict[str, Any]],
    *,
    max_recent_conversations: int = 25,
    lookback_days: int = 90,
    max_total_semantic_checks: int = 100,
    max_semantic_candidates: int = 5,
) -> tuple[set[str], int]:
    recent_rows = _select_recent_topic_rows(
        topic_rows,
        max_recent_conversations=max_recent_conversations,
        lookback_days=lookback_days,
    )
    if not recent_rows:
        return set(), 0

    semantic_budget = {"used": 0, "limit": max_total_semantic_checks}
    affected_cluster_ids: set[str] = set()

    clusters = load_topic_clusters(db, user_id, min_conversations=1)
    cluster_map = {cluster.id: cluster for cluster in clusters}
    cluster_candidates = [
        {
            "id": cluster.id,
            "canonical_label": cluster.label,
            "canonical_summary": cluster.summary,
            "last_mentioned_at": cluster.last_mentioned_at,
        }
        for cluster in clusters
    ]

    for row in recent_rows:
        current_cluster_id = str(row.get("cluster_id") or "")
        if not current_cluster_id:
            continue
        current_cluster = cluster_map.get(current_cluster_id)
        if current_cluster is None:
            continue
        # Only spend semantic budget on singleton leftovers from the lexical pass.
        if len(current_cluster.conversation_ids) > 1 or len(current_cluster.topic_ids) > 1:
            continue

        label = clean_topic_label(str(row.get("label") or ""))
        summary = str(row.get("summary") or "").strip()
        candidate_clusters = [
            candidate
            for candidate in cluster_candidates
            if str(candidate.get("id") or "") != current_cluster_id
        ]
        target_cluster_id = _find_semantic_cluster_id(
            label,
            summary,
            candidate_clusters,
            max_semantic_candidates=max_semantic_candidates,
            semantic_budget=semantic_budget,
        )
        if not target_cluster_id or target_cluster_id == current_cluster_id:
            continue

        (
            db.table("topics")
            .update({"cluster_id": target_cluster_id})
            .eq("user_id", user_id)
            .eq("id", str(row.get("id") or ""))
            .execute()
        )
        row["cluster_id"] = target_cluster_id
        affected_cluster_ids.add(current_cluster_id)
        affected_cluster_ids.add(target_cluster_id)

        # Refresh in-memory cluster view so later rows see the updated membership.
        clusters = load_topic_clusters(db, user_id, min_conversations=1)
        cluster_map = {cluster.id: cluster for cluster in clusters}
        cluster_candidates = [
            {
                "id": cluster.id,
                "canonical_label": cluster.label,
                "canonical_summary": cluster.summary,
                "last_mentioned_at": cluster.last_mentioned_at,
            }
            for cluster in clusters
        ]

    return affected_cluster_ids, semantic_budget["used"]


def upsert_topic_arc_for_cluster(
    db: Any,
    user_id: str,
    cluster_id: str,
) -> dict[str, Any]:
    cluster = load_topic_cluster(db, user_id, cluster_id)
    if cluster is None:
        raise RuntimeError(f"Topic cluster {cluster_id} not found")

    topic_to_segment_ids: dict[str, list[str]] = {}
    topic_segment_match_scores: dict[tuple[str, str], float] = {}
    if cluster.topic_ids:
        link_rows = (
            db.table("topic_segment_links")
            .select("topic_id, segment_id, match_score")
            .eq("user_id", user_id)
            .in_("topic_id", cluster.topic_ids)
            .execute()
        ).data or []
        for row in link_rows:
            topic_id = str(row.get("topic_id") or "")
            segment_id = str(row.get("segment_id") or "")
            if topic_id and segment_id:
                topic_to_segment_ids.setdefault(topic_id, []).append(segment_id)
                raw_score = row.get("match_score")
                match_score = float(raw_score) if isinstance(raw_score, int | float) else 0.0
                topic_segment_match_scores[(topic_id, segment_id)] = match_score

    segment_map: dict[str, dict[str, Any]] = {}
    all_segment_ids = sorted(
        {segment_id for segment_ids in topic_to_segment_ids.values() for segment_id in segment_ids}
    )
    if all_segment_ids:
        segment_rows = (
            db.table("transcript_segments")
            .select("id, start_ms, text")
            .eq("user_id", user_id)
            .in_("id", all_segment_ids)
            .execute()
        ).data or []
        segment_map = {str(row["id"]): row for row in segment_rows if row.get("id")}

    raw_points: list[dict[str, Any]] = []
    for topic_row in cluster.rows:
        current_topic_id = str(topic_row.get("id") or "")
        conversation_id = str(topic_row.get("conversation_id") or "")
        segment_ids = topic_to_segment_ids.get(current_topic_id, [])
        sorted_segments = sorted(
            (segment_map[segment_id] for segment_id in segment_ids if segment_id in segment_map),
            key=lambda row: (
                topic_segment_match_scores.get((current_topic_id, str(row.get("id") or "")), 0.0),
                -(row.get("start_ms") or 0),
            ),
            reverse=True,
        )
        primary_segment = sorted_segments[0] if sorted_segments else None

        snippet: str | None = None
        offset_seconds: int | None = None
        citation_segment_id: str | None = None
        if primary_segment:
            text_value = str(primary_segment.get("text") or "").strip()
            snippet = text_value[:220] if text_value else None
            start_ms = primary_segment.get("start_ms")
            if isinstance(start_ms, int):
                offset_seconds = start_ms // 1000
            if primary_segment.get("id"):
                citation_segment_id = str(primary_segment["id"])

        occurred_at = str(topic_row.get("meeting_date") or topic_row.get("created_at") or "")
        raw_points.append(
            {
                "topic_id": current_topic_id,
                "conversation_id": conversation_id,
                "conversation_title": str(
                    topic_row.get("conversation_title") or "Untitled meeting"
                ),
                "occurred_at": occurred_at,
                "summary": str(topic_row.get("summary") or ""),
                "topic_status": str(topic_row.get("status") or "open"),
                "citation_segment_id": citation_segment_id,
                "transcript_offset_seconds": offset_seconds,
                "citation_snippet": snippet,
            }
        )

    raw_points.sort(
        key=lambda point: (
            _parse_datetime(str(point.get("occurred_at") or "")) or datetime.min.replace(tzinfo=UTC)
        )
    )

    arc_points: list[dict[str, Any]] = []
    seen_conversations: set[str] = set()
    for point in raw_points:
        conversation_id = str(point.get("conversation_id") or "")
        if not conversation_id or conversation_id in seen_conversations:
            continue
        seen_conversations.add(conversation_id)
        arc_points.append(point)

    overall_status = (
        "resolved"
        if arc_points and all(point["topic_status"] == "resolved" for point in arc_points)
        else "open"
    )
    if overall_status == "resolved":
        trend = "resolved"
    elif len(arc_points) >= 3:
        trend = "growing"
    else:
        trend = "stable"

    if not arc_points:
        arc_summary = f"{cluster.label} has not been linked to indexed meetings yet."
    elif len(arc_points) == 1:
        arc_summary = f"{cluster.label} has appeared in one meeting so far."
    else:
        first_seen = _format_date_label(str(arc_points[0].get("occurred_at") or ""))
        last_seen = _format_date_label(str(arc_points[-1].get("occurred_at") or ""))
        arc_summary = (
            f"{cluster.label} appears across {len(arc_points)} meetings from "
            f"{first_seen} to {last_seen}."
        )

    representative_topic_id = cluster.topic_ids[0] if cluster.topic_ids else None
    existing_arc = (
        db.table("topic_arcs")
        .select("id")
        .eq("user_id", user_id)
        .eq("cluster_id", cluster.id)
        .execute()
    ).data or []
    if existing_arc:
        arc_id = str(existing_arc[0].get("id") or "")
        (
            db.table("topic_arcs")
            .update(
                {
                    "topic_id": representative_topic_id,
                    "summary": arc_summary,
                    "trend": trend,
                    "cluster_id": cluster.id,
                }
            )
            .eq("user_id", user_id)
            .eq("id", arc_id)
            .execute()
        )
    else:
        inserted = (
            db.table("topic_arcs")
            .insert(
                {
                    "user_id": user_id,
                    "topic_id": representative_topic_id,
                    "cluster_id": cluster.id,
                    "summary": arc_summary,
                    "trend": trend,
                }
            )
            .execute()
        ).data or []
        if not inserted:
            raise RuntimeError("Failed to create topic arc")
        arc_id = str(inserted[0].get("id") or "")

    (
        db.table("topic_arc_conversation_links")
        .delete()
        .eq("topic_arc_id", arc_id)
        .eq("user_id", user_id)
        .execute()
    )
    if arc_points:
        (
            db.table("topic_arc_conversation_links")
            .insert(
                [
                    {
                        "topic_arc_id": arc_id,
                        "conversation_id": str(point["conversation_id"]),
                        "user_id": user_id,
                    }
                    for point in arc_points
                ]
            )
            .execute()
        )

    return {
        "id": arc_id,
        "topic_id": cluster.id,
        "label": cluster.label,
        "summary": arc_summary,
        "status": overall_status,
        "trend": trend,
        "conversation_count": len(arc_points),
        "arc_points": arc_points,
    }


def upsert_topic_arcs_for_clusters(
    db: Any,
    user_id: str,
    cluster_ids: set[str] | list[str],
) -> None:
    for cluster_id in sorted({cluster_id for cluster_id in cluster_ids if cluster_id}):
        upsert_topic_arc_for_cluster(db, user_id, cluster_id)
