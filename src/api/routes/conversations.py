"""
Conversations routes — list and detail views.

GET /conversations            — paginated list of the user's conversations
GET /conversations/{id}       — full conversation detail with topics, commitments,
                                entities, and transcript segments
GET /conversations/{id}/connections — detect and return cross-meeting connections
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


_VALID_CATEGORIES = {"strategy", "client", "1on1", "agency", "partner", "team", "other"}


class ConversationSummary(BaseModel):
    id: str
    title: str
    source: str
    meeting_date: str
    duration_seconds: int | None
    status: str  # "processing" | "indexed"
    latest_brief_id: str | None = None
    latest_brief_generated_at: str | None = None
    topic_labels: list[str] = []
    category: str | None = None


class TopicOut(BaseModel):
    id: str
    label: str
    summary: str
    status: str
    key_quotes: list[str]


class CommitmentOut(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    status: str
    action_type: str = "commitment"


class EntityOut(BaseModel):
    id: str
    name: str
    type: str
    mentions: int


class SegmentOut(BaseModel):
    id: str
    speaker_id: str
    start_ms: int
    end_ms: int
    text: str


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    topics: list[TopicOut]
    commitments: list[CommitmentOut]
    entities: list[EntityOut]
    segments: list[SegmentOut]
    connections: list[Any]  # Connection details are served via /conversations/{id}/connections


class ConversationConnection(BaseModel):
    id: str
    linked_type: str
    label: str
    summary: str
    connected_conversation_id: str
    connected_conversation_title: str
    connected_meeting_date: str | None
    shared_topics: list[str]
    shared_entities: list[str]
    shared_commitments: list[str]


class ConnectionsResponse(BaseModel):
    connections: list[ConversationConnection]


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


def _normalize_phrase(value: str | None) -> str:
    if not value:
        return ""
    collapsed = " ".join(value.lower().strip().split())
    return collapsed


def _commitment_signature(owner: str | None, text: str | None) -> str:
    owner_norm = _normalize_phrase(owner)
    tokens = [token for token in _TOKEN_RE.findall((text or "").lower()) if token not in _STOPWORDS]
    if not owner_norm or not tokens:
        return ""
    return f"{owner_norm}:{'-'.join(tokens[:6])}"


def _describe_shared(
    shared_topics: list[str],
    shared_entities: list[str],
    shared_commitments: list[str],
) -> str:
    parts: list[str] = []
    if shared_topics:
        parts.append(f"shared topics ({', '.join(shared_topics[:3])})")
    if shared_entities:
        parts.append(f"shared entities ({', '.join(shared_entities[:3])})")
    if shared_commitments:
        parts.append("commitment thread overlap")
    return "; ".join(parts) if parts else "context overlap detected"


def _new_candidate_signals() -> dict[str, set[str]]:
    return {
        "topic_ids": set(),
        "shared_topics": set(),
        "shared_entities": set(),
        "shared_commitments": set(),
    }


def _compute_and_store_connections(
    db: Any,
    user_id: str,
    source_conversation_id: str,
    source_title: str,
) -> list[ConversationConnection]:
    source_topics_result = (
        db.table("topics")
        .select("id, label")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .execute()
    )
    source_entities_result = (
        db.table("entities")
        .select("id, name")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .execute()
    )
    source_commitments_result = (
        db.table("commitments")
        .select("id, owner, text")
        .eq("user_id", user_id)
        .eq("conversation_id", source_conversation_id)
        .execute()
    )

    source_topics = source_topics_result.data or []
    source_entities = source_entities_result.data or []
    source_commitments = source_commitments_result.data or []

    source_topic_labels = {
        _normalize_phrase(str(row.get("label", ""))): str(row.get("label", ""))
        for row in source_topics
        if row.get("label")
    }
    source_entity_names = {
        _normalize_phrase(str(row.get("name", ""))): str(row.get("name", ""))
        for row in source_entities
        if row.get("name")
    }
    source_commitment_sigs = {
        _commitment_signature(row.get("owner"), row.get("text")): str(row.get("text", ""))
        for row in source_commitments
        if _commitment_signature(row.get("owner"), row.get("text"))
    }

    all_other_topics = (
        db.table("topics")
        .select("id, conversation_id, label")
        .eq("user_id", user_id)
        .neq("conversation_id", source_conversation_id)
        .execute()
    ).data or []
    all_other_entities = (
        db.table("entities")
        .select("id, conversation_id, name")
        .eq("user_id", user_id)
        .neq("conversation_id", source_conversation_id)
        .execute()
    ).data or []
    all_other_commitments = (
        db.table("commitments")
        .select("id, conversation_id, owner, text")
        .eq("user_id", user_id)
        .neq("conversation_id", source_conversation_id)
        .execute()
    ).data or []

    candidate_map: dict[str, dict[str, Any]] = {}

    for row in all_other_topics:
        normalized = _normalize_phrase(str(row.get("label", "")))
        if not normalized or normalized not in source_topic_labels:
            continue
        conversation_id = str(row.get("conversation_id", ""))
        if not conversation_id:
            continue
        candidate = candidate_map.setdefault(conversation_id, _new_candidate_signals())
        topic_id = str(row.get("id", ""))
        if topic_id:
            candidate["topic_ids"].add(topic_id)
        candidate["shared_topics"].add(source_topic_labels[normalized])

    for row in all_other_entities:
        normalized = _normalize_phrase(str(row.get("name", "")))
        if not normalized or normalized not in source_entity_names:
            continue
        conversation_id = str(row.get("conversation_id", ""))
        if not conversation_id:
            continue
        candidate = candidate_map.setdefault(conversation_id, _new_candidate_signals())
        candidate["shared_entities"].add(source_entity_names[normalized])

    for row in all_other_commitments:
        signature = _commitment_signature(row.get("owner"), row.get("text"))
        if not signature or signature not in source_commitment_sigs:
            continue
        conversation_id = str(row.get("conversation_id", ""))
        if not conversation_id:
            continue
        candidate = candidate_map.setdefault(conversation_id, _new_candidate_signals())
        candidate["shared_commitments"].add(source_commitment_sigs[signature])

    if not candidate_map:
        existing_links = (
            db.table("connection_linked_items")
            .select("connection_id")
            .eq("user_id", user_id)
            .eq("linked_id", source_conversation_id)
            .execute()
        ).data or []
        existing_connection_ids = sorted(
            {
                str(row.get("connection_id", ""))
                for row in existing_links
                if row.get("connection_id")
            }
        )
        if existing_connection_ids:
            (
                db.table("connections")
                .delete()
                .eq("user_id", user_id)
                .in_("id", existing_connection_ids)
                .execute()
            )
        return []

    candidate_ids = sorted(candidate_map.keys())
    candidate_conversations = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("user_id", user_id)
        .in_("id", candidate_ids)
        .execute()
    ).data or []
    conversation_meta = {str(row["id"]): row for row in candidate_conversations}

    existing_links = (
        db.table("connection_linked_items")
        .select("connection_id")
        .eq("user_id", user_id)
        .eq("linked_id", source_conversation_id)
        .execute()
    ).data or []
    existing_connection_ids = sorted(
        {str(row.get("connection_id", "")) for row in existing_links if row.get("connection_id")}
    )
    if existing_connection_ids:
        (
            db.table("connections")
            .delete()
            .eq("user_id", user_id)
            .in_("id", existing_connection_ids)
            .execute()
        )

    ranked_candidates = sorted(
        candidate_map.items(),
        key=lambda item: (
            len(item[1]["shared_topics"]) * 3
            + len(item[1]["shared_entities"]) * 2
            + len(item[1]["shared_commitments"]),
            item[0],
        ),
        reverse=True,
    )[:25]

    output: list[ConversationConnection] = []
    for conversation_id, signals in ranked_candidates:
        meta = conversation_meta.get(conversation_id)
        if not meta:
            continue

        shared_topics = sorted(str(value) for value in signals["shared_topics"])
        shared_entities = sorted(str(value) for value in signals["shared_entities"])
        shared_commitments = sorted(str(value) for value in signals["shared_commitments"])
        topic_ids = sorted(str(value) for value in signals["topic_ids"])

        if shared_topics and shared_entities:
            label = "Shared topics and entities"
        elif shared_topics:
            label = "Shared topic thread"
        elif shared_entities:
            label = "Shared entities"
        else:
            label = "Commitment thread overlap"

        summary = (
            f"{source_title} and {meta.get('title', 'this meeting')} are connected through "
            f"{_describe_shared(shared_topics, shared_entities, shared_commitments)}."
        )
        linked_type = "topic" if topic_ids else "conversation"

        created_connection = (
            db.table("connections")
            .insert(
                {
                    "user_id": user_id,
                    "label": label,
                    "linked_type": linked_type,
                    "summary": summary,
                }
            )
            .execute()
        )
        if not created_connection.data:
            continue

        connection_id = str(created_connection.data[0]["id"])
        linked_ids = [source_conversation_id, conversation_id, *topic_ids]
        deduped_linked_ids = sorted(set(linked_ids))
        db.table("connection_linked_items").insert(
            [
                {"connection_id": connection_id, "linked_id": linked_id, "user_id": user_id}
                for linked_id in deduped_linked_ids
            ]
        ).execute()

        output.append(
            ConversationConnection(
                id=connection_id,
                linked_type=linked_type,
                label=label,
                summary=summary,
                connected_conversation_id=conversation_id,
                connected_conversation_title=str(meta.get("title") or "Untitled meeting"),
                connected_meeting_date=meta.get("meeting_date"),
                shared_topics=shared_topics,
                shared_entities=shared_entities,
                shared_commitments=shared_commitments,
            )
        )

    return output


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ConversationSummary],
    summary="List all conversations for the current user",
)
def list_conversations(
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[ConversationSummary]:
    """Return a paginated list of conversations, newest first.

    Each item includes the conversation's current processing status
    (``processing`` until AI extraction completes, then ``indexed``).
    Optional ``category`` filter accepts one of: strategy, client, 1on1,
    agency, partner, team, other.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    if category and category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of: {', '.join(sorted(_VALID_CATEGORIES))}",
        )

    query = (
        db.table("conversations")
        .select("id, title, source, meeting_date, duration_seconds, status, category")
        .eq("user_id", user_id)
        .order("meeting_date", desc=True)
        .range(offset, offset + limit - 1)
    )
    if category:
        query = query.eq("category", category)

    result = query.execute()
    rows = result.data or []

    # Fetch up to 3 topic labels per conversation in a single query.
    labels_by_conv: dict[str, list[str]] = {}
    if rows:
        conv_ids = [str(row["id"]) for row in rows]
        topic_rows = (
            db.table("topics")
            .select("conversation_id, label")
            .eq("user_id", user_id)
            .in_("conversation_id", conv_ids)
            .order("created_at", desc=True)
            .execute()
        ).data or []
        for t in topic_rows:
            cid = str(t.get("conversation_id", ""))
            lbl = str(t.get("label", "") or "").strip()
            if cid and lbl:
                bucket = labels_by_conv.setdefault(cid, [])
                if len(bucket) < 3:
                    bucket.append(lbl)

    return [
        ConversationSummary(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            meeting_date=row["meeting_date"],
            duration_seconds=row.get("duration_seconds"),
            status=row.get("status", "processing"),
            latest_brief_id=None,
            latest_brief_generated_at=None,
            topic_labels=labels_by_conv.get(str(row["id"]), []),
            category=row.get("category"),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /conversations/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get full detail for a single conversation",
)
def get_conversation(
    conversation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ConversationDetail:
    """Return a conversation with its topics, commitments, entities, and segments.

    Topics, commitments, and entities are only present once extraction completes
    (conversation.status == 'indexed'). While status is 'processing', those lists
    are empty.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    # --- Conversation ---
    conv_result = (
        db.table("conversations")
        .select("id, title, source, meeting_date, duration_seconds, status, category")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conv_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    conv = conv_result.data[0]

    # --- Topics ---
    topics_result = (
        db.table("topics")
        .select("id, cluster_id, label, summary, status, key_quotes")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    topic_rows = topics_result.data or []
    cluster_ids = sorted(
        {str(row["cluster_id"]) for row in topic_rows if row.get("cluster_id") is not None}
    )
    cluster_rows: list[dict[str, Any]] = []
    if cluster_ids:
        cluster_rows = (
            db.table("topic_clusters")
            .select("id, canonical_label")
            .eq("user_id", user_id)
            .in_("id", cluster_ids)
            .execute()
        ).data or []
    cluster_label_by_id = {
        str(row["id"]): str(row.get("canonical_label") or "")
        for row in cluster_rows
        if row.get("id")
    }

    # --- Commitments ---
    commitments_result = (
        db.table("commitments")
        .select("id, text, owner, due_date, status, action_type")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )

    # --- Entities ---
    entities_result = (
        db.table("entities")
        .select("id, name, type, mentions")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("mentions", desc=True)
        .execute()
    )

    # --- Transcript segments ---
    segments_result = (
        db.table("transcript_segments")
        .select("id, speaker_id, start_ms, end_ms, text")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("start_ms")
        .execute()
    )

    latest_brief_rows = (
        db.table("briefs")
        .select("id, generated_at")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    latest_brief = latest_brief_rows[0] if latest_brief_rows else None

    return ConversationDetail(
        conversation=ConversationSummary(
            id=conv["id"],
            title=conv["title"],
            source=conv["source"],
            meeting_date=conv["meeting_date"],
            duration_seconds=conv.get("duration_seconds"),
            status=conv.get("status", "processing"),
            latest_brief_id=(
                str(latest_brief["id"]) if latest_brief and latest_brief.get("id") else None
            ),
            latest_brief_generated_at=(
                str(latest_brief["generated_at"])
                if latest_brief and latest_brief.get("generated_at")
                else None
            ),
            category=conv.get("category"),
        ),
        topics=[
            TopicOut(
                id=str(t.get("cluster_id") or t["id"]),
                label=cluster_label_by_id.get(str(t.get("cluster_id") or ""), t["label"]),
                summary=t["summary"],
                status=t["status"],
                key_quotes=t.get("key_quotes") or [],
            )
            for t in topic_rows
        ],
        commitments=[
            CommitmentOut(
                id=c["id"],
                text=c["text"],
                owner=c["owner"],
                due_date=c.get("due_date"),
                status=c["status"],
                action_type=c.get("action_type") or "commitment",
            )
            for c in (commitments_result.data or [])
        ],
        entities=[
            EntityOut(
                id=e["id"],
                name=e["name"],
                type=e["type"],
                mentions=e["mentions"],
            )
            for e in (entities_result.data or [])
        ],
        segments=[
            SegmentOut(
                id=s["id"],
                speaker_id=s["speaker_id"],
                start_ms=s["start_ms"],
                end_ms=s["end_ms"],
                text=s["text"],
            )
            for s in (segments_result.data or [])
        ],
        connections=[],
    )


# ---------------------------------------------------------------------------
# PATCH /conversations/{id} — update category
# ---------------------------------------------------------------------------


class ConversationPatch(BaseModel):
    category: str


@router.patch(
    "/{conversation_id}",
    response_model=ConversationSummary,
    summary="Update conversation metadata (category)",
)
def update_conversation(
    conversation_id: str,
    body: ConversationPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ConversationSummary:
    """Update a conversation's category. Accepts one of the valid category values."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    if body.category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of: {', '.join(sorted(_VALID_CATEGORIES))}",
        )

    existing = (
        db.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    update_result = (
        db.table("conversations")
        .update({"category": body.category})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not update_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation",
        )

    updated = update_result.data[0]
    logger.info(
        "Conversation %s category updated to %s — user=%s",
        conversation_id,
        body.category,
        user_id,
    )

    return ConversationSummary(
        id=str(updated["id"]),
        title=str(updated.get("title", "")),
        source=str(updated.get("source", "")),
        meeting_date=str(updated.get("meeting_date", "")),
        duration_seconds=updated.get("duration_seconds"),
        status=str(updated.get("status", "processing")),
        category=updated.get("category"),
    )


# ---------------------------------------------------------------------------
# GET /conversations/{id}/connections
# ---------------------------------------------------------------------------


@router.get(
    "/{conversation_id}/connections",
    response_model=ConnectionsResponse,
    summary="Detect and return connections for a conversation",
)
def get_connections(
    conversation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ConnectionsResponse:
    """Detect and persist cross-meeting connections for a conversation."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    conversation_result = (
        db.table("conversations")
        .select("id, title")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conversation_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    conversation = conversation_result.data[0]

    connections = _compute_and_store_connections(
        db=db,
        user_id=user_id,
        source_conversation_id=conversation_id,
        source_title=str(conversation.get("title") or "This meeting"),
    )
    logger.info(
        "Connections computed — conversation=%s user=%s count=%d",
        conversation_id,
        user_id,
        len(connections),
    )
    return ConnectionsResponse(connections=connections)
