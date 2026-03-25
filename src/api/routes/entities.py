"""Entities route — canonical entity node directory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.entity_node_store import load_entity_nodes

router = APIRouter()
_ENTITIES_CACHE_TTL_SECONDS = 120


class EntitySummary(BaseModel):
    name: str
    type: str
    mentions: int
    conversation_count: int


@router.get("", response_model=list[EntitySummary], summary="List canonical entity nodes")
def list_entities(
    limit: int = 100,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[EntitySummary]:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    cache_key = build_user_cache_key(
        user_id,
        "entities",
        {"limit": limit, "offset": offset},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return [EntitySummary.model_validate(row) for row in cached]

    summaries = [
        EntitySummary(
            name=node.name,
            type=node.entity_type,
            mentions=node.mention_count,
            conversation_count=len(node.conversation_ids),
        )
        for node in load_entity_nodes(
            db,
            user_id,
            min_conversations=1,
            limit=limit,
            offset=offset,
        )
    ]
    set_cached_json(
        cache_key,
        [summary.model_dump(mode="json") for summary in summaries],
        _ENTITIES_CACHE_TTL_SECONDS,
    )
    return summaries
