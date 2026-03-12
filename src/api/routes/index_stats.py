"""
Index stats route.

GET /index/stats — return counts and last-updated timestamp from the user's index
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.topic_cluster_store import load_topic_clusters

logger = logging.getLogger(__name__)

router = APIRouter()
_INDEX_STATS_CACHE_TTL_SECONDS = 60


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
    cache_key = build_user_cache_key(user_id, "index_stats", {"path": "/index/stats"})
    cached = get_cached_json(cache_key)
    if cached is not None:
        return IndexStats.model_validate(cached)

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
    topic_count = len(load_topic_clusters(db, user_id, min_conversations=1))

    entity_count = entity_result.count or 0

    payload = IndexStats(
        conversation_count=conversation_result.count or 0,
        topic_count=topic_count,
        commitment_count=commitment_result.count or 0,
        entity_count=entity_count,
        last_updated_at=idx.get("last_updated"),
    )
    set_cached_json(cache_key, payload.model_dump(mode="json"), _INDEX_STATS_CACHE_TTL_SECONDS)
    return payload
