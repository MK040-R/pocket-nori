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

from celery import Celery

from src import celeryconfig, llm_client
from src.database import get_client

logger = logging.getLogger(__name__)

celery_app = Celery("farz")
celery_app.config_from_object(celeryconfig)

# OpenAI rate limit: 2048 inputs per batch for text-embedding-3-small
_EMBED_BATCH_SIZE = 100


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
        raise RuntimeError(
            f"Conversation {conversation_id} not found for user {user_id}"
        )

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
        logger.info(
            "No unembedded segments for conversation=%s — nothing to do", conversation_id
        )
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
            db.table("transcript_segments").update(
                {"embedding": vector}
            ).eq("id", seg["id"]).execute()

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

    return {"conversation_id": conversation_id, "segment_count": total_embedded}
