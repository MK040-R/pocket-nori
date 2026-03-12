"""
Index stats route.

GET /index/stats — return counts and last-updated timestamp from the user's index
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client
from src.topic_utils import cluster_topic_rows

logger = logging.getLogger(__name__)

router = APIRouter()


class IndexStats(BaseModel):
    conversation_count: int
    topic_count: int
    commitment_count: int
    entity_count: int
    last_updated_at: str | None


@router.get(
    "/stats",
    response_model=IndexStats,
    summary="Return counts and last-updated time from the user's index",
)
def get_index_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> IndexStats:
    """Return aggregate counts for the current user's intelligence index.

    Counts are computed live for MVP so the dashboard matches the visible UI.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    index_result = (
        db.table("user_index")
        .select("conversation_count, topic_count, commitment_count, last_updated")
        .eq("user_id", user_id)
        .execute()
    )
    if not index_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index not found. Please sign in again.",
        )
    idx = index_result.data[0]

    conversation_result = (
        db.table("conversations").select("id", count="exact").eq("user_id", user_id).execute()
    )
    commitment_result = (
        db.table("commitments").select("id", count="exact").eq("user_id", user_id).execute()
    )
    entity_result = (
        db.table("entities").select("id", count="exact").eq("user_id", user_id).execute()
    )
    topic_rows = (
        db.table("topics")
        .select("id, label, summary, status, key_quotes, conversation_id, created_at")
        .eq("user_id", user_id)
        .execute()
    ).data or []
    topic_count = len(cluster_topic_rows(topic_rows))

    entity_count = entity_result.count or 0

    return IndexStats(
        conversation_count=conversation_result.count or 0,
        topic_count=topic_count,
        commitment_count=commitment_result.count or 0,
        entity_count=entity_count,
        last_updated_at=idx.get("last_updated"),
    )
