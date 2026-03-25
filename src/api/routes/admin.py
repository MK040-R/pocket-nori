"""
Admin routes — one-time maintenance operations for the authenticated user's index.

POST /admin/backfill-embeddings
    Generates meeting digests and rich embeddings for all existing conversations
    that were imported before migration 009.

    Run once after deploying migration 009. Idempotent — skips conversations that
    already have a digest or embeddings.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import llm_client
from src.api.deps import get_current_user
from src.celery_app import celery_app
from src.database import get_client
from src.entity_node_store import ENTITY_NODE_FOREIGN_KEY_COLUMN
from src.topic_node_store import TOPIC_NODE_FOREIGN_KEY_COLUMN
from src.workers.embed import refresh_entity_node_embeddings, refresh_topic_node_embeddings
from src.workers.extract import (
    backfill_knowledge_graph_for_user,
    backfill_segment_links_for_user,
    rebuild_entity_nodes_for_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class BackfillResult(BaseModel):
    digests_generated: int
    topic_nodes_embedded: int
    entity_nodes_embedded: int
    entities_embedded: int
    digest_embeddings_stored: int
    conversations_processed: int
    conversations_skipped: int


class MaintenanceJobAccepted(BaseModel):
    job_id: str
    status: str


class MaintenanceJobStatus(BaseModel):
    job_id: str
    status: str
    detail: str | None = None
    result: dict[str, Any] | None = None


def _serialize_maintenance_job_status(job_id: str, user_id: str) -> MaintenanceJobStatus:
    """Return a normalized status payload for a maintenance Celery task."""
    result = AsyncResult(job_id, app=celery_app)
    state = result.state.lower()

    if state == "pending":
        return MaintenanceJobStatus(job_id=job_id, status="pending")

    if state == "progress":
        meta = result.info if isinstance(result.info, dict) else {}
        meta_user_id = str(meta.get("user_id") or "")
        if meta_user_id and meta_user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
        return MaintenanceJobStatus(
            job_id=job_id,
            status="progress",
            detail=str(meta.get("status") or "processing"),
        )

    if state == "success":
        task_result = result.result if isinstance(result.result, dict) else {}
        result_user_id = str(task_result.get("user_id") or "")
        if result_user_id and result_user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
        return MaintenanceJobStatus(
            job_id=job_id,
            status="success",
            result=task_result or None,
        )

    error_detail = str(result.result) if result.result else "Unknown error"
    return MaintenanceJobStatus(job_id=job_id, status="failure", detail=error_detail)


@router.post(
    "/backfill-embeddings",
    response_model=BackfillResult,
    summary="Generate missing digests and rich embeddings for all existing meetings",
)
def backfill_embeddings(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> BackfillResult:
    """Backfill digests and rich embeddings for meetings imported before migration 009.

    Idempotent — each step checks for IS NULL before generating or storing.
    Processes all conversations belonging to the authenticated user only.

    May take several minutes for large meeting libraries. Call once after deployment.
    """
    user_id: str = current_user["sub"]
    user_jwt: str = current_user["_raw_jwt"]
    db = get_client(user_jwt)

    digests_generated = 0
    topic_nodes_embedded = 0
    entity_nodes_embedded = 0
    entities_embedded = 0
    digest_embeddings_stored = 0
    conversations_processed = 0
    conversations_skipped = 0

    # --- Load all indexed conversations ---
    conv_result = (
        db.table("conversations")
        .select("id, digest, digest_embedding")
        .eq("user_id", user_id)
        .eq("status", "indexed")
        .execute()
    )
    conversations = conv_result.data or []
    logger.info("Backfill started — user=%s conversations=%d", user_id, len(conversations))

    for conv in conversations:
        conv_id: str = conv["id"]

        # --- Step 1: Generate digest if missing ---
        if not conv.get("digest"):
            topics_result = (
                db.table("topics")
                .select("label, summary")
                .eq("conversation_id", conv_id)
                .eq("user_id", user_id)
                .execute()
            )
            commitments_result = (
                db.table("commitments")
                .select("text, owner, due_date")
                .eq("conversation_id", conv_id)
                .eq("user_id", user_id)
                .execute()
            )
            entities_result = (
                db.table("entities")
                .select("name, type")
                .eq("conversation_id", conv_id)
                .eq("user_id", user_id)
                .execute()
            )

            topics = topics_result.data or []
            commitments = commitments_result.data or []
            entities = entities_result.data or []

            if not topics and not entities:
                conversations_skipped += 1
                continue

            try:
                digest = llm_client.generate_meeting_digest(
                    topics=[{"label": t["label"], "summary": t.get("summary", "")} for t in topics],
                    commitments=[
                        {"text": c["text"], "owner": c["owner"], "due_date": c.get("due_date")}
                        for c in commitments
                    ],
                    entities=[{"name": e["name"], "type": e["type"]} for e in entities],
                )
                if digest:
                    db.table("conversations").update({"digest": digest}).eq("id", conv_id).eq(
                        "user_id", user_id
                    ).execute()
                    conv["digest"] = digest
                    digests_generated += 1
            except Exception as exc:
                logger.warning(
                    "Backfill digest failed — conversation=%s error=%s",
                    conv_id,
                    type(exc).__name__,
                )

        # --- Step 2: Embed canonical topic nodes (skip already-embedded rows) ---
        topics_result = (
            db.table("topics")
            .select(TOPIC_NODE_FOREIGN_KEY_COLUMN)
            .eq("conversation_id", conv_id)
            .eq("user_id", user_id)
            .execute()
        )
        topic_node_ids = list(
            {
                row[TOPIC_NODE_FOREIGN_KEY_COLUMN]
                for row in (topics_result.data or [])
                if row.get(TOPIC_NODE_FOREIGN_KEY_COLUMN)
            }
        )
        if topic_node_ids:
            try:
                topic_nodes_embedded += refresh_topic_node_embeddings(
                    db,
                    user_id,
                    topic_node_ids,
                    only_missing=True,
                )
            except Exception as exc:
                logger.warning(
                    "Backfill topic node embed failed — conversation=%s error=%s",
                    conv_id,
                    type(exc).__name__,
                )

        # --- Step 3: Embed canonical entity nodes (skip already-embedded rows) ---
        entity_node_ids = list(
            {
                row[ENTITY_NODE_FOREIGN_KEY_COLUMN]
                for row in (
                    db.table("entities")
                    .select(ENTITY_NODE_FOREIGN_KEY_COLUMN)
                    .eq("conversation_id", conv_id)
                    .eq("user_id", user_id)
                    .execute()
                ).data
                or []
                if row.get(ENTITY_NODE_FOREIGN_KEY_COLUMN)
            }
        )
        if entity_node_ids:
            try:
                entity_nodes_embedded += refresh_entity_node_embeddings(
                    db,
                    user_id,
                    entity_node_ids,
                    only_missing=True,
                )
            except Exception as exc:
                logger.warning(
                    "Backfill entity node embed failed — conversation=%s error=%s",
                    conv_id,
                    type(exc).__name__,
                )

        # --- Step 4: Embed entities for this conversation ---
        ents_result = (
            db.table("entities")
            .select("id, name, type")
            .eq("conversation_id", conv_id)
            .eq("user_id", user_id)
            .is_("embedding", "null")
            .execute()
        )
        ents = ents_result.data or []
        if ents:
            try:
                texts = [f"{e['name']} ({e['type']})" for e in ents]
                vectors = llm_client.embed_texts(texts)
                for entity, vector in zip(ents, vectors, strict=True):
                    db.table("entities").update({"embedding": vector}).eq("id", entity["id"]).eq(
                        "user_id", user_id
                    ).execute()
                entities_embedded += len(ents)
            except Exception as exc:
                logger.warning(
                    "Backfill entity embed failed — conversation=%s error=%s",
                    conv_id,
                    type(exc).__name__,
                )

        # --- Step 5: Embed digest if present and not yet embedded ---
        if conv.get("digest") and not conv.get("digest_embedding"):
            try:
                vectors = llm_client.embed_texts([conv["digest"]])
                db.table("conversations").update({"digest_embedding": vectors[0]}).eq(
                    "id", conv_id
                ).eq("user_id", user_id).execute()
                digest_embeddings_stored += 1
            except Exception as exc:
                logger.warning(
                    "Backfill digest embed failed — conversation=%s error=%s",
                    conv_id,
                    type(exc).__name__,
                )

        conversations_processed += 1

    logger.info(
        "Backfill complete — user=%s processed=%d skipped=%d "
        "digests=%d topic_nodes=%d entity_nodes=%d entities=%d digest_embeddings=%d",
        user_id,
        conversations_processed,
        conversations_skipped,
        digests_generated,
        topic_nodes_embedded,
        entity_nodes_embedded,
        entities_embedded,
        digest_embeddings_stored,
    )

    return BackfillResult(
        digests_generated=digests_generated,
        topic_nodes_embedded=topic_nodes_embedded,
        entity_nodes_embedded=entity_nodes_embedded,
        entities_embedded=entities_embedded,
        digest_embeddings_stored=digest_embeddings_stored,
        conversations_processed=conversations_processed,
        conversations_skipped=conversations_skipped,
    )


@router.post(
    "/backfill-segment-links",
    response_model=MaintenanceJobAccepted,
    summary="Queue a rebuild of scored segment links for existing indexed data",
)
def queue_segment_link_backfill(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> MaintenanceJobAccepted:
    """Queue a per-user repair of topic, commitment, and entity segment citations."""
    user_id: str = current_user["sub"]
    user_jwt: str = current_user["_raw_jwt"]
    task = backfill_segment_links_for_user.delay(user_id=user_id, user_jwt=user_jwt)
    logger.info("Queued segment link backfill — user=%s job=%s", user_id, task.id)
    return MaintenanceJobAccepted(job_id=task.id, status="queued")


@router.get(
    "/jobs/{job_id}",
    response_model=MaintenanceJobStatus,
    summary="Poll the status of a maintenance job",
)
def get_maintenance_job_status(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> MaintenanceJobStatus:
    """Return the state of a queued rebuild/backfill Celery task."""
    user_id: str = current_user["sub"]
    return _serialize_maintenance_job_status(job_id, user_id)


@router.post(
    "/rebuild-entity-nodes",
    response_model=MaintenanceJobAccepted,
    summary="Queue a rebuild of canonical entity nodes for the authenticated user",
)
def queue_entity_node_rebuild(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> MaintenanceJobAccepted:
    user_id: str = current_user["sub"]
    user_jwt: str = current_user["_raw_jwt"]
    task = rebuild_entity_nodes_for_user.delay(user_id=user_id, user_jwt=user_jwt)
    logger.info("Queued entity node rebuild — user=%s job=%s", user_id, task.id)
    return MaintenanceJobAccepted(job_id=task.id, status="queued")


@router.post(
    "/backfill-knowledge-graph",
    response_model=MaintenanceJobAccepted,
    summary="Queue graph edge and compatibility-connection materialization for the user",
)
def queue_knowledge_graph_backfill(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> MaintenanceJobAccepted:
    user_id: str = current_user["sub"]
    user_jwt: str = current_user["_raw_jwt"]
    task = backfill_knowledge_graph_for_user.delay(user_id=user_id, user_jwt=user_jwt)
    logger.info("Queued knowledge graph backfill — user=%s job=%s", user_id, task.id)
    return MaintenanceJobAccepted(job_id=task.id, status="queued")
