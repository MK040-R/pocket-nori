"""
Topics routes.

GET /topics           — list all topics across all conversations (newest conversation first)
GET /topics/{id}      — single topic with key quotes and source conversations
"""

import logging
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
        [TopicConversation(
            id=conv["id"],
            title=conv.get("title", ""),
            meeting_date=conv.get("meeting_date", ""),
        )]
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
