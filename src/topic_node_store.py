"""Bridge helpers for canonical topic node identity.

This module is the runtime abstraction layer for canonical topics. During the
bridge phase it still reads and writes the legacy topic cluster storage, but
callers interact with topic nodes only.
"""

# ruff: noqa: S608

from __future__ import annotations

from typing import Any

from src.database import get_direct_connection
from src.topic_cluster_store import (
    StoredTopicCluster,
    TopicClusterSnapshot,
    assign_cluster_for_topic,
    assign_clusters_to_existing_topics,
    clear_user_topic_clusters,
    load_cluster_registry,
    load_recluster_source_rows,
    load_topic_cluster,
    load_topic_clusters,
    merge_recent_topic_rows_semantically,
    purge_placeholder_topics,
    refresh_clusters_metadata,
    stabilize_reclustered_cluster_ids,
    upsert_topic_arc_for_cluster,
    upsert_topic_arcs_for_clusters,
)

TOPIC_NODE_TABLE = "topic_clusters"
TOPIC_NODE_FOREIGN_KEY_COLUMN = "cluster_id"
TOPIC_NODE_LABEL_COLUMN = "canonical_label"
TOPIC_NODE_SUMMARY_COLUMN = "canonical_summary"

TopicNodeSnapshot = TopicClusterSnapshot
StoredTopicNode = StoredTopicCluster


def topic_node_table_name() -> str:
    return TOPIC_NODE_TABLE


def topic_node_foreign_key_column() -> str:
    return TOPIC_NODE_FOREIGN_KEY_COLUMN


def topic_node_label_column() -> str:
    return TOPIC_NODE_LABEL_COLUMN


def topic_node_summary_column() -> str:
    return TOPIC_NODE_SUMMARY_COLUMN


def load_topic_node_registry(db: Any, user_id: str) -> list[dict[str, Any]]:
    return load_cluster_registry(db, user_id)


def assign_node_for_topic(
    db: Any,
    user_id: str,
    *,
    topic_row: dict[str, Any],
    nodes: list[dict[str, Any]],
    enable_semantic: bool = True,
    max_semantic_candidates: int = 8,
    semantic_budget: dict[str, int] | None = None,
) -> str:
    return assign_cluster_for_topic(
        db,
        user_id,
        topic_row=topic_row,
        clusters=nodes,
        enable_semantic=enable_semantic,
        max_semantic_candidates=max_semantic_candidates,
        semantic_budget=semantic_budget,
    )


def load_topic_nodes(
    db: Any,
    user_id: str,
    *,
    min_conversations: int = 1,
    limit: int | None = None,
    offset: int = 0,
) -> list[StoredTopicNode]:
    return load_topic_clusters(
        db,
        user_id,
        min_conversations=min_conversations,
        limit=limit,
        offset=offset,
    )


def load_topic_node(db: Any, user_id: str, topic_or_node_id: str) -> StoredTopicNode | None:
    return load_topic_cluster(db, user_id, topic_or_node_id)


def resolve_topic_node_id(db: Any, user_id: str, topic_or_node_id: str) -> str | None:
    from src.topic_cluster_store import resolve_topic_cluster_id

    return resolve_topic_cluster_id(db, user_id, topic_or_node_id)


def refresh_node_metadata(
    db: Any,
    user_id: str,
    node_id: str,
) -> StoredTopicNode | None:
    from src.topic_cluster_store import refresh_cluster_metadata

    return refresh_cluster_metadata(db, user_id, node_id)


def refresh_nodes_metadata(
    db: Any,
    user_id: str,
    node_ids: set[str] | list[str],
) -> list[StoredTopicNode]:
    return refresh_clusters_metadata(db, user_id, node_ids)


def stabilize_rebuilt_node_ids(
    db: Any,
    user_id: str,
    previous_nodes: list[StoredTopicNode],
) -> set[str]:
    return stabilize_reclustered_cluster_ids(db, user_id, previous_nodes)


def clear_user_topic_nodes(db: Any, user_id: str) -> None:
    clear_user_topic_clusters(db, user_id)


def assign_nodes_to_existing_topics(
    db: Any,
    user_id: str,
    topic_rows: list[dict[str, Any]],
    *,
    enable_semantic: bool = True,
    semantic_budget: dict[str, int] | None = None,
) -> set[str]:
    return assign_clusters_to_existing_topics(
        db,
        user_id,
        topic_rows,
        enable_semantic=enable_semantic,
        semantic_budget=semantic_budget,
    )


def merge_recent_topic_rows_into_nodes_semantically(
    db: Any,
    user_id: str,
    topic_rows: list[dict[str, Any]],
    *,
    max_recent_conversations: int = 25,
    lookback_days: int = 90,
    max_total_semantic_checks: int = 100,
    max_semantic_candidates: int = 5,
) -> tuple[set[str], int]:
    return merge_recent_topic_rows_semantically(
        db,
        user_id,
        topic_rows,
        max_recent_conversations=max_recent_conversations,
        lookback_days=lookback_days,
        max_total_semantic_checks=max_total_semantic_checks,
        max_semantic_candidates=max_semantic_candidates,
    )


def upsert_topic_arc_for_node(
    db: Any,
    user_id: str,
    node_id: str,
) -> dict[str, Any]:
    return upsert_topic_arc_for_cluster(db, user_id, node_id)


def upsert_topic_arcs_for_nodes(
    db: Any,
    user_id: str,
    node_ids: set[str] | list[str],
) -> None:
    upsert_topic_arcs_for_clusters(db, user_id, node_ids)


def load_topic_node_label_map(
    db: Any,
    user_id: str,
    node_ids: list[str],
) -> dict[str, str]:
    if not node_ids:
        return {}
    rows = (
        db.table(TOPIC_NODE_TABLE)
        .select(f"id, {TOPIC_NODE_LABEL_COLUMN}")
        .eq("user_id", user_id)
        .in_("id", node_ids)
        .execute()
    ).data or []
    return {
        str(row["id"]): str(row.get(TOPIC_NODE_LABEL_COLUMN) or "") for row in rows if row.get("id")
    }


def search_topic_node_rows(
    user_id: str,
    query_vector: list[float],
    limit: int,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    score_threshold: float = 0.30,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    """Return raw topic node search rows using the bridge storage abstraction."""
    vector_literal = "[" + ",".join(str(value) for value in query_vector) + "]"
    date_clauses: list[str] = []
    params: list[Any] = [vector_literal, user_id, user_id, user_id, vector_literal, score_threshold]
    if date_from:
        date_clauses.append("AND c.meeting_date >= %s")
        params.append(date_from)
    if date_to:
        date_clauses.append("AND c.meeting_date <= %s")
        params.append(date_to)
    params.append(limit)

    sql = f"""
        SELECT DISTINCT ON (tn.id)
            tn.id AS result_id,
            tn.{TOPIC_NODE_LABEL_COLUMN} AS title,
            coalesce(tn.{TOPIC_NODE_SUMMARY_COLUMN}, '') AS text,
            c.id AS conversation_id,
            c.title AS conversation_title,
            c.meeting_date AS meeting_date,
            1 - (tn.embedding <=> %s::vector) AS score
        FROM {TOPIC_NODE_TABLE} tn
        JOIN topics t
          ON t.{TOPIC_NODE_FOREIGN_KEY_COLUMN} = tn.id
         AND t.user_id = %s
        JOIN conversations c
          ON c.id = t.conversation_id
         AND c.user_id = %s
        WHERE tn.user_id = %s
          AND tn.embedding IS NOT NULL
          AND 1 - (tn.embedding <=> %s::vector) >= %s
          {" ".join(date_clauses)}
        ORDER BY tn.id, c.meeting_date DESC, score DESC
        LIMIT %s
    """

    managed_conn = conn is None
    active_conn = conn or get_direct_connection()
    try:
        with active_conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        if managed_conn:
            active_conn.close()


__all__ = [
    "TOPIC_NODE_FOREIGN_KEY_COLUMN",
    "TOPIC_NODE_LABEL_COLUMN",
    "TOPIC_NODE_SUMMARY_COLUMN",
    "TOPIC_NODE_TABLE",
    "StoredTopicNode",
    "TopicNodeSnapshot",
    "assign_node_for_topic",
    "assign_nodes_to_existing_topics",
    "clear_user_topic_nodes",
    "load_recluster_source_rows",
    "load_topic_node",
    "load_topic_node_label_map",
    "load_topic_node_registry",
    "load_topic_nodes",
    "merge_recent_topic_rows_into_nodes_semantically",
    "purge_placeholder_topics",
    "refresh_node_metadata",
    "refresh_nodes_metadata",
    "resolve_topic_node_id",
    "search_topic_node_rows",
    "stabilize_rebuilt_node_ids",
    "topic_node_foreign_key_column",
    "topic_node_label_column",
    "topic_node_summary_column",
    "topic_node_table_name",
    "upsert_topic_arc_for_node",
    "upsert_topic_arcs_for_nodes",
]
