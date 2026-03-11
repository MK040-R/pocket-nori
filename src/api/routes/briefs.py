"""
Brief routes.

GET /briefs/{brief_id}  — return full brief detail with citation segments.
GET /briefs/latest      — resolve latest brief by conversation_id or calendar_event_id.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client

router = APIRouter()


class BriefTopicArcOut(BaseModel):
    id: str
    topic_id: str
    summary: str
    trend: str


class BriefCommitmentOut(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    status: str


class BriefConnectionOut(BaseModel):
    id: str
    label: str
    summary: str
    linked_type: str


class BriefCitationOut(BaseModel):
    segment_id: str
    conversation_id: str
    speaker_id: str
    start_ms: int
    text: str


class BriefDetailOut(BaseModel):
    id: str
    conversation_id: str
    calendar_event_id: str | None
    content: str
    generated_at: str
    topic_arcs: list[BriefTopicArcOut]
    commitments: list[BriefCommitmentOut]
    connections: list[BriefConnectionOut]
    citations: list[BriefCitationOut]


class BriefLatestOut(BaseModel):
    brief_id: str
    generated_at: str
    preview: str


def _collect_citation_segments(
    db: Any,
    user_id: str,
    topic_arc_rows: list[dict[str, Any]],
    commitment_rows: list[dict[str, Any]],
) -> list[BriefCitationOut]:
    topic_ids = [str(row["topic_id"]) for row in topic_arc_rows if row.get("topic_id")]
    commitment_ids = [str(row["id"]) for row in commitment_rows if row.get("id")]

    segment_ids: set[str] = set()
    if topic_ids:
        topic_segment_rows = (
            db.table("topic_segment_links")
            .select("segment_id")
            .eq("user_id", user_id)
            .in_("topic_id", topic_ids)
            .execute()
        ).data or []
        for row in topic_segment_rows:
            segment_id = row.get("segment_id")
            if segment_id:
                segment_ids.add(str(segment_id))

    if commitment_ids:
        commitment_segment_rows = (
            db.table("commitment_segment_links")
            .select("segment_id")
            .eq("user_id", user_id)
            .in_("commitment_id", commitment_ids)
            .execute()
        ).data or []
        for row in commitment_segment_rows:
            segment_id = row.get("segment_id")
            if segment_id:
                segment_ids.add(str(segment_id))

    if not segment_ids:
        return []

    segment_rows = (
        db.table("transcript_segments")
        .select("id, conversation_id, speaker_id, start_ms, text")
        .eq("user_id", user_id)
        .in_("id", sorted(segment_ids))
        .order("start_ms")
        .execute()
    ).data or []

    return [
        BriefCitationOut(
            segment_id=str(row.get("id", "")),
            conversation_id=str(row.get("conversation_id", "")),
            speaker_id=str(row.get("speaker_id", "")),
            start_ms=int(row.get("start_ms", 0)),
            text=str(row.get("text", "")),
        )
        for row in segment_rows
    ]


@router.get(
    "/latest",
    response_model=BriefLatestOut,
    summary="Resolve the latest brief by conversation or calendar event",
)
def get_latest_brief(
    conversation_id: str | None = Query(default=None),
    calendar_event_id: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> BriefLatestOut:
    if not conversation_id and not calendar_event_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="conversation_id or calendar_event_id is required",
        )

    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    query = db.table("briefs").select("id, generated_at, content").eq("user_id", user_id)
    if conversation_id:
        query = query.eq("conversation_id", conversation_id)
    if calendar_event_id:
        query = query.eq("calendar_event_id", calendar_event_id)

    rows = query.order("generated_at", desc=True).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    row = rows[0]
    content = str(row.get("content", ""))
    preview = content[:220].strip()
    if len(content) > 220:
        preview = f"{preview}..."
    return BriefLatestOut(
        brief_id=str(row.get("id", "")),
        generated_at=str(row.get("generated_at", "")),
        preview=preview,
    )


@router.get(
    "/{brief_id}",
    response_model=BriefDetailOut,
    summary="Get a generated brief with supporting citations",
)
def get_brief(
    brief_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> BriefDetailOut:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    brief_rows = (
        db.table("briefs")
        .select("id, conversation_id, calendar_event_id, content, generated_at")
        .eq("id", brief_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    if not brief_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    brief = brief_rows[0]

    topic_arc_link_rows = (
        db.table("brief_topic_arc_links")
        .select("topic_arc_id")
        .eq("brief_id", brief_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    topic_arc_ids = [
        str(row["topic_arc_id"]) for row in topic_arc_link_rows if row.get("topic_arc_id")
    ]

    commitment_link_rows = (
        db.table("brief_commitment_links")
        .select("commitment_id")
        .eq("brief_id", brief_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    commitment_ids = [
        str(row["commitment_id"]) for row in commitment_link_rows if row.get("commitment_id")
    ]

    connection_link_rows = (
        db.table("brief_connection_links")
        .select("connection_id")
        .eq("brief_id", brief_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    connection_ids = [
        str(row["connection_id"]) for row in connection_link_rows if row.get("connection_id")
    ]

    topic_arc_rows: list[dict[str, Any]]
    if topic_arc_ids:
        topic_arc_rows = (
            db.table("topic_arcs")
            .select("id, topic_id, summary, trend")
            .eq("user_id", user_id)
            .in_("id", topic_arc_ids)
            .execute()
        ).data or []
    else:
        topic_arc_rows = []

    commitment_rows: list[dict[str, Any]]
    if commitment_ids:
        commitment_rows = (
            db.table("commitments")
            .select("id, text, owner, due_date, status")
            .eq("user_id", user_id)
            .in_("id", commitment_ids)
            .execute()
        ).data or []
    else:
        commitment_rows = []

    connection_rows: list[dict[str, Any]]
    if connection_ids:
        connection_rows = (
            db.table("connections")
            .select("id, label, summary, linked_type")
            .eq("user_id", user_id)
            .in_("id", connection_ids)
            .execute()
        ).data or []
    else:
        connection_rows = []

    citations = _collect_citation_segments(db, user_id, topic_arc_rows, commitment_rows)

    return BriefDetailOut(
        id=str(brief.get("id", "")),
        conversation_id=str(brief.get("conversation_id", "")),
        calendar_event_id=(
            str(brief["calendar_event_id"]) if brief.get("calendar_event_id") is not None else None
        ),
        content=str(brief.get("content", "")),
        generated_at=str(brief.get("generated_at", "")),
        topic_arcs=[
            BriefTopicArcOut(
                id=str(row.get("id", "")),
                topic_id=str(row.get("topic_id", "")),
                summary=str(row.get("summary", "")),
                trend=str(row.get("trend", "")),
            )
            for row in topic_arc_rows
        ],
        commitments=[
            BriefCommitmentOut(
                id=str(row.get("id", "")),
                text=str(row.get("text", "")),
                owner=str(row.get("owner", "")),
                due_date=str(row["due_date"]) if row.get("due_date") is not None else None,
                status=str(row.get("status", "")),
            )
            for row in commitment_rows
        ],
        connections=[
            BriefConnectionOut(
                id=str(row.get("id", "")),
                label=str(row.get("label", "")),
                summary=str(row.get("summary", "")),
                linked_type=str(row.get("linked_type", "")),
            )
            for row in connection_rows
        ],
        citations=citations,
    )
