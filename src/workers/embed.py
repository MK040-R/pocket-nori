"""
Embedding worker — generates pgvector embeddings for transcript segments.

Pipeline per conversation:
  1. Load all TranscriptSegments for the conversation from DB
  2. Batch-embed segment texts via OpenAI text-embedding-3-small
  3. Update each transcript_segment.embedding column with the vector

Rules:
- Transcript content is NEVER logged — only IDs and counts.
- user_jwt is used for all DB operations (RLS enforced, never service_role).
- Embeddings are generated in batches to stay within API rate limits.
"""

import logging
from typing import Any

from supabase import Client

from src import llm_client
from src.celery_app import celery_app
from src.database import get_client
from src.entity_node_store import (
    ENTITY_NODE_FOREIGN_KEY_COLUMN,
    ENTITY_NODE_NAME_COLUMN,
    ENTITY_NODE_TABLE,
    ENTITY_NODE_TYPE_COLUMN,
)
from src.topic_node_store import (
    TOPIC_NODE_FOREIGN_KEY_COLUMN,
    TOPIC_NODE_LABEL_COLUMN,
    TOPIC_NODE_SUMMARY_COLUMN,
    TOPIC_NODE_TABLE,
)

logger = logging.getLogger(__name__)

# OpenAI rate limit: 2048 inputs per batch for text-embedding-3-small
_EMBED_BATCH_SIZE = 100


def refresh_entity_node_embeddings(
    db: Client,
    user_id: str,
    entity_node_ids: list[str] | set[str],
    *,
    only_missing: bool = False,
) -> int:
    """Refresh embeddings for the provided canonical entity nodes."""
    node_ids = sorted({node_id for node_id in entity_node_ids if node_id})
    if not node_ids:
        return 0

    query = (
        db.table(ENTITY_NODE_TABLE)
        .select(f"id, {ENTITY_NODE_NAME_COLUMN}, {ENTITY_NODE_TYPE_COLUMN}")
        .in_("id", node_ids)
        .eq("user_id", user_id)
    )
    if only_missing:
        query = query.is_("embedding", "null")

    entity_nodes = query.execute().data or []
    if not entity_nodes:
        return 0

    total_embedded = 0
    for batch_start in range(0, len(entity_nodes), _EMBED_BATCH_SIZE):
        batch = entity_nodes[batch_start : batch_start + _EMBED_BATCH_SIZE]
        texts = [
            f"{node[ENTITY_NODE_NAME_COLUMN]} ({node[ENTITY_NODE_TYPE_COLUMN]})".strip()
            for node in batch
        ]
        vectors = llm_client.embed_texts(texts)

        for entity_node, vector in zip(batch, vectors, strict=True):
            (
                db.table(ENTITY_NODE_TABLE)
                .update({"embedding": vector})
                .eq("id", entity_node["id"])
                .eq("user_id", user_id)
                .execute()
            )
        total_embedded += len(batch)

    return total_embedded


def refresh_topic_node_embeddings(
    db: Client,
    user_id: str,
    topic_node_ids: list[str] | set[str],
    *,
    only_missing: bool = False,
) -> int:
    """Refresh embeddings for the provided canonical topic nodes.

    When ``only_missing`` is true, only rows with ``embedding IS NULL`` are
    embedded. Otherwise all provided nodes are re-embedded from current label
    and summary metadata.
    """
    node_ids = sorted({node_id for node_id in topic_node_ids if node_id})
    if not node_ids:
        return 0

    query = (
        db.table(TOPIC_NODE_TABLE)
        .select(f"id, {TOPIC_NODE_LABEL_COLUMN}, {TOPIC_NODE_SUMMARY_COLUMN}")
        .in_("id", node_ids)
        .eq("user_id", user_id)
    )
    if only_missing:
        query = query.is_("embedding", "null")

    topic_nodes = query.execute().data or []
    if not topic_nodes:
        return 0

    total_embedded = 0
    for batch_start in range(0, len(topic_nodes), _EMBED_BATCH_SIZE):
        batch = topic_nodes[batch_start : batch_start + _EMBED_BATCH_SIZE]
        texts = [
            (
                f"{node[TOPIC_NODE_LABEL_COLUMN]}. "
                f"{node.get(TOPIC_NODE_SUMMARY_COLUMN, '')}"
            ).strip()
            for node in batch
        ]
        vectors = llm_client.embed_texts(texts)

        for topic_node, vector in zip(batch, vectors, strict=True):
            db.table(TOPIC_NODE_TABLE).update({"embedding": vector}).eq("id", topic_node["id"]).eq(
                "user_id", user_id
            ).execute()
        total_embedded += len(batch)

    return total_embedded


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=420,
)
def embed_conversation(
    self: Any,
    conversation_id: str,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Generate and store embeddings for all segments in a conversation.

    Args:
        conversation_id: UUID of the conversation to embed.
        user_id: Supabase user UUID (for per-user isolation validation).
        user_jwt: Supabase JWT — used for all DB operations (RLS enforced).

    Returns:
        dict with conversation_id and segment_count (number of segments embedded).

    Raises:
        ValueError: If any required argument is empty.
        RuntimeError: If the conversation doesn't belong to the user.
    """
    if not all([conversation_id, user_id, user_jwt]):
        raise ValueError("conversation_id, user_id, and user_jwt are all required")

    logger.info("Embedding started — conversation=%s user=%s", conversation_id, user_id)
    db = get_client(user_jwt)

    # --- Validate ownership ---
    conv_result = (
        db.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conv_result.data:
        raise RuntimeError(f"Conversation {conversation_id} not found for user {user_id}")

    # --- Load segments that need embeddings ---
    self.update_state(state="PROGRESS", meta={"status": "loading_segments"})
    segments_result = (
        db.table("transcript_segments")
        .select("id, text")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .is_("embedding", "null")
        .order("start_ms")
        .execute()
    )
    segments: list[dict[str, Any]] = segments_result.data or []

    if not segments:
        logger.info("No unembedded segments for conversation=%s — nothing to do", conversation_id)
        return {"conversation_id": conversation_id, "segment_count": 0}

    # --- Batch embed ---
    self.update_state(state="PROGRESS", meta={"status": "embedding"})

    total_embedded = 0
    for batch_start in range(0, len(segments), _EMBED_BATCH_SIZE):
        batch = segments[batch_start : batch_start + _EMBED_BATCH_SIZE]
        texts = [seg["text"] for seg in batch]

        # Never log transcript text — only counts
        vectors = llm_client.embed_texts(texts)

        # Update each segment with its embedding vector
        for seg, vector in zip(batch, vectors, strict=True):
            db.table("transcript_segments").update({"embedding": vector}).eq(
                "id", seg["id"]
            ).execute()

        total_embedded += len(batch)
        logger.info(
            "Embedded batch — conversation=%s progress=%d/%d",
            conversation_id,
            total_embedded,
            len(segments),
        )

    logger.info(
        "Embedding complete — conversation=%s segments=%d user=%s",
        conversation_id,
        total_embedded,
        user_id,
    )

    # --- Embed canonical topic nodes linked to this conversation ---
    self.update_state(state="PROGRESS", meta={"status": "embedding_topics"})
    _embed_topic_nodes(db, conversation_id, user_id)

    # --- Embed entities for this conversation ---
    self.update_state(state="PROGRESS", meta={"status": "embedding_entities"})
    _embed_entities(db, conversation_id, user_id)

    # --- Embed canonical entity nodes linked to this conversation ---
    self.update_state(state="PROGRESS", meta={"status": "embedding_entity_nodes"})
    _embed_entity_nodes(db, conversation_id, user_id)

    # --- Embed conversation digest ---
    self.update_state(state="PROGRESS", meta={"status": "embedding_digest"})
    _embed_conversation_digest(db, conversation_id, user_id)

    return {"conversation_id": conversation_id, "segment_count": total_embedded}


def _embed_topic_nodes(db: Client, conversation_id: str, user_id: str) -> None:
    """Embed topic nodes linked to this conversation that have no embedding yet.

    Only embeds rows with embedding IS NULL to avoid re-embedding topic nodes
    already processed by a prior conversation in the same batch.
    """
    topics_result = (
        db.table("topics")
        .select(TOPIC_NODE_FOREIGN_KEY_COLUMN)
        .eq("conversation_id", conversation_id)
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
    if not topic_node_ids:
        return

    embedded_count = refresh_topic_node_embeddings(
        db,
        user_id,
        topic_node_ids,
        only_missing=True,
    )
    if not embedded_count:
        return

    logger.info(
        "Topic node embeddings stored — conversation=%s topic_nodes=%d",
        conversation_id,
        embedded_count,
    )


def _embed_entities(db: Client, conversation_id: str, user_id: str) -> None:
    """Embed entities for this conversation (all — entities are per-conversation rows)."""
    entities_result = (
        db.table("entities")
        .select("id, name, type")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .is_("embedding", "null")
        .execute()
    )
    entities = entities_result.data or []
    if not entities:
        return

    texts = [f"{e['name']} ({e['type']})" for e in entities]
    vectors = llm_client.embed_texts(texts)

    for entity, vector in zip(entities, vectors, strict=True):
        db.table("entities").update({"embedding": vector}).eq("id", entity["id"]).eq(
            "user_id", user_id
        ).execute()

    logger.info(
        "Entity embeddings stored — conversation=%s entities=%d",
        conversation_id,
        len(entities),
    )


def _embed_entity_nodes(db: Client, conversation_id: str, user_id: str) -> None:
    """Embed canonical entity nodes linked to this conversation that have no embedding yet."""
    entities_result = (
        db.table("entities")
        .select(ENTITY_NODE_FOREIGN_KEY_COLUMN)
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    entity_node_ids = list(
        {
            row[ENTITY_NODE_FOREIGN_KEY_COLUMN]
            for row in (entities_result.data or [])
            if row.get(ENTITY_NODE_FOREIGN_KEY_COLUMN)
        }
    )
    if not entity_node_ids:
        return

    embedded_count = refresh_entity_node_embeddings(
        db,
        user_id,
        entity_node_ids,
        only_missing=True,
    )
    if not embedded_count:
        return

    logger.info(
        "Entity node embeddings stored — conversation=%s entity_nodes=%d",
        conversation_id,
        embedded_count,
    )


def _embed_conversation_digest(db: Client, conversation_id: str, user_id: str) -> None:
    """Embed the conversation digest if present and not yet embedded."""
    conv_result = (
        db.table("conversations")
        .select("id, digest, digest_embedding")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    conv = (conv_result.data or [None])[0]
    if not conv or not conv.get("digest") or conv.get("digest_embedding"):
        return

    vectors = llm_client.embed_texts([conv["digest"]])
    db.table("conversations").update({"digest_embedding": vectors[0]}).eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()

    logger.info("Digest embedding stored — conversation=%s", conversation_id)
