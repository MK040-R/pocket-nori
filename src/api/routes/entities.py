"""Entities route — minimal MVP directory for named entities mentioned across meetings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.entity_utils import group_entity_rows

router = APIRouter()
_ENTITIES_CACHE_TTL_SECONDS = 120


class EntitySummary(BaseModel):
    name: str
    type: str
    mentions: int
    conversation_count: int


@router.get("", response_model=list[EntitySummary], summary="List grouped entities")
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

    rows = (
        db.table("entities")
        .select("name, type, mentions, conversation_id")
        .eq("user_id", user_id)
        .order("mentions", desc=True)
        .execute()
    ).data or []

    summaries = [
        EntitySummary(
            name=summary.name,
            type=summary.type,
            mentions=summary.mentions,
            conversation_count=summary.conversation_count,
        )
        for summary in group_entity_rows(rows)
    ]
    visible = summaries[offset : offset + limit]
    set_cached_json(
        cache_key,
        [summary.model_dump(mode="json") for summary in visible],
        _ENTITIES_CACHE_TTL_SECONDS,
    )
    return visible
