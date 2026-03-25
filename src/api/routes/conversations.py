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
from src.api.schema_guards import feature_unavailable, is_missing_schema_feature
from src.database import get_client
from src.knowledge_graph import materialize_connections_for_conversation
from src.topic_node_store import (
    TOPIC_NODE_FOREIGN_KEY_COLUMN,
    load_topic_node_label_map,
)

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


def _category_schema_missing(exc: Exception) -> bool:
    return is_missing_schema_feature(exc, "conversations", "category")


def _execute_conversation_list_query(
    db: Any,
    user_id: str,
    limit: int,
    offset: int,
    *,
    include_category: bool,
    category: str | None,
) -> Any:
    selected_columns = "id, title, source, meeting_date, duration_seconds, status"
    if include_category:
        selected_columns = f"{selected_columns}, category"

    query = (
        db.table("conversations")
        .select(selected_columns)
        .eq("user_id", user_id)
        .order("meeting_date", desc=True)
        .range(offset, offset + limit - 1)
    )
    if category:
        query = query.eq("category", category)
    return query.execute()


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
    rows = materialize_connections_for_conversation(
        db,
        user_id,
        source_conversation_id,
        source_title,
    )
    return [ConversationConnection.model_validate(row) for row in rows]


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

    category_available = True
    try:
        result = _execute_conversation_list_query(
            db,
            user_id,
            limit,
            offset,
            include_category=True,
            category=category,
        )
    except Exception as exc:
        if not _category_schema_missing(exc):
            raise
        if category:
            raise feature_unavailable("Meeting categories are not available yet.") from exc
        category_available = False
        result = _execute_conversation_list_query(
            db,
            user_id,
            limit,
            offset,
            include_category=False,
            category=None,
        )
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
            category=row.get("category") if category_available else None,
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
    category_available = True
    try:
        conv_result = (
            db.table("conversations")
            .select("id, title, source, meeting_date, duration_seconds, status, category")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        if not _category_schema_missing(exc):
            raise
        category_available = False
        conv_result = (
            db.table("conversations")
            .select("id, title, source, meeting_date, duration_seconds, status")
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
        .select(f"id, {TOPIC_NODE_FOREIGN_KEY_COLUMN}, label, summary, status, key_quotes")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    topic_rows = topics_result.data or []
    topic_node_ids = sorted(
        {
            str(row[TOPIC_NODE_FOREIGN_KEY_COLUMN])
            for row in topic_rows
            if row.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) is not None
        }
    )
    topic_node_label_by_id = load_topic_node_label_map(db, user_id, topic_node_ids)

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
            category=conv.get("category") if category_available else None,
        ),
        topics=[
            TopicOut(
                id=str(t.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) or t["id"]),
                label=topic_node_label_by_id.get(
                    str(t.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) or ""), t["label"]
                ),
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

    try:
        update_result = (
            db.table("conversations")
            .update({"category": body.category})
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        if _category_schema_missing(exc):
            raise feature_unavailable("Meeting categories are not available yet.") from exc
        raise
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
