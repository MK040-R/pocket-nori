"""Durable entity node helpers.

This module owns:
- entity node assignment at ingestion/backfill time
- entity node metadata refresh from member entity mentions
- canonical entity node loading for read routes
- entity-node search rows for semantic retrieval

No read route calls merge logic. Semantic merge checks are limited to write-time
resolution when lexical identity is insufficient.
"""

# ruff: noqa: S608

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src import llm_client
from src.database import get_direct_connection
from src.entity_utils import clean_entity_name

ENTITY_NODE_TABLE = "entity_nodes"
ENTITY_NODE_FOREIGN_KEY_COLUMN = "entity_node_id"
ENTITY_NODE_NAME_COLUMN = "canonical_name"
ENTITY_NODE_TYPE_COLUMN = "entity_type"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_BRAND_LIKE_TYPES = {"company", "product"}
_ENTITY_TYPE_COMPATIBILITY: dict[str, set[str]] = {
    "person": {"person"},
    "project": {"project"},
    "company": {"company", "product"},
    "product": {"company", "product"},
}


@dataclass(slots=True)
class EntityNodeSnapshot:
    canonical_name: str
    entity_type: str
    mention_count: int
    first_mentioned_at: str
    last_mentioned_at: str


@dataclass(slots=True)
class StoredEntityNode:
    id: str
    name: str
    entity_type: str
    mention_count: int
    first_mentioned_at: str
    last_mentioned_at: str
    conversation_ids: list[str]
    entity_ids: list[str]
    rows: list[dict[str, Any]]


def _normalize_phrase(value: str | None) -> str:
    cleaned = clean_entity_name(value).lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _compact_key(value: str | None) -> str:
    return "".join(_TOKEN_RE.findall(_normalize_phrase(value)))


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(_normalize_phrase(value)))


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


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(tz=UTC).isoformat()
    return value.isoformat()


def _compatible_types(entity_type: str) -> set[str]:
    return _ENTITY_TYPE_COMPATIBILITY.get(entity_type, {entity_type})


def _is_compatible_type(left: str, right: str) -> bool:
    return right in _compatible_types(left) or left in _compatible_types(right)


def _node_sort_key(node: dict[str, Any]) -> tuple[int, datetime, str]:
    return (
        int(node.get("mention_count") or 0),
        _parse_datetime(node.get("last_mentioned_at")) or datetime.min.replace(tzinfo=UTC),
        str(node.get("canonical_name") or "").lower(),
    )


def _choose_canonical_name(rows: list[dict[str, Any]]) -> str:
    scored = sorted(
        (
            (
                int(row.get("mentions") or 0),
                len(_tokens(row.get("name"))),
                len(clean_entity_name(str(row.get("name") or ""))),
                clean_entity_name(str(row.get("name") or "")),
            )
            for row in rows
            if clean_entity_name(str(row.get("name") or ""))
        ),
        reverse=True,
    )
    if not scored:
        return ""
    return scored[0][3]


def _dominant_entity_type(rows: list[dict[str, Any]]) -> str:
    counts: Counter[str] = Counter()
    for row in rows:
        entity_type = str(row.get("type") or "").strip()
        if not entity_type:
            continue
        counts[entity_type] += int(row.get("mentions") or 0)
    if not counts:
        return "project"
    return counts.most_common(1)[0][0]


def _build_entity_node_snapshot(rows: list[dict[str, Any]]) -> EntityNodeSnapshot:
    sorted_rows = sorted(rows, key=_sort_key_for_row, reverse=True)
    timestamps = [
        _parse_datetime(row.get("meeting_date") or row.get("created_at")) for row in sorted_rows
    ]
    values = [value for value in timestamps if value is not None]
    return EntityNodeSnapshot(
        canonical_name=_choose_canonical_name(sorted_rows),
        entity_type=_dominant_entity_type(sorted_rows),
        mention_count=sum(int(row.get("mentions") or 0) for row in sorted_rows),
        first_mentioned_at=_serialize_datetime(min(values) if values else None),
        last_mentioned_at=_serialize_datetime(max(values) if values else None),
    )


def _load_entity_node_rows(
    db: Any,
    user_id: str,
    node_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.table(ENTITY_NODE_TABLE)
        .select(
            "id, canonical_name, entity_type, mention_count, first_mentioned_at, "
            "last_mentioned_at, created_at, updated_at"
        )
        .eq("user_id", user_id)
    )
    if node_ids is not None:
        if not node_ids:
            return []
        query = query.in_("id", node_ids)
    return query.order("last_mentioned_at", desc=True).execute().data or []


def _load_entity_member_rows(
    db: Any,
    user_id: str,
    node_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.table("entities")
        .select("id, entity_node_id, name, type, mentions, conversation_id, created_at")
        .eq("user_id", user_id)
    )
    if node_ids is not None:
        if not node_ids:
            return []
        query = query.in_("entity_node_id", node_ids)
    else:
        query = query.not_.is_("entity_node_id", "null")

    entity_rows = query.order("created_at", desc=True).execute().data or []
    if not entity_rows:
        return []

    conversation_ids = sorted(
        {str(row["conversation_id"]) for row in entity_rows if row.get("conversation_id")}
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
        for row in entity_rows
    ]


def _build_stored_entity_node(
    node_row: dict[str, Any],
    member_rows: list[dict[str, Any]],
) -> StoredEntityNode:
    snapshot = _build_entity_node_snapshot(member_rows)
    conversation_ids = sorted(
        {str(row.get("conversation_id") or "") for row in member_rows if row.get("conversation_id")}
    )
    entity_ids = [str(row.get("id") or "") for row in member_rows if row.get("id")]
    return StoredEntityNode(
        id=str(node_row.get("id") or ""),
        name=str(node_row.get("canonical_name") or snapshot.canonical_name),
        entity_type=str(node_row.get("entity_type") or snapshot.entity_type),
        mention_count=int(node_row.get("mention_count") or snapshot.mention_count),
        first_mentioned_at=str(
            node_row.get("first_mentioned_at") or snapshot.first_mentioned_at
        ),
        last_mentioned_at=str(node_row.get("last_mentioned_at") or snapshot.last_mentioned_at),
        conversation_ids=conversation_ids,
        entity_ids=entity_ids,
        rows=sorted(member_rows, key=_sort_key_for_row, reverse=True),
    )


def load_entity_nodes(
    db: Any,
    user_id: str,
    *,
    min_conversations: int = 1,
    limit: int | None = None,
    offset: int = 0,
) -> list[StoredEntityNode]:
    node_rows = _load_entity_node_rows(db, user_id)
    if not node_rows:
        return []

    node_ids = [str(row.get("id") or "") for row in node_rows if row.get("id")]
    member_rows = _load_entity_member_rows(db, user_id, node_ids)
    rows_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in member_rows:
        node_id = str(row.get("entity_node_id") or "")
        if node_id:
            rows_by_node[node_id].append(row)

    nodes: list[StoredEntityNode] = []
    for node_row in node_rows:
        node_id = str(node_row.get("id") or "")
        members = rows_by_node.get(node_id, [])
        if not members:
            continue
        node = _build_stored_entity_node(node_row, members)
        if len(node.conversation_ids) < min_conversations:
            continue
        nodes.append(node)

    nodes.sort(
        key=lambda node: (
            _parse_datetime(node.last_mentioned_at) or datetime.min.replace(tzinfo=UTC),
            node.name.lower(),
        ),
        reverse=True,
    )
    visible = nodes[offset:]
    if limit is not None:
        visible = visible[:limit]
    return visible


def load_entity_node_registry(db: Any, user_id: str) -> list[dict[str, Any]]:
    return _load_entity_node_rows(db, user_id)


def load_entity_node(db: Any, user_id: str, entity_or_node_id: str) -> StoredEntityNode | None:
    node_id = resolve_entity_node_id(db, user_id, entity_or_node_id)
    if not node_id:
        return None
    nodes = load_entity_nodes(db, user_id)
    for node in nodes:
        if node.id == node_id:
            return node
    return None


def resolve_entity_node_id(db: Any, user_id: str, entity_or_node_id: str) -> str | None:
    node_rows = (
        db.table(ENTITY_NODE_TABLE)
        .select("id")
        .eq("user_id", user_id)
        .eq("id", entity_or_node_id)
        .execute()
    ).data or []
    if node_rows:
        return str(node_rows[0].get("id") or "")

    entity_rows = (
        db.table("entities")
        .select("entity_node_id")
        .eq("user_id", user_id)
        .eq("id", entity_or_node_id)
        .execute()
    ).data or []
    if entity_rows and entity_rows[0].get("entity_node_id"):
        return str(entity_rows[0]["entity_node_id"])
    return None


def load_entity_node_name_map(
    db: Any,
    user_id: str,
    node_ids: list[str],
) -> dict[str, str]:
    if not node_ids:
        return {}
    rows = (
        db.table(ENTITY_NODE_TABLE)
        .select("id, canonical_name")
        .eq("user_id", user_id)
        .in_("id", node_ids)
        .execute()
    ).data or []
    return {
        str(row["id"]): str(row.get("canonical_name") or "")
        for row in rows
        if row.get("id")
    }


def _find_lexical_entity_node_id(
    name: str,
    entity_type: str,
    nodes: list[dict[str, Any]],
) -> str | None:
    cleaned = clean_entity_name(name)
    normalized = _normalize_phrase(cleaned)
    compact = _compact_key(cleaned)
    token_list = _tokens(cleaned)

    exact_matches = sorted(
        (
            node
            for node in nodes
            if _is_compatible_type(entity_type, str(node.get("entity_type") or ""))
            and (
                _normalize_phrase(str(node.get("canonical_name") or "")) == normalized
                or (
                    entity_type in _BRAND_LIKE_TYPES
                    and _compact_key(str(node.get("canonical_name") or "")) == compact
                )
            )
        ),
        key=_node_sort_key,
        reverse=True,
    )
    if exact_matches:
        return str(exact_matches[0].get("id") or "")

    if entity_type == "person" and len(token_list) == 1 and len(token_list[0]) >= 4:
        token = token_list[0]
        person_candidates = [
            node
            for node in nodes
            if str(node.get("entity_type") or "") == "person"
            and len(_tokens(str(node.get("canonical_name") or ""))) >= 2
            and token in _tokens(str(node.get("canonical_name") or ""))
        ]
        if len(person_candidates) == 1:
            return str(person_candidates[0].get("id") or "")

    return None


def _candidate_entity_nodes(
    name: str,
    entity_type: str,
    nodes: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    normalized = _normalize_phrase(name)
    compact = _compact_key(name)
    token_list = set(_tokens(name))
    scored: list[tuple[int, int, int, datetime, dict[str, Any]]] = []

    for node in nodes:
        node_type = str(node.get("entity_type") or "")
        if not _is_compatible_type(entity_type, node_type):
            continue
        node_name = str(node.get("canonical_name") or "")
        node_normalized = _normalize_phrase(node_name)
        node_tokens = set(_tokens(node_name))
        overlap = len(token_list & node_tokens)
        brand_match = int(
            entity_type in _BRAND_LIKE_TYPES
            and compact
            and compact == _compact_key(node_name)
        )
        substring_match = int(
            bool(normalized)
            and (
                normalized in node_normalized
                or node_normalized in normalized
            )
        )
        if overlap == 0 and brand_match == 0 and substring_match == 0:
            continue
        scored.append(
            (
                brand_match,
                overlap,
                substring_match,
                _parse_datetime(node.get("last_mentioned_at"))
                or datetime.min.replace(tzinfo=UTC),
                node,
            )
        )

    scored.sort(reverse=True)
    return [candidate[-1] for candidate in scored[:max_candidates]]


def _find_embedding_candidate_ids(
    user_id: str,
    name: str,
    entity_type: str,
    *,
    limit: int,
    min_score: float,
) -> list[str]:
    try:
        vector = llm_client.embed_texts([f"{clean_entity_name(name)} ({entity_type})"])[0]
    except Exception:
        return []

    vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
    compatible_types = sorted(_compatible_types(entity_type))
    sql = f"""
        SELECT id
        FROM {ENTITY_NODE_TABLE}
        WHERE user_id = %s
          AND entity_type = ANY(%s)
          AND embedding IS NOT NULL
          AND 1 - (embedding <=> %s::vector) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    conn = get_direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                [user_id, compatible_types, vector_literal, min_score, vector_literal, limit],
            )
            return [str(row["id"]) for row in cur.fetchall() if row.get("id")]
    finally:
        conn.close()


def _find_semantic_entity_node_id(
    user_id: str,
    name: str,
    entity_type: str,
    nodes: list[dict[str, Any]],
    *,
    max_candidates: int = 6,
    semantic_budget: dict[str, int] | None = None,
    use_embedding_candidates: bool = False,
) -> str | None:
    candidates = _candidate_entity_nodes(name, entity_type, nodes, max_candidates=max_candidates)
    if use_embedding_candidates:
        embedding_candidate_ids = set(
            _find_embedding_candidate_ids(
                user_id,
                name,
                entity_type,
                limit=max_candidates,
                min_score=0.72,
            )
        )
        if embedding_candidate_ids:
            candidate_map = {str(node.get("id") or ""): node for node in nodes}
            for candidate_id in embedding_candidate_ids:
                candidate = candidate_map.get(candidate_id)
                if candidate and candidate not in candidates:
                    candidates.append(candidate)

    for candidate in candidates[:max_candidates]:
        if semantic_budget is not None:
            limit = semantic_budget.get("limit", 0)
            used = semantic_budget.get("used", 0)
            if used >= limit:
                return None
            semantic_budget["used"] = used + 1
        if llm_client.check_entity_merge(
            name,
            entity_type,
            str(candidate.get("canonical_name") or ""),
            str(candidate.get("entity_type") or ""),
        ):
            return str(candidate.get("id") or "")
    return None


def _create_entity_node(
    db: Any,
    user_id: str,
    *,
    name: str,
    entity_type: str,
    mentions: int,
    mentioned_at: str,
) -> dict[str, Any]:
    inserted = (
        db.table(ENTITY_NODE_TABLE)
        .insert(
            {
                "user_id": user_id,
                "canonical_name": clean_entity_name(name),
                "entity_type": entity_type,
                "mention_count": max(int(mentions or 0), 1),
                "first_mentioned_at": mentioned_at,
                "last_mentioned_at": mentioned_at,
            }
        )
        .execute()
    ).data or []
    if not inserted:
        raise RuntimeError("Failed to create entity node")
    return dict(inserted[0])


def assign_node_for_entity(
    db: Any,
    user_id: str,
    *,
    entity_row: dict[str, Any],
    nodes: list[dict[str, Any]],
    enable_semantic: bool = True,
    semantic_budget: dict[str, int] | None = None,
    use_embedding_candidates: bool = False,
) -> str:
    name = clean_entity_name(str(entity_row.get("name") or ""))
    entity_type = str(entity_row.get("type") or "").strip()
    mentions = int(entity_row.get("mentions") or 1)
    mentioned_at = str(entity_row.get("meeting_date") or entity_row.get("created_at") or "")

    lexical_node_id = _find_lexical_entity_node_id(name, entity_type, nodes)
    if lexical_node_id:
        return lexical_node_id

    if enable_semantic:
        semantic_node_id = _find_semantic_entity_node_id(
            user_id,
            name,
            entity_type,
            nodes,
            semantic_budget=semantic_budget,
            use_embedding_candidates=use_embedding_candidates,
        )
        if semantic_node_id:
            return semantic_node_id

    created = _create_entity_node(
        db,
        user_id,
        name=name,
        entity_type=entity_type,
        mentions=mentions,
        mentioned_at=mentioned_at or datetime.now(tz=UTC).isoformat(),
    )
    nodes.append(created)
    return str(created.get("id") or "")


def refresh_entity_node_metadata(
    db: Any,
    user_id: str,
    node_id: str,
) -> StoredEntityNode | None:
    member_rows = _load_entity_member_rows(db, user_id, [node_id])
    if not member_rows:
        (db.table(ENTITY_NODE_TABLE).delete().eq("user_id", user_id).eq("id", node_id).execute())
        return None

    snapshot = _build_entity_node_snapshot(member_rows)
    updated_rows = (
        db.table(ENTITY_NODE_TABLE)
        .update(
            {
                "canonical_name": snapshot.canonical_name,
                "entity_type": snapshot.entity_type,
                "mention_count": snapshot.mention_count,
                "first_mentioned_at": snapshot.first_mentioned_at,
                "last_mentioned_at": snapshot.last_mentioned_at,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        .eq("user_id", user_id)
        .eq("id", node_id)
        .execute()
    ).data or []
    node_row = updated_rows[0] if updated_rows else {"id": node_id}
    return _build_stored_entity_node(node_row, member_rows)


def refresh_entity_nodes_metadata(
    db: Any,
    user_id: str,
    node_ids: set[str] | list[str],
) -> list[StoredEntityNode]:
    refreshed: list[StoredEntityNode] = []
    for node_id in sorted({node_id for node_id in node_ids if node_id}):
        node = refresh_entity_node_metadata(db, user_id, node_id)
        if node is not None:
            refreshed.append(node)
    return refreshed


def clear_user_entity_nodes(db: Any, user_id: str) -> None:
    (db.table("entities").update({"entity_node_id": None}).eq("user_id", user_id).execute())
    (db.table(ENTITY_NODE_TABLE).delete().eq("user_id", user_id).execute())


def load_rebuild_entity_source_rows(db: Any, user_id: str) -> list[dict[str, Any]]:
    entity_rows = (
        db.table("entities")
        .select("id, name, type, mentions, conversation_id, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    ).data or []
    if not entity_rows:
        return []

    conversation_ids = sorted(
        {str(row["conversation_id"]) for row in entity_rows if row.get("conversation_id")}
    )
    conversation_rows: list[dict[str, Any]] = []
    if conversation_ids:
        conversation_rows = (
            db.table("conversations")
            .select("id, meeting_date")
            .eq("user_id", user_id)
            .in_("id", conversation_ids)
            .execute()
        ).data or []
    conversation_map = {str(row["id"]): row for row in conversation_rows if row.get("id")}

    return [
        {
            **row,
            "name": clean_entity_name(str(row.get("name") or "")),
            "meeting_date": conversation_map.get(str(row.get("conversation_id") or ""), {}).get(
                "meeting_date"
            ),
        }
        for row in entity_rows
        if row.get("id") and clean_entity_name(str(row.get("name") or ""))
    ]


def assign_nodes_to_existing_entities(
    db: Any,
    user_id: str,
    entity_rows: list[dict[str, Any]],
    *,
    enable_semantic: bool = True,
    semantic_budget: dict[str, int] | None = None,
    use_embedding_candidates: bool = False,
) -> set[str]:
    nodes = load_entity_node_registry(db, user_id)
    affected_node_ids: set[str] = set()
    for row in entity_rows:
        node_id = assign_node_for_entity(
            db,
            user_id,
            entity_row=row,
            nodes=nodes,
            enable_semantic=enable_semantic,
            semantic_budget=semantic_budget,
            use_embedding_candidates=use_embedding_candidates,
        )
        affected_node_ids.add(node_id)
        row["entity_node_id"] = node_id
        (
            db.table("entities")
            .update({"entity_node_id": node_id})
            .eq("user_id", user_id)
            .eq("id", str(row.get("id") or ""))
            .execute()
        )
    return affected_node_ids


def _entity_identity_candidates(
    rebuilt_nodes: list[StoredEntityNode],
    previous_nodes: list[StoredEntityNode],
) -> list[tuple[int, int, int, float, str, str]]:
    candidates: list[tuple[int, int, int, float, str, str]] = []
    for rebuilt in rebuilt_nodes:
        rebuilt_entity_ids = {entity_id for entity_id in rebuilt.entity_ids if entity_id}
        if not rebuilt_entity_ids:
            continue
        rebuilt_name = _normalize_phrase(rebuilt.name)
        rebuilt_last = _parse_datetime(rebuilt.last_mentioned_at) or datetime.min.replace(
            tzinfo=UTC
        )
        for previous in previous_nodes:
            previous_entity_ids = {entity_id for entity_id in previous.entity_ids if entity_id}
            overlap = len(rebuilt_entity_ids & previous_entity_ids)
            if overlap == 0:
                continue
            exact_name = int(rebuilt_name == _normalize_phrase(previous.name))
            same_type = int(rebuilt.entity_type == previous.entity_type)
            recency_score = (
                rebuilt_last.timestamp()
                if rebuilt_last != datetime.min.replace(tzinfo=UTC)
                else float("-inf")
            )
            candidates.append(
                (
                    overlap,
                    exact_name,
                    same_type,
                    recency_score,
                    rebuilt.id,
                    previous.id,
                )
            )
    candidates.sort(reverse=True)
    return candidates


def _insert_entity_node_with_id(
    db: Any,
    user_id: str,
    *,
    node_id: str,
    node: StoredEntityNode,
) -> None:
    (
        db.table(ENTITY_NODE_TABLE)
        .insert(
            {
                "id": node_id,
                "user_id": user_id,
                "canonical_name": node.name,
                "entity_type": node.entity_type,
                "mention_count": node.mention_count,
                "first_mentioned_at": node.first_mentioned_at,
                "last_mentioned_at": node.last_mentioned_at,
            }
        )
        .execute()
    )


def stabilize_rebuilt_entity_node_ids(
    db: Any,
    user_id: str,
    previous_nodes: list[StoredEntityNode],
) -> set[str]:
    rebuilt_nodes = load_entity_nodes(db, user_id)
    if not rebuilt_nodes:
        return set()
    if not previous_nodes:
        return {node.id for node in rebuilt_nodes}

    rebuilt_by_id = {node.id: node for node in rebuilt_nodes}
    final_node_ids = set(rebuilt_by_id)
    assigned_rebuilt: set[str] = set()
    assigned_previous: set[str] = set()

    for _, _, _, _, rebuilt_id, previous_id in _entity_identity_candidates(
        rebuilt_nodes,
        previous_nodes,
    ):
        if rebuilt_id in assigned_rebuilt or previous_id in assigned_previous:
            continue
        if rebuilt_id == previous_id:
            assigned_rebuilt.add(rebuilt_id)
            assigned_previous.add(previous_id)
            continue

        rebuilt_node = rebuilt_by_id.get(rebuilt_id)
        if rebuilt_node is None:
            continue

        _insert_entity_node_with_id(
            db,
            user_id,
            node_id=previous_id,
            node=rebuilt_node,
        )
        (
            db.table("entities")
            .update({"entity_node_id": previous_id})
            .eq("user_id", user_id)
            .eq("entity_node_id", rebuilt_id)
            .execute()
        )
        (db.table(ENTITY_NODE_TABLE).delete().eq("user_id", user_id).eq("id", rebuilt_id).execute())

        assigned_rebuilt.add(rebuilt_id)
        assigned_previous.add(previous_id)
        final_node_ids.discard(rebuilt_id)
        final_node_ids.add(previous_id)

    return final_node_ids


def resolve_entity_node_for_name(
    db: Any,
    user_id: str,
    name: str,
    *,
    entity_type: str = "person",
) -> str | None:
    nodes = load_entity_node_registry(db, user_id)
    return _find_lexical_entity_node_id(name, entity_type, nodes)


def search_entity_node_rows(
    user_id: str,
    query_vector: list[float],
    limit: int,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    score_threshold: float = 0.30,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
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
        SELECT DISTINCT ON (en.id)
            en.id AS result_id,
            en.canonical_name AS title,
            en.entity_type AS text,
            c.id AS conversation_id,
            c.title AS conversation_title,
            c.meeting_date AS meeting_date,
            1 - (en.embedding <=> %s::vector) AS score
        FROM {ENTITY_NODE_TABLE} en
        JOIN entities e
          ON e.entity_node_id = en.id
         AND e.user_id = %s
        JOIN conversations c
          ON c.id = e.conversation_id
         AND c.user_id = %s
        WHERE en.user_id = %s
          AND en.embedding IS NOT NULL
          AND 1 - (en.embedding <=> %s::vector) >= %s
          {' '.join(date_clauses)}
        ORDER BY en.id, c.meeting_date DESC, score DESC
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
    "ENTITY_NODE_FOREIGN_KEY_COLUMN",
    "ENTITY_NODE_NAME_COLUMN",
    "ENTITY_NODE_TABLE",
    "ENTITY_NODE_TYPE_COLUMN",
    "EntityNodeSnapshot",
    "StoredEntityNode",
    "assign_node_for_entity",
    "assign_nodes_to_existing_entities",
    "clear_user_entity_nodes",
    "load_entity_node",
    "load_entity_node_name_map",
    "load_entity_node_registry",
    "load_entity_nodes",
    "load_rebuild_entity_source_rows",
    "refresh_entity_node_metadata",
    "refresh_entity_nodes_metadata",
    "resolve_entity_node_for_name",
    "resolve_entity_node_id",
    "search_entity_node_rows",
    "stabilize_rebuilt_entity_node_ids",
]
