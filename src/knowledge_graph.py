"""Knowledge graph materialization and query helpers."""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from datetime import UTC, datetime
from itertools import combinations
from typing import Any, TypedDict

from src import llm_client
from src.entity_node_store import (
    load_entity_node_name_map,
    resolve_entity_node_for_name,
)
from src.topic_node_store import load_topic_node_label_map

logger = logging.getLogger(__name__)

_SYMMETRIC_RELATIONS = {"co_mentioned"}
_VALID_NODE_TYPES = {"topic_node", "entity_node", "commitment"}
_VALID_RELATIONS = {
    "co_mentioned",
    "discussed_in_context",
    "assigned_to",
    "works_on",
    "owns",
    "reports_to",
    "manages",
    "uses",
    "depends_on",
    "decided",
    "blocked_by",
    "client_of",
    "partner_of",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}


class _ConnectionCandidate(TypedDict):
    shared_topics: set[str]
    shared_entities: set[str]
    shared_commitments: set[str]
    graph_matches: int


def _new_connection_candidate() -> _ConnectionCandidate:
    return {
        "shared_topics": set(),
        "shared_entities": set(),
        "shared_commitments": set(),
        "graph_matches": 0,
    }


def _normalize_phrase(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def _commitment_signature(owner: str | None, text: str | None) -> str:
    owner_norm = _normalize_phrase(owner)
    tokens = [token for token in _TOKEN_RE.findall((text or "").lower()) if token not in _STOPWORDS]
    if not owner_norm or not tokens:
        return ""
    return f"{owner_norm}:{'-'.join(tokens[:6])}"


def _ordered_edge_endpoints(
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation_type: str,
) -> tuple[str, str, str, str]:
    if relation_type not in _SYMMETRIC_RELATIONS:
        return source_type, source_id, target_type, target_id
    left = (source_type, source_id)
    right = (target_type, target_id)
    if left <= right:
        return source_type, source_id, target_type, target_id
    return target_type, target_id, source_type, source_id


def _safe_snippet(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(str(text).split()).strip()
    return cleaned[:220] if cleaned else None


def _load_segments_map(
    db: Any,
    user_id: str,
    segment_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not segment_ids:
        return {}
    rows = (
        db.table("transcript_segments")
        .select("id, conversation_id, start_ms, text")
        .eq("user_id", user_id)
        .in_("id", sorted(segment_ids))
        .execute()
    ).data or []
    return {str(row["id"]): row for row in rows if row.get("id")}


def _load_topic_segment_ids(
    db: Any,
    user_id: str,
    topic_ids: list[str],
) -> dict[str, set[str]]:
    if not topic_ids:
        return {}
    rows = (
        db.table("topic_segment_links")
        .select("topic_id, segment_id")
        .eq("user_id", user_id)
        .in_("topic_id", topic_ids)
        .execute()
    ).data or []
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        topic_id = str(row.get("topic_id") or "")
        segment_id = str(row.get("segment_id") or "")
        if topic_id and segment_id:
            result[topic_id].add(segment_id)
    return result


def _load_entity_segment_ids(
    db: Any,
    user_id: str,
    entity_ids: list[str],
) -> dict[str, set[str]]:
    if not entity_ids:
        return {}
    rows = (
        db.table("entity_segment_links")
        .select("entity_id, segment_id")
        .eq("user_id", user_id)
        .in_("entity_id", entity_ids)
        .execute()
    ).data or []
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        entity_id = str(row.get("entity_id") or "")
        segment_id = str(row.get("segment_id") or "")
        if entity_id and segment_id:
            result[entity_id].add(segment_id)
    return result


def _load_commitment_segment_ids(
    db: Any,
    user_id: str,
    commitment_ids: list[str],
) -> dict[str, set[str]]:
    if not commitment_ids:
        return {}
    rows = (
        db.table("commitment_segment_links")
        .select("commitment_id, segment_id")
        .eq("user_id", user_id)
        .in_("commitment_id", commitment_ids)
        .execute()
    ).data or []
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        commitment_id = str(row.get("commitment_id") or "")
        segment_id = str(row.get("segment_id") or "")
        if commitment_id and segment_id:
            result[commitment_id].add(segment_id)
    return result


def _best_segment_id(
    segment_ids: set[str],
    segment_map: dict[str, dict[str, Any]],
) -> str | None:
    candidates = [
        segment_map[segment_id] for segment_id in segment_ids if segment_id in segment_map
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: (int(row.get("start_ms") or 0), str(row.get("id") or "")))
    return str(candidates[0].get("id") or "")


def _pick_evidence(
    segment_ids: set[str],
    segment_map: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    segment_id = _best_segment_id(segment_ids, segment_map)
    if not segment_id:
        return None, None
    row = segment_map.get(segment_id) or {}
    return segment_id, _safe_snippet(row.get("text"))


def _pick_shared_evidence(
    left_segment_ids: set[str],
    right_segment_ids: set[str],
    segment_map: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    shared = left_segment_ids & right_segment_ids
    if shared:
        return _pick_evidence(shared, segment_map)
    combined = set(left_segment_ids) | set(right_segment_ids)
    return _pick_evidence(combined, segment_map)


def _ensure_knowledge_edge(
    db: Any,
    user_id: str,
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation_type: str,
    confidence: float,
    seen_at: str,
) -> str:
    rows = (
        db.table("knowledge_edges")
        .select("id")
        .eq("user_id", user_id)
        .eq("source_type", source_type)
        .eq("source_id", source_id)
        .eq("target_type", target_type)
        .eq("target_id", target_id)
        .eq("relation_type", relation_type)
        .execute()
    ).data or []
    if rows:
        return str(rows[0].get("id") or "")

    inserted = (
        db.table("knowledge_edges")
        .insert(
            {
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "relation_type": relation_type,
                "confidence": confidence,
                "evidence_count": 0,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            }
        )
        .execute()
    ).data or []
    if not inserted:
        raise RuntimeError("Failed to create knowledge edge")
    return str(inserted[0].get("id") or "")


def _insert_edge_evidence(
    db: Any,
    user_id: str,
    *,
    edge_id: str,
    conversation_id: str,
    segment_id: str | None,
    snippet: str | None,
) -> bool:
    query = (
        db.table("knowledge_edge_evidence")
        .select("id")
        .eq("user_id", user_id)
        .eq("edge_id", edge_id)
        .eq("conversation_id", conversation_id)
    )
    if segment_id:
        query = query.eq("segment_id", segment_id)
    else:
        query = query.is_("segment_id", "null")
    existing = query.execute().data or []
    if existing:
        return False

    inserted = (
        db.table("knowledge_edge_evidence")
        .insert(
            {
                "edge_id": edge_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "segment_id": segment_id,
                "snippet": snippet,
            }
        )
        .execute()
    ).data or []
    return bool(inserted)


def register_knowledge_edge(
    db: Any,
    user_id: str,
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation_type: str,
    confidence: float,
    conversation_id: str,
    segment_id: str | None = None,
    snippet: str | None = None,
    seen_at: str | None = None,
) -> str:
    if relation_type not in _VALID_RELATIONS:
        raise ValueError(f"Unsupported relation_type: {relation_type}")
    if source_type not in _VALID_NODE_TYPES or target_type not in _VALID_NODE_TYPES:
        raise ValueError("Invalid edge endpoint types")

    ordered_source_type, ordered_source_id, ordered_target_type, ordered_target_id = (
        _ordered_edge_endpoints(source_type, source_id, target_type, target_id, relation_type)
    )
    observed_at = seen_at or datetime.now(tz=UTC).isoformat()
    edge_id = _ensure_knowledge_edge(
        db,
        user_id,
        source_type=ordered_source_type,
        source_id=ordered_source_id,
        target_type=ordered_target_type,
        target_id=ordered_target_id,
        relation_type=relation_type,
        confidence=confidence,
        seen_at=observed_at,
    )
    inserted_evidence = _insert_edge_evidence(
        db,
        user_id,
        edge_id=edge_id,
        conversation_id=conversation_id,
        segment_id=segment_id,
        snippet=snippet,
    )
    if inserted_evidence:
        edge_rows = (
            db.table("knowledge_edges")
            .select("evidence_count, first_seen_at, last_seen_at, confidence")
            .eq("user_id", user_id)
            .eq("id", edge_id)
            .execute()
        ).data or []
        edge_row = edge_rows[0] if edge_rows else {}
        first_seen = edge_row.get("first_seen_at") or observed_at
        last_seen = edge_row.get("last_seen_at") or observed_at
        db.table("knowledge_edges").update(
            {
                "evidence_count": int(edge_row.get("evidence_count") or 0) + 1,
                "confidence": max(float(edge_row.get("confidence") or 0.0), confidence),
                "first_seen_at": min(str(first_seen), observed_at),
                "last_seen_at": max(str(last_seen), observed_at),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).eq("id", edge_id).execute()
    return edge_id


def _hydrate_labels(
    db: Any,
    user_id: str,
    refs: list[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    topic_ids = sorted({ref_id for ref_type, ref_id in refs if ref_type == "topic_node"})
    entity_ids = sorted({ref_id for ref_type, ref_id in refs if ref_type == "entity_node"})
    commitment_ids = sorted({ref_id for ref_type, ref_id in refs if ref_type == "commitment"})
    labels: dict[tuple[str, str], str] = {}

    for node_id, label in load_topic_node_label_map(db, user_id, topic_ids).items():
        labels[("topic_node", node_id)] = label
    for node_id, label in load_entity_node_name_map(db, user_id, entity_ids).items():
        labels[("entity_node", node_id)] = label
    if commitment_ids:
        rows = (
            db.table("commitments")
            .select("id, text")
            .eq("user_id", user_id)
            .in_("id", commitment_ids)
            .execute()
        ).data or []
        for row in rows:
            commitment_id = str(row.get("id") or "")
            if commitment_id:
                labels[("commitment", commitment_id)] = str(row.get("text") or "")
    return labels


def _build_relation_context(
    conversation_title: str,
    topic_labels: dict[str, str],
    entity_labels: dict[str, str],
    commitments: list[dict[str, Any]],
    snippets: list[str],
) -> str:
    lines = [f"Conversation: {conversation_title}", "", "Known nodes:"]
    if topic_labels:
        lines.append("Topics:")
        lines.extend(f"- {label} [topic_node]" for label in sorted(topic_labels.values()))
    if entity_labels:
        lines.append("Entities:")
        lines.extend(
            f"- {label} [entity_node]" for label in sorted(entity_labels.values())
        )
    if commitments:
        lines.append("Commitments:")
        for row in commitments:
            lines.append(f"- {row.get('text', '')} [commitment]")
    if snippets:
        lines.append("")
        lines.append("Evidence snippets:")
        lines.extend(f"- {snippet}" for snippet in snippets[:10])
    return "\n".join(lines)


def materialize_conversation_graph(
    db: Any,
    user_id: str,
    conversation_id: str,
) -> dict[str, int]:
    """Materialize deterministic and bounded explicit graph edges for one conversation."""
    conversation_rows = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("user_id", user_id)
        .eq("id", conversation_id)
        .execute()
    ).data or []
    if not conversation_rows:
        return {"edge_count": 0, "evidence_count": 0}
    conversation = conversation_rows[0]
    seen_at = str(conversation.get("meeting_date") or datetime.now(tz=UTC).isoformat())

    topic_rows = (
        db.table("topics")
        .select("id, cluster_id, label")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []
    entity_rows = (
        db.table("entities")
        .select("id, entity_node_id, name, type")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []
    commitment_rows = (
        db.table("commitments")
        .select("id, owner, text")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []

    topic_ids = [str(row.get("id") or "") for row in topic_rows if row.get("id")]
    entity_ids = [str(row.get("id") or "") for row in entity_rows if row.get("id")]
    commitment_ids = [str(row.get("id") or "") for row in commitment_rows if row.get("id")]

    topic_segment_map = _load_topic_segment_ids(db, user_id, topic_ids)
    entity_segment_map = _load_entity_segment_ids(db, user_id, entity_ids)
    commitment_segment_map = _load_commitment_segment_ids(db, user_id, commitment_ids)
    all_segment_ids = set().union(
        *(topic_segment_map.values() or []),
        *(entity_segment_map.values() or []),
        *(commitment_segment_map.values() or []),
    )
    segment_map = _load_segments_map(db, user_id, all_segment_ids)

    topic_segments_by_node: dict[str, set[str]] = defaultdict(set)
    for row in topic_rows:
        node_id = str(row.get("cluster_id") or "")
        topic_id = str(row.get("id") or "")
        if node_id and topic_id:
            topic_segments_by_node[node_id].update(topic_segment_map.get(topic_id, set()))

    entity_segments_by_node: dict[str, set[str]] = defaultdict(set)
    entity_name_by_node: dict[str, str] = {}
    for row in entity_rows:
        node_id = str(row.get("entity_node_id") or "")
        entity_id = str(row.get("id") or "")
        if node_id and entity_id:
            entity_segments_by_node[node_id].update(entity_segment_map.get(entity_id, set()))
            entity_name_by_node.setdefault(node_id, str(row.get("name") or ""))

    edge_ids: set[str] = set()
    evidence_count = 0

    entity_node_ids = sorted(entity_segments_by_node)
    for left_id, right_id in combinations(entity_node_ids, 2):
        segment_id, snippet = _pick_shared_evidence(
            entity_segments_by_node[left_id],
            entity_segments_by_node[right_id],
            segment_map,
        )
        edge_id = register_knowledge_edge(
            db,
            user_id,
            source_type="entity_node",
            source_id=left_id,
            target_type="entity_node",
            target_id=right_id,
            relation_type="co_mentioned",
            confidence=0.9,
            conversation_id=conversation_id,
            segment_id=segment_id,
            snippet=snippet,
            seen_at=seen_at,
        )
        edge_ids.add(edge_id)
        evidence_count += 1

    topic_node_ids = sorted(topic_segments_by_node)
    for topic_node_id in topic_node_ids:
        for entity_node_id in entity_node_ids:
            segment_id, snippet = _pick_shared_evidence(
                topic_segments_by_node[topic_node_id],
                entity_segments_by_node[entity_node_id],
                segment_map,
            )
            edge_id = register_knowledge_edge(
                db,
                user_id,
                source_type="topic_node",
                source_id=topic_node_id,
                target_type="entity_node",
                target_id=entity_node_id,
                relation_type="discussed_in_context",
                confidence=0.88,
                conversation_id=conversation_id,
                segment_id=segment_id,
                snippet=snippet,
                seen_at=seen_at,
            )
            edge_ids.add(edge_id)
            evidence_count += 1

    for commitment_row in commitment_rows:
        commitment_id = str(commitment_row.get("id") or "")
        if not commitment_id:
            continue
        owner_node_id = resolve_entity_node_for_name(
            db,
            user_id,
            str(commitment_row.get("owner") or ""),
            entity_type="person",
        )
        if not owner_node_id:
            continue
        segment_id, snippet = _pick_evidence(
            commitment_segment_map.get(commitment_id, set()),
            segment_map,
        )
        edge_id = register_knowledge_edge(
            db,
            user_id,
            source_type="commitment",
            source_id=commitment_id,
            target_type="entity_node",
            target_id=owner_node_id,
            relation_type="assigned_to",
            confidence=0.95,
            conversation_id=conversation_id,
            segment_id=segment_id,
            snippet=snippet,
            seen_at=seen_at,
        )
        edge_ids.add(edge_id)
        evidence_count += 1

    # Bounded explicit relation extraction from structured context.
    topic_labels = load_topic_node_label_map(db, user_id, topic_node_ids)
    entity_labels = load_entity_node_name_map(db, user_id, entity_node_ids)
    evidence_snippets = [
        snippet
        for _, snippet in (
            _pick_evidence(segment_ids, segment_map)
            for segment_ids in (
                list(topic_segments_by_node.values()) + list(entity_segments_by_node.values())
            )
        )
        if snippet
    ]
    try:
        if topic_labels or entity_labels or commitment_rows:
            relation_context = _build_relation_context(
                str(conversation.get("title") or "Untitled meeting"),
                topic_labels,
                entity_labels,
                commitment_rows,
                evidence_snippets,
            )
            relation_result = llm_client.extract_relations(relation_context)
            topic_id_by_label = {label: node_id for node_id, label in topic_labels.items()}
            entity_id_by_label = {label: node_id for node_id, label in entity_labels.items()}
            commitment_id_by_text = {
                str(row.get("text") or ""): str(row.get("id") or "")
                for row in commitment_rows
                if row.get("id")
            }
            for relation in relation_result.relations:
                if relation.source_type == "topic_node":
                    source_id = topic_id_by_label.get(relation.source_label)
                elif relation.source_type == "entity_node":
                    source_id = entity_id_by_label.get(relation.source_label)
                else:
                    source_id = commitment_id_by_text.get(relation.source_label)

                if relation.target_type == "topic_node":
                    target_id = topic_id_by_label.get(relation.target_label)
                elif relation.target_type == "entity_node":
                    target_id = entity_id_by_label.get(relation.target_label)
                else:
                    target_id = commitment_id_by_text.get(relation.target_label)

                if not source_id or not target_id or source_id == target_id:
                    continue

                edge_id = register_knowledge_edge(
                    db,
                    user_id,
                    source_type=relation.source_type,
                    source_id=source_id,
                    target_type=relation.target_type,
                    target_id=target_id,
                    relation_type=relation.relation_type,
                    confidence=max(relation.confidence, 0.6),
                    conversation_id=conversation_id,
                    snippet=_safe_snippet(relation.evidence_quote),
                    seen_at=seen_at,
                )
                edge_ids.add(edge_id)
                evidence_count += 1
    except Exception as exc:
        # Explicit relation extraction is additive only; deterministic edges remain authoritative.
        logger.info(
            "Explicit relation extraction skipped — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

    return {"edge_count": len(edge_ids), "evidence_count": evidence_count}


def _clear_existing_connections_for_source(
    db: Any,
    user_id: str,
    source_conversation_id: str,
) -> None:
    existing_links = (
        db.table("connection_linked_items")
        .select("connection_id")
        .eq("user_id", user_id)
        .eq("linked_id", source_conversation_id)
        .execute()
    ).data or []
    existing_connection_ids = sorted(
        {str(row.get("connection_id") or "") for row in existing_links if row.get("connection_id")}
    )
    if existing_connection_ids:
        (
            db.table("connections")
            .delete()
            .eq("user_id", user_id)
            .in_("id", existing_connection_ids)
            .execute()
        )


def materialize_connections_for_conversation(
    db: Any,
    user_id: str,
    source_conversation_id: str,
    source_title: str,
) -> list[dict[str, Any]]:
    """Populate the legacy connections read model from canonical nodes and graph edges."""
    materialize_conversation_graph(db, user_id, source_conversation_id)

    source_topics = (
        db.table("topics")
        .select("cluster_id")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .not_.is_("cluster_id", "null")
        .execute()
    ).data or []
    source_topic_node_ids = sorted(
        {str(row.get("cluster_id") or "") for row in source_topics if row.get("cluster_id")}
    )
    source_topic_labels = load_topic_node_label_map(db, user_id, source_topic_node_ids)

    source_entities = (
        db.table("entities")
        .select("entity_node_id")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .not_.is_("entity_node_id", "null")
        .execute()
    ).data or []
    source_entity_node_ids = sorted(
        {
            str(row.get("entity_node_id") or "")
            for row in source_entities
            if row.get("entity_node_id")
        }
    )
    source_entity_labels = load_entity_node_name_map(db, user_id, source_entity_node_ids)

    source_commitments = (
        db.table("commitments")
        .select("id, owner, text")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .execute()
    ).data or []
    source_commitment_sigs = {
        _commitment_signature(row.get("owner"), row.get("text")): str(row.get("text") or "")
        for row in source_commitments
        if _commitment_signature(row.get("owner"), row.get("text"))
    }

    candidate_map: dict[str, _ConnectionCandidate] = {}

    if source_topic_node_ids:
        other_topic_rows = (
            db.table("topics")
            .select("conversation_id, cluster_id")
            .eq("user_id", user_id)
            .in_("cluster_id", source_topic_node_ids)
            .neq("conversation_id", source_conversation_id)
            .execute()
        ).data or []
        for row in other_topic_rows:
            conversation_id = str(row.get("conversation_id") or "")
            node_id = str(row.get("cluster_id") or "")
            if not conversation_id or not node_id:
                continue
            candidate = candidate_map.setdefault(conversation_id, _new_connection_candidate())
            candidate["shared_topics"].add(source_topic_labels.get(node_id, node_id))

    if source_entity_node_ids:
        other_entity_rows = (
            db.table("entities")
            .select("conversation_id, entity_node_id")
            .eq("user_id", user_id)
            .in_("entity_node_id", source_entity_node_ids)
            .neq("conversation_id", source_conversation_id)
            .execute()
        ).data or []
        for row in other_entity_rows:
            conversation_id = str(row.get("conversation_id") or "")
            node_id = str(row.get("entity_node_id") or "")
            if not conversation_id or not node_id:
                continue
            candidate = candidate_map.setdefault(conversation_id, _new_connection_candidate())
            candidate["shared_entities"].add(source_entity_labels.get(node_id, node_id))

    all_other_commitments = (
        db.table("commitments")
        .select("conversation_id, owner, text")
        .eq("user_id", user_id)
        .neq("conversation_id", source_conversation_id)
        .execute()
    ).data or []
    for row in all_other_commitments:
        signature = _commitment_signature(row.get("owner"), row.get("text"))
        if not signature or signature not in source_commitment_sigs:
            continue
        conversation_id = str(row.get("conversation_id") or "")
        if not conversation_id:
            continue
        candidate = candidate_map.setdefault(conversation_id, _new_connection_candidate())
        candidate["shared_commitments"].add(source_commitment_sigs[signature])

    source_edge_ids = (
        db.table("knowledge_edge_evidence")
        .select("edge_id")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .execute()
    ).data or []
    edge_ids = sorted(
        {str(row.get("edge_id") or "") for row in source_edge_ids if row.get("edge_id")}
    )
    if edge_ids:
        other_edge_evidence = (
            db.table("knowledge_edge_evidence")
            .select("conversation_id, edge_id")
            .eq("user_id", user_id)
            .in_("edge_id", edge_ids)
            .neq("conversation_id", source_conversation_id)
            .execute()
        ).data or []
        for row in other_edge_evidence:
            conversation_id = str(row.get("conversation_id") or "")
            if not conversation_id:
                continue
            candidate = candidate_map.setdefault(conversation_id, _new_connection_candidate())
            candidate["graph_matches"] = int(candidate.get("graph_matches") or 0) + 1

    if not candidate_map:
        _clear_existing_connections_for_source(db, user_id, source_conversation_id)
        return []

    candidate_ids = sorted(candidate_map)
    candidate_conversations = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("user_id", user_id)
        .in_("id", candidate_ids)
        .execute()
    ).data or []
    conversation_meta = {
        str(row.get("id") or ""): row for row in candidate_conversations if row.get("id")
    }

    _clear_existing_connections_for_source(db, user_id, source_conversation_id)

    ranked_candidates = sorted(
        candidate_map.items(),
        key=lambda item: (
            len(item[1]["shared_topics"]) * 3
            + len(item[1]["shared_entities"]) * 2
            + len(item[1]["shared_commitments"])
            + int(item[1].get("graph_matches") or 0),
            item[0],
        ),
        reverse=True,
    )[:25]

    output: list[dict[str, Any]] = []
    for conversation_id, signals in ranked_candidates:
        meta = conversation_meta.get(conversation_id)
        if not meta:
            continue

        shared_topics = sorted(str(value) for value in signals["shared_topics"])
        shared_entities = sorted(str(value) for value in signals["shared_entities"])
        shared_commitments = sorted(str(value) for value in signals["shared_commitments"])

        if shared_topics and shared_entities:
            label = "Shared topics and entities"
        elif shared_topics:
            label = "Shared topic thread"
        elif shared_entities:
            label = "Shared entities"
        else:
            label = "Shared graph context"

        summary_parts: list[str] = []
        if shared_topics:
            summary_parts.append(f"shared topics ({', '.join(shared_topics[:3])})")
        if shared_entities:
            summary_parts.append(f"shared entities ({', '.join(shared_entities[:3])})")
        if shared_commitments:
            summary_parts.append("commitment thread overlap")
        if int(signals.get("graph_matches") or 0) > 0:
            summary_parts.append("graph evidence overlap")
        summary_detail = "; ".join(summary_parts) if summary_parts else "context overlap detected"
        summary = (
            f"{source_title} and {meta.get('title', 'this meeting')} are connected through "
            f"{summary_detail}."
        )

        created_connection = (
            db.table("connections")
            .insert(
                {
                    "user_id": user_id,
                    "label": label,
                    "linked_type": "topic" if shared_topics else "conversation",
                    "summary": summary,
                }
            )
            .execute()
        )
        if not created_connection.data:
            continue
        connection_id = str(created_connection.data[0]["id"])

        linked_ids = [source_conversation_id, conversation_id]
        if shared_topics:
            shared_topic_ids = [
                node_id
                for node_id, label_value in source_topic_labels.items()
                if label_value in shared_topics
            ]
            linked_ids.extend(shared_topic_ids)
        deduped_linked_ids = sorted(set(linked_ids))
        db.table("connection_linked_items").insert(
            [
                {"connection_id": connection_id, "linked_id": linked_id, "user_id": user_id}
                for linked_id in deduped_linked_ids
            ]
        ).execute()

        output.append(
            {
                "id": connection_id,
                "linked_type": "topic" if shared_topics else "conversation",
                "label": label,
                "summary": summary,
                "connected_conversation_id": conversation_id,
                "connected_conversation_title": str(meta.get("title") or "Untitled meeting"),
                "connected_meeting_date": meta.get("meeting_date"),
                "shared_topics": shared_topics,
                "shared_entities": shared_entities,
                "shared_commitments": shared_commitments,
            }
        )

    return output


def get_neighbors(
    db: Any,
    user_id: str,
    node_type: str,
    node_id: str,
) -> list[dict[str, Any]]:
    source_edges = (
        db.table("knowledge_edges")
        .select(
            "id, source_type, source_id, target_type, target_id, relation_type, confidence, "
            "evidence_count, first_seen_at, last_seen_at"
        )
        .eq("user_id", user_id)
        .eq("source_type", node_type)
        .eq("source_id", node_id)
        .execute()
    ).data or []
    target_edges = (
        db.table("knowledge_edges")
        .select(
            "id, source_type, source_id, target_type, target_id, relation_type, confidence, "
            "evidence_count, first_seen_at, last_seen_at"
        )
        .eq("user_id", user_id)
        .eq("target_type", node_type)
        .eq("target_id", node_id)
        .execute()
    ).data or []
    rows = source_edges + target_edges
    refs = [
        (str(row.get("source_type") or ""), str(row.get("source_id") or ""))
        for row in rows
    ] + [
        (str(row.get("target_type") or ""), str(row.get("target_id") or ""))
        for row in rows
    ]
    labels = _hydrate_labels(db, user_id, refs)
    evidence_rows = (
        db.table("knowledge_edge_evidence")
        .select("edge_id, conversation_id, segment_id, snippet")
        .eq("user_id", user_id)
        .in_("edge_id", [str(row.get("id") or "") for row in rows if row.get("id")])
        .execute()
    ).data or []
    evidence_by_edge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        edge_id = str(row.get("edge_id") or "")
        if edge_id:
            evidence_by_edge[edge_id].append(dict(row))
    return [
        {
            "edge_id": str(row.get("id") or ""),
            "source": {
                "type": str(row.get("source_type") or ""),
                "id": str(row.get("source_id") or ""),
                "label": labels.get(
                    (str(row.get("source_type") or ""), str(row.get("source_id") or "")),
                    "",
                ),
            },
            "target": {
                "type": str(row.get("target_type") or ""),
                "id": str(row.get("target_id") or ""),
                "label": labels.get(
                    (str(row.get("target_type") or ""), str(row.get("target_id") or "")),
                    "",
                ),
            },
            "relation_type": str(row.get("relation_type") or ""),
            "confidence": float(row.get("confidence") or 0.0),
            "evidence_count": int(row.get("evidence_count") or 0),
            "first_seen_at": row.get("first_seen_at"),
            "last_seen_at": row.get("last_seen_at"),
            "evidence": evidence_by_edge.get(str(row.get("id") or ""), [])[:5],
        }
        for row in rows
    ]


def get_subgraph_for_conversation(
    db: Any,
    user_id: str,
    conversation_id: str,
) -> dict[str, list[dict[str, Any]]]:
    evidence_rows = (
        db.table("knowledge_edge_evidence")
        .select("edge_id, conversation_id, segment_id, snippet")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []
    edge_ids = sorted(
        {str(row.get("edge_id") or "") for row in evidence_rows if row.get("edge_id")}
    )
    if not edge_ids:
        return {"nodes": [], "edges": []}
    edge_rows = (
        db.table("knowledge_edges")
        .select(
            "id, source_type, source_id, target_type, target_id, relation_type, confidence, "
            "evidence_count, first_seen_at, last_seen_at"
        )
        .eq("user_id", user_id)
        .in_("id", edge_ids)
        .execute()
    ).data or []
    refs = [
        (str(row.get("source_type") or ""), str(row.get("source_id") or ""))
        for row in edge_rows
    ] + [
        (str(row.get("target_type") or ""), str(row.get("target_id") or ""))
        for row in edge_rows
    ]
    labels = _hydrate_labels(db, user_id, refs)
    nodes = [
        {"type": ref_type, "id": ref_id, "label": labels.get((ref_type, ref_id), "")}
        for ref_type, ref_id in sorted(set(refs))
    ]
    return {
        "nodes": nodes,
        "edges": [
            {
                "id": str(row.get("id") or ""),
                "source_type": str(row.get("source_type") or ""),
                "source_id": str(row.get("source_id") or ""),
                "target_type": str(row.get("target_type") or ""),
                "target_id": str(row.get("target_id") or ""),
                "relation_type": str(row.get("relation_type") or ""),
                "confidence": float(row.get("confidence") or 0.0),
                "evidence_count": int(row.get("evidence_count") or 0),
                "evidence": [
                    dict(evidence_row)
                    for evidence_row in evidence_rows
                    if str(evidence_row.get("edge_id") or "") == str(row.get("id") or "")
                ],
            }
            for row in edge_rows
        ],
    }


def _resolve_node_ref(db: Any, user_id: str, node_id: str) -> tuple[str, str] | None:
    topic_rows = (
        db.table("topic_clusters").select("id").eq("user_id", user_id).eq("id", node_id).execute()
    ).data or []
    if topic_rows:
        return ("topic_node", node_id)
    entity_rows = (
        db.table("entity_nodes").select("id").eq("user_id", user_id).eq("id", node_id).execute()
    ).data or []
    if entity_rows:
        return ("entity_node", node_id)
    commitment_rows = (
        db.table("commitments").select("id").eq("user_id", user_id).eq("id", node_id).execute()
    ).data or []
    if commitment_rows:
        return ("commitment", node_id)
    return None


def find_path(
    db: Any,
    user_id: str,
    from_node_id: str,
    to_node_id: str,
) -> dict[str, list[dict[str, Any]]]:
    start_ref = _resolve_node_ref(db, user_id, from_node_id)
    end_ref = _resolve_node_ref(db, user_id, to_node_id)
    if not start_ref or not end_ref:
        return {"nodes": [], "edges": []}

    edge_rows = (
        db.table("knowledge_edges")
        .select(
            "id, source_type, source_id, target_type, target_id, relation_type, "
            "confidence, evidence_count"
        )
        .eq("user_id", user_id)
        .execute()
    ).data or []
    adjacency: dict[
        tuple[str, str],
        list[tuple[tuple[str, str], dict[str, Any]]],
    ] = defaultdict(list)
    for row in edge_rows:
        source = (str(row.get("source_type") or ""), str(row.get("source_id") or ""))
        target = (str(row.get("target_type") or ""), str(row.get("target_id") or ""))
        adjacency[source].append((target, row))
        adjacency[target].append((source, row))

    queue: deque[tuple[str, str]] = deque([start_ref])
    previous: dict[tuple[str, str], tuple[tuple[str, str], dict[str, Any]]] = {}
    visited = {start_ref}
    while queue:
        current = queue.popleft()
        if current == end_ref:
            break
        for neighbor, edge_row in adjacency.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            previous[neighbor] = (current, edge_row)
            queue.append(neighbor)

    if end_ref not in visited:
        return {"nodes": [], "edges": []}

    path_nodes: list[tuple[str, str]] = []
    path_edges: list[dict[str, Any]] = []
    cursor = end_ref
    while cursor != start_ref:
        path_nodes.append(cursor)
        parent, edge_row = previous[cursor]
        path_edges.append(edge_row)
        cursor = parent
    path_nodes.append(start_ref)
    path_nodes.reverse()
    path_edges.reverse()

    labels = _hydrate_labels(db, user_id, path_nodes)
    return {
        "nodes": [
            {"type": ref_type, "id": ref_id, "label": labels.get((ref_type, ref_id), "")}
            for ref_type, ref_id in path_nodes
        ],
        "edges": [dict(row) for row in path_edges],
    }


def backfill_knowledge_graph_for_user(
    db: Any,
    user_id: str,
) -> dict[str, int]:
    conversation_rows = (
        db.table("conversations")
        .select("id, title")
        .eq("user_id", user_id)
        .order("meeting_date")
        .execute()
    ).data or []
    conversations_processed = 0
    edge_count = 0
    evidence_count = 0
    for row in conversation_rows:
        conversation_id = str(row.get("id") or "")
        if not conversation_id:
            continue
        graph_counts = materialize_conversation_graph(db, user_id, conversation_id)
        materialize_connections_for_conversation(
            db,
            user_id,
            conversation_id,
            str(row.get("title") or "This meeting"),
        )
        conversations_processed += 1
        edge_count += graph_counts["edge_count"]
        evidence_count += graph_counts["evidence_count"]
    return {
        "conversations_processed": conversations_processed,
        "edge_count": edge_count,
        "evidence_count": evidence_count,
    }
