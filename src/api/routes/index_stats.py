"""
Index stats route.

GET /index/stats — return counts and last-updated timestamp from the user's index
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.schema_guards import is_missing_schema_feature
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.entity_node_store import load_entity_nodes
from src.topic_node_store import load_topic_nodes

logger = logging.getLogger(__name__)

router = APIRouter()
_INDEX_STATS_CACHE_TTL_SECONDS = 60

# Backward-compatible alias during the topic-node bridge.
load_topic_clusters = load_topic_nodes


class IndexStats(BaseModel):
    conversation_count: int
    topic_count: int
    commitment_count: int
    entity_count: int
    last_updated_at: str | None


def _compute_fallback_stats(db: Any, user_id: str, index_row: dict[str, Any]) -> IndexStats:
    return IndexStats(
        conversation_count=int(index_row.get("conversation_count") or 0),
        topic_count=len(load_topic_clusters(db, user_id, min_conversations=1)),
        commitment_count=int(index_row.get("commitment_count") or 0),
        entity_count=len(load_entity_nodes(db, user_id, min_conversations=1)),
        last_updated_at=index_row.get("last_updated"),
    )


def load_index_stats_snapshot(db: Any, user_id: str) -> IndexStats:
    """Return cached index stats for dashboard reads."""
    cache_key = build_user_cache_key(user_id, "index_stats", {"path": "/index/stats"})
    cached = get_cached_json(cache_key)
    if cached is not None:
        return IndexStats.model_validate(cached)

    try:
        index_result = (
            db.table("user_index")
            .select("conversation_count, topic_count, commitment_count, entity_count, last_updated")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        if not is_missing_schema_feature(exc, "user_index", "entity_count"):
            raise
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
            ) from exc
        payload = _compute_fallback_stats(db, user_id, index_result.data[0])
        set_cached_json(cache_key, payload.model_dump(mode="json"), _INDEX_STATS_CACHE_TTL_SECONDS)
        return payload

    if not index_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index not found. Please sign in again.",
        )
    idx = index_result.data[0]
    entity_count = idx.get("entity_count")
    if entity_count is None:
        payload = _compute_fallback_stats(db, user_id, idx)
        set_cached_json(cache_key, payload.model_dump(mode="json"), _INDEX_STATS_CACHE_TTL_SECONDS)
        return payload

    payload = IndexStats(
        conversation_count=int(idx.get("conversation_count") or 0),
        topic_count=int(idx.get("topic_count") or 0),
        commitment_count=int(idx.get("commitment_count") or 0),
        entity_count=int(entity_count or 0),
        last_updated_at=idx.get("last_updated"),
    )
    set_cached_json(cache_key, payload.model_dump(mode="json"), _INDEX_STATS_CACHE_TTL_SECONDS)
    return payload


@router.get(
    "/stats",
    response_model=IndexStats,
    summary="Return counts and last-updated time from the user's index",
)
def get_index_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> IndexStats:
    """Return aggregate counts for the current user's intelligence index."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    return load_index_stats_snapshot(db, user_id)
