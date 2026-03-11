"""
Topics routes.

GET /topics           — list all topics across all conversations (newest conversation first)
GET /topics/{id}      — single topic with key quotes and source conversations
GET /topics/{id}/arc  — topic arc timeline with segment citations
"""

import logging
from datetime import UTC, datetime
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


class TopicSummary(BaseModel):
    id: str
    label: str
    conversation_count: int
    latest_date: str | None


class TopicConversation(BaseModel):
    id: str
    title: str
    meeting_date: str


class TopicDetail(BaseModel):
    id: str
    label: str
    summary: str
    key_quotes: list[str]
    conversations: list[TopicConversation]


class TopicArcPoint(BaseModel):
    topic_id: str
    conversation_id: str
    conversation_title: str
    occurred_at: str
    summary: str
    topic_status: str
    citation_segment_id: str | None
    transcript_offset_seconds: int | None
    citation_snippet: str | None


class TopicArcDetail(BaseModel):
    id: str
    topic_id: str
    label: str
    summary: str
    status: str
    trend: str
    conversation_count: int
    arc_points: list[TopicArcPoint]


def _normalize_status(value: str | None) -> str:
    return "resolved" if value == "resolved" else "open"


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _format_date_label(value: str | None) -> str:
    parsed = _parse_iso_timestamp(value)
    if not parsed:
        return "unknown date"
    return parsed.date().isoformat()


def _build_and_store_topic_arc(
    db: Any,
    user_id: str,
    topic_id: str,
) -> TopicArcDetail:
    base_topic_result = (
        db.table("topics")
        .select("id, label, summary, status, conversation_id, created_at")
        .eq("id", topic_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not base_topic_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    base_topic = base_topic_result.data[0]

    base_label = base_topic.get("label", "")
    related_topics_result = (
        db.table("topics")
        .select("id, label, summary, status, conversation_id, created_at")
        .eq("user_id", user_id)
        .ilike("label", base_label)
        .execute()
    )
    related_topics = related_topics_result.data or [base_topic]
    if not any(str(row.get("id")) == str(topic_id) for row in related_topics):
        related_topics.append(base_topic)

    topic_ids = [str(row["id"]) for row in related_topics if row.get("id")]
    conversation_ids = list(
        {str(row["conversation_id"]) for row in related_topics if row.get("conversation_id")}
    )

    conversation_map: dict[str, dict[str, Any]] = {}
    if conversation_ids:
        conversation_result = (
            db.table("conversations")
            .select("id, title, meeting_date")
            .eq("user_id", user_id)
            .in_("id", conversation_ids)
            .execute()
        )
        conversation_map = {str(row["id"]): row for row in (conversation_result.data or [])}

    topic_to_segment_ids: dict[str, list[str]] = {}
    if topic_ids:
        link_result = (
            db.table("topic_segment_links")
            .select("topic_id, segment_id")
            .eq("user_id", user_id)
            .in_("topic_id", topic_ids)
            .execute()
        )
        for row in link_result.data or []:
            current_topic_id = str(row.get("topic_id", ""))
            current_segment_id = str(row.get("segment_id", ""))
            if not current_topic_id or not current_segment_id:
                continue
            topic_to_segment_ids.setdefault(current_topic_id, []).append(current_segment_id)

    segment_map: dict[str, dict[str, Any]] = {}
    all_segment_ids = sorted(
        {segment_id for segment_ids in topic_to_segment_ids.values() for segment_id in segment_ids}
    )
    if all_segment_ids:
        segment_result = (
            db.table("transcript_segments")
            .select("id, start_ms, text")
            .eq("user_id", user_id)
            .in_("id", all_segment_ids)
            .execute()
        )
        segment_map = {str(row["id"]): row for row in (segment_result.data or [])}

    raw_points: list[TopicArcPoint] = []
    for topic_row in related_topics:
        current_topic_id = str(topic_row.get("id", ""))
        conversation_id = str(topic_row.get("conversation_id", ""))
        conversation = conversation_map.get(conversation_id, {})
        segment_ids = topic_to_segment_ids.get(current_topic_id, [])
        sorted_segments = sorted(
            (segment_map[segment_id] for segment_id in segment_ids if segment_id in segment_map),
            key=lambda row: row.get("start_ms") or 0,
        )
        primary_segment = sorted_segments[0] if sorted_segments else None

        snippet: str | None = None
        offset_seconds: int | None = None
        citation_segment_id: str | None = None
        if primary_segment:
            text_value = (primary_segment.get("text") or "").strip()
            snippet = text_value[:220] if text_value else None
            start_ms = primary_segment.get("start_ms")
            if isinstance(start_ms, int):
                offset_seconds = start_ms // 1000
            segment_id = primary_segment.get("id")
            citation_segment_id = str(segment_id) if segment_id else None

        occurred_at = str(
            conversation.get("meeting_date")
            or topic_row.get("created_at")
            or base_topic.get("created_at")
            or ""
        )

        raw_points.append(
            TopicArcPoint(
                topic_id=current_topic_id,
                conversation_id=conversation_id,
                conversation_title=str(conversation.get("title") or "Untitled meeting"),
                occurred_at=occurred_at,
                summary=str(topic_row.get("summary") or ""),
                topic_status=_normalize_status(topic_row.get("status")),
                citation_segment_id=citation_segment_id,
                transcript_offset_seconds=offset_seconds,
                citation_snippet=snippet,
            )
        )

    raw_points.sort(
        key=lambda point: (
            _parse_iso_timestamp(point.occurred_at) or datetime.min.replace(tzinfo=UTC)
        )
    )

    arc_points: list[TopicArcPoint] = []
    seen_conversations: set[str] = set()
    for point in raw_points:
        if point.conversation_id in seen_conversations:
            continue
        seen_conversations.add(point.conversation_id)
        arc_points.append(point)

    overall_status = (
        "resolved"
        if arc_points and all(point.topic_status == "resolved" for point in arc_points)
        else "open"
    )
    if overall_status == "resolved":
        trend = "resolved"
    elif len(arc_points) >= 3:
        trend = "growing"
    else:
        trend = "stable"

    if not arc_points:
        arc_summary = f"{base_label} has not been linked to indexed meetings yet."
    elif len(arc_points) == 1:
        arc_summary = f"{base_label} has appeared in one meeting so far."
    else:
        first_seen = _format_date_label(arc_points[0].occurred_at)
        last_seen = _format_date_label(arc_points[-1].occurred_at)
        arc_summary = (
            f"{base_label} appears across {len(arc_points)} meetings from "
            f"{first_seen} to {last_seen}."
        )

    existing_arc_result = (
        db.table("topic_arcs")
        .select("id")
        .eq("topic_id", topic_id)
        .eq("user_id", user_id)
        .execute()
    )
    existing_arc = existing_arc_result.data or []

    if existing_arc:
        arc_id = str(existing_arc[0]["id"])
        (
            db.table("topic_arcs")
            .update({"summary": arc_summary, "trend": trend})
            .eq("id", arc_id)
            .eq("user_id", user_id)
            .execute()
        )
    else:
        created_arc = (
            db.table("topic_arcs")
            .insert(
                {
                    "user_id": user_id,
                    "topic_id": topic_id,
                    "summary": arc_summary,
                    "trend": trend,
                }
            )
            .execute()
        )
        if not created_arc.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create topic arc",
            )
        arc_id = str(created_arc.data[0]["id"])

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
                        "conversation_id": point.conversation_id,
                        "user_id": user_id,
                    }
                    for point in arc_points
                ]
            )
            .execute()
        )

    return TopicArcDetail(
        id=arc_id,
        topic_id=topic_id,
        label=base_label,
        summary=arc_summary,
        status=overall_status,
        trend=trend,
        conversation_count=len(arc_points),
        arc_points=arc_points,
    )


# ---------------------------------------------------------------------------
# GET /topics
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[TopicSummary],
    summary="List all topics across all conversations",
)
def list_topics(
    limit: int = 100,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[TopicSummary]:
    """Return all topics for the current user, newest conversation first."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    topics_result = (
        db.table("topics")
        .select("id, label, conversation_id, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    topics = topics_result.data or []
    if not topics:
        return []

    # Fetch conversation meeting_date for latest_date
    conv_ids = list({t["conversation_id"] for t in topics})
    convs_result = (
        db.table("conversations")
        .select("id, meeting_date")
        .eq("user_id", user_id)
        .in_("id", conv_ids)
        .execute()
    )
    conv_date_map = {c["id"]: c.get("meeting_date") for c in (convs_result.data or [])}

    return [
        TopicSummary(
            id=t["id"],
            label=t["label"],
            conversation_count=1,
            latest_date=conv_date_map.get(t["conversation_id"]),
        )
        for t in topics
    ]


# ---------------------------------------------------------------------------
# GET /topics/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{topic_id}",
    response_model=TopicDetail,
    summary="Get a single topic with its source conversations",
)
def get_topic(
    topic_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TopicDetail:
    """Return a single topic with its key quotes and source conversations."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    topic_result = (
        db.table("topics")
        .select("id, label, summary, key_quotes, conversation_id")
        .eq("id", topic_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not topic_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    t = topic_result.data[0]

    conv_result = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("id", t["conversation_id"])
        .eq("user_id", user_id)
        .execute()
    )
    conv = conv_result.data[0] if conv_result.data else {}
    conversations = (
        [
            TopicConversation(
                id=conv["id"],
                title=conv.get("title", ""),
                meeting_date=conv.get("meeting_date", ""),
            )
        ]
        if conv
        else []
    )

    return TopicDetail(
        id=t["id"],
        label=t["label"],
        summary=t["summary"],
        key_quotes=t.get("key_quotes") or [],
        conversations=conversations,
    )


# ---------------------------------------------------------------------------
# GET /topics/{id}/arc
# ---------------------------------------------------------------------------


@router.get(
    "/{topic_id}/arc",
    response_model=TopicArcDetail,
    summary="Get topic arc timeline with citation metadata",
)
def get_topic_arc(
    topic_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TopicArcDetail:
    """Compute and persist a topic arc for the current user's topic."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    arc = _build_and_store_topic_arc(db=db, user_id=user_id, topic_id=topic_id)
    point_count = len(arc.arc_points) if isinstance(arc, TopicArcDetail) else len(arc["arc_points"])
    logger.info(
        "Topic arc computed — topic_id=%s user=%s points=%d",
        topic_id,
        user_id,
        point_count,
    )
    return arc
