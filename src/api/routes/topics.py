"""
Topics routes.

GET  /topics             — list stored canonical topic nodes
GET  /topics/{id}        — single topic node with source conversations
GET  /topics/{id}/arc    — topic arc timeline with citation metadata
POST /topics/recluster   — enqueue a per-user topic-node rebuild
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.topic_node_store import (
    StoredTopicNode,
    load_topic_node,
    load_topic_nodes,
    resolve_topic_node_id,
    upsert_topic_arc_for_node,
)
from src.workers.extract import rebuild_topic_nodes_for_user

logger = logging.getLogger(__name__)

router = APIRouter()
_TOPICS_CACHE_TTL_SECONDS = 120
_TOPIC_DETAIL_CACHE_TTL_SECONDS = 120
_TOPIC_ARC_CACHE_TTL_SECONDS = 120

# Backward-compatible aliases for older tests/call sites during the bridge.
load_topic_cluster = load_topic_node
load_topic_clusters = load_topic_nodes
resolve_topic_cluster_id = resolve_topic_node_id
recluster_topics_for_user = rebuild_topic_nodes_for_user
upsert_topic_arc_for_cluster = upsert_topic_arc_for_node


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


class TopicReclusterAccepted(BaseModel):
    job_id: str
    status: str


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


def _load_topic_node_or_404(db: Any, user_id: str, topic_id: str) -> StoredTopicNode:
    topic_node = load_topic_cluster(db, user_id, topic_id)
    if topic_node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic_node


@router.get(
    "",
    response_model=list[TopicSummary],
    summary="List canonical topics across all conversations",
)
def list_topics(
    min_conversations: int = Query(default=2, ge=1),
    limit: int = 100,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[TopicSummary]:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    cache_key = build_user_cache_key(
        user_id,
        "topics_list",
        {
            "min_conversations": min_conversations,
            "limit": limit,
            "offset": offset,
        },
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return [TopicSummary.model_validate(item) for item in cached]

    topic_nodes = load_topic_clusters(
        db,
        user_id,
        min_conversations=min_conversations,
        limit=limit,
        offset=offset,
    )
    payload = [
        TopicSummary(
            id=topic_node.id,
            label=topic_node.label,
            conversation_count=len(topic_node.conversation_ids),
            latest_date=topic_node.last_mentioned_at,
        )
        for topic_node in topic_nodes
    ]
    set_cached_json(
        cache_key,
        [item.model_dump(mode="json") for item in payload],
        _TOPICS_CACHE_TTL_SECONDS,
    )
    return payload


@router.post(
    "/recluster",
    response_model=TopicReclusterAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a per-user topic node rebuild",
)
def recluster_topics(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TopicReclusterAccepted:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    task = recluster_topics_for_user.delay(user_id=user_id, user_jwt=raw_jwt)
    logger.info("Queued topic node rebuild — user=%s job=%s", user_id, task.id)
    return TopicReclusterAccepted(job_id=task.id, status="queued")


@router.get(
    "/{topic_id}",
    response_model=TopicDetail,
    summary="Get a single canonical topic node with its source conversations",
)
def get_topic(
    topic_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TopicDetail:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    resolved_topic_node_id = resolve_topic_cluster_id(db, user_id, topic_id) or topic_id
    cache_key = build_user_cache_key(
        user_id,
        "topic_detail",
        {"topic_id": resolved_topic_node_id},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return TopicDetail.model_validate(cached)

    topic_node = _load_topic_node_or_404(db, user_id, topic_id)
    conversations: list[TopicConversation] = []
    seen_conversations: set[str] = set()
    for row in sorted(
        topic_node.rows,
        key=lambda candidate: (
            _parse_iso_timestamp(str(candidate.get("meeting_date") or ""))
            or datetime.min.replace(tzinfo=UTC)
        ),
        reverse=True,
    ):
        conversation_id = str(row.get("conversation_id") or "")
        if not conversation_id or conversation_id in seen_conversations:
            continue
        seen_conversations.add(conversation_id)
        conversations.append(
            TopicConversation(
                id=conversation_id,
                title=str(row.get("conversation_title") or ""),
                meeting_date=str(row.get("meeting_date") or ""),
            )
        )

    payload = TopicDetail(
        id=topic_node.id,
        label=topic_node.label,
        summary=topic_node.summary,
        key_quotes=topic_node.key_quotes,
        conversations=conversations,
    )
    set_cached_json(cache_key, payload.model_dump(mode="json"), _TOPIC_DETAIL_CACHE_TTL_SECONDS)
    return payload


@router.get(
    "/{topic_id}/arc",
    response_model=TopicArcDetail,
    summary="Get topic arc timeline with citation metadata",
)
def get_topic_arc(
    topic_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TopicArcDetail:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    resolved_topic_node_id = resolve_topic_cluster_id(db, user_id, topic_id)
    if not resolved_topic_node_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    cache_key = build_user_cache_key(
        user_id,
        "topic_arc",
        {"topic_id": resolved_topic_node_id},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return TopicArcDetail.model_validate(cached)

    arc_payload = upsert_topic_arc_for_cluster(db, user_id, resolved_topic_node_id)
    logger.info(
        "Topic arc computed — topic_node_id=%s user=%s points=%d",
        resolved_topic_node_id,
        user_id,
        len(arc_payload["arc_points"]),
    )
    set_cached_json(cache_key, arc_payload, _TOPIC_ARC_CACHE_TTL_SECONDS)
    return TopicArcDetail.model_validate(arc_payload)
