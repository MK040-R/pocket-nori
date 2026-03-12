"""Entities route — minimal MVP directory for named entities mentioned across meetings."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client

router = APIRouter()


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

    rows = (
        db.table("entities")
        .select("name, type, mentions, conversation_id")
        .eq("user_id", user_id)
        .order("mentions", desc=True)
        .execute()
    ).data or []

    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"mentions": 0, "conversation_ids": set()}
    )
    canonical_names: dict[tuple[str, str], str] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        entity_type = str(row.get("type") or "").strip()
        conversation_id = str(row.get("conversation_id") or "").strip()
        if not name or not entity_type:
            continue
        key = (name.lower(), entity_type)
        canonical_names.setdefault(key, name)
        grouped[key]["mentions"] += int(row.get("mentions") or 0)
        if conversation_id:
            grouped[key]["conversation_ids"].add(conversation_id)

    summaries = [
        EntitySummary(
            name=canonical_names[key],
            type=key[1],
            mentions=value["mentions"],
            conversation_count=len(value["conversation_ids"]),
        )
        for key, value in grouped.items()
    ]
    summaries.sort(key=lambda item: (-item.mentions, -item.conversation_count, item.name.lower()))
    return summaries[offset : offset + limit]
