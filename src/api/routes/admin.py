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

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src import llm_client
from src.api.deps import get_current_user
from src.database import get_client

logger = logging.getLogger(__name__)

router = APIRouter()


class BackfillResult(BaseModel):
    digests_generated: int
    topic_clusters_embedded: int
    entities_embedded: int
    digest_embeddings_stored: int
    conversations_processed: int
    conversations_skipped: int


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
    topic_clusters_embedded = 0
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

        # --- Step 2: Embed topic clusters (skip already-embedded clusters) ---
        topics_result = (
            db.table("topics")
            .select("cluster_id")
            .eq("conversation_id", conv_id)
            .eq("user_id", user_id)
            .execute()
        )
        cluster_ids = list(
            {row["cluster_id"] for row in (topics_result.data or []) if row.get("cluster_id")}
        )
        if cluster_ids:
            clusters_result = (
                db.table("topic_clusters")
                .select("id, canonical_label, canonical_summary")
                .in_("id", cluster_ids)
                .eq("user_id", user_id)
                .is_("embedding", "null")
                .execute()
            )
            clusters = clusters_result.data or []
            if clusters:
                try:
                    texts = [
                        f"{c['canonical_label']}. {c.get('canonical_summary', '')}".strip()
                        for c in clusters
                    ]
                    vectors = llm_client.embed_texts(texts)
                    for cluster, vector in zip(clusters, vectors, strict=True):
                        db.table("topic_clusters").update({"embedding": vector}).eq(
                            "id", cluster["id"]
                        ).eq("user_id", user_id).execute()
                    topic_clusters_embedded += len(clusters)
                except Exception as exc:
                    logger.warning(
                        "Backfill topic cluster embed failed — conversation=%s error=%s",
                        conv_id,
                        type(exc).__name__,
                    )

        # --- Step 3: Embed entities for this conversation ---
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

        # --- Step 4: Embed digest if present and not yet embedded ---
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
        "digests=%d clusters=%d entities=%d digest_embeddings=%d",
        user_id,
        conversations_processed,
        conversations_skipped,
        digests_generated,
        topic_clusters_embedded,
        entities_embedded,
        digest_embeddings_stored,
    )

    return BackfillResult(
        digests_generated=digests_generated,
        topic_clusters_embedded=topic_clusters_embedded,
        entities_embedded=entities_embedded,
        digest_embeddings_stored=digest_embeddings_stored,
        conversations_processed=conversations_processed,
        conversations_skipped=conversations_skipped,
    )
