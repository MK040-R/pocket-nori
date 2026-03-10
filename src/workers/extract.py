"""
Extraction worker — AI pipeline from transcript segments to structured knowledge.

Pipeline per conversation:
  1. Load all TranscriptSegments for the conversation from DB
  2. Concatenate segment texts → single transcript string
  3. Call llm_client to extract Topics, Commitments, Entities in parallel
  4. Insert Topics, Commitments, Entities with source segment_ids (junction tables)
  5. Update conversations.status → 'indexed'
  6. Update user_index topic_count and commitment_count

Rules:
- Transcript content is NEVER logged — only IDs and counts.
- user_jwt is used for all DB operations (RLS enforced, never service_role).
- Celery task validates ownership before any read/write.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src import llm_client
from src.celery_app import celery_app
from src.database import get_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=420,
)
def extract_from_conversation(
    self: Any,
    conversation_id: str,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Extract topics, commitments, and entities from a stored conversation.

    Reads TranscriptSegments from DB, runs AI extraction via llm_client,
    and persists Topics, Commitments, and Entities back to DB.

    Args:
        conversation_id: UUID of the conversation to process.
        user_id: Supabase user UUID (for per-user isolation validation).
        user_jwt: Supabase JWT — used for all DB operations (RLS enforced).

    Returns:
        dict with conversation_id, topic_count, commitment_count, entity_count.

    Raises:
        ValueError: If any required argument is empty.
        RuntimeError: If the conversation doesn't belong to the user.
    """
    if not all([conversation_id, user_id, user_jwt]):
        raise ValueError("conversation_id, user_id, and user_jwt are all required")

    logger.info("Extraction started — conversation=%s user=%s", conversation_id, user_id)
    db = get_client(user_jwt)

    # --- Validate ownership ---
    conv_result = (
        db.table("conversations")
        .select("id, user_id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conv_result.data:
        raise RuntimeError(f"Conversation {conversation_id} not found for user {user_id}")

    # --- Load transcript segments ---
    self.update_state(state="PROGRESS", meta={"status": "loading_segments"})
    segments_result = (
        db.table("transcript_segments")
        .select("id, speaker_id, start_ms, text")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("start_ms")
        .execute()
    )
    segments: list[dict[str, Any]] = segments_result.data or []

    if not segments:
        logger.warning(
            "No transcript segments found for conversation=%s — marking indexed anyway",
            conversation_id,
        )
        db.table("conversations").update({"status": "indexed"}).eq("id", conversation_id).execute()
        return {
            "conversation_id": conversation_id,
            "topic_count": 0,
            "commitment_count": 0,
            "entity_count": 0,
        }

    # Concatenate segments into a single transcript (never log this text)
    transcript = "\n".join(f"[{seg['speaker_id']}] {seg['text']}" for seg in segments)
    segment_ids = [seg["id"] for seg in segments]

    # --- AI extraction (3 independent calls) ---
    self.update_state(state="PROGRESS", meta={"status": "extracting"})

    topic_list = llm_client.extract_topics(transcript)
    commitment_list = llm_client.extract_commitments(transcript)
    entity_list = llm_client.extract_entities(transcript)

    logger.info(
        "Extraction complete — conversation=%s topics=%d commitments=%d entities=%d",
        conversation_id,
        len(topic_list.topics),
        len(commitment_list.commitments),
        len(entity_list.entities),
    )

    # --- Persist Topics ---
    self.update_state(state="PROGRESS", meta={"status": "saving_topics"})
    topic_ids: list[str] = []

    for topic in topic_list.topics:
        topic_id = str(uuid.uuid4())
        db.table("topics").insert(
            {
                "id": topic_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "label": topic.label,
                "summary": topic.summary,
                "status": topic.status,
                "key_quotes": topic.key_quotes,
            }
        ).execute()
        topic_ids.append(topic_id)

        # Link topic → all segments (simple: link to all, since topics span the conversation)
        if segment_ids:
            db.table("topic_segment_links").insert(
                [
                    {"user_id": user_id, "topic_id": topic_id, "segment_id": seg_id}
                    for seg_id in segment_ids
                ]
            ).execute()

    # --- Persist Commitments ---
    self.update_state(state="PROGRESS", meta={"status": "saving_commitments"})

    for commitment in commitment_list.commitments:
        commitment_id = str(uuid.uuid4())

        # Parse due_date if present
        due_date: str | None = None
        if commitment.due_date:
            try:
                due_date = datetime.fromisoformat(commitment.due_date).isoformat()
            except ValueError:
                due_date = None

        db.table("commitments").insert(
            {
                "id": commitment_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "text": commitment.text,
                "owner": commitment.owner,
                "due_date": due_date,
                "status": commitment.status,
            }
        ).execute()

        # Link commitment → all segments
        if segment_ids:
            db.table("commitment_segment_links").insert(
                [
                    {"user_id": user_id, "commitment_id": commitment_id, "segment_id": seg_id}
                    for seg_id in segment_ids
                ]
            ).execute()

    # --- Persist Entities ---
    self.update_state(state="PROGRESS", meta={"status": "saving_entities"})

    for entity in entity_list.entities:
        entity_id = str(uuid.uuid4())
        db.table("entities").insert(
            {
                "id": entity_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "name": entity.name,
                "type": entity.type,
                "mentions": entity.mentions,
            }
        ).execute()

        # Link entity → all segments
        if segment_ids:
            db.table("entity_segment_links").insert(
                [
                    {"user_id": user_id, "entity_id": entity_id, "segment_id": seg_id}
                    for seg_id in segment_ids
                ]
            ).execute()

    # --- Mark conversation as indexed ---
    db.table("conversations").update({"status": "indexed"}).eq("id", conversation_id).execute()

    # --- Update user_index counts ---
    existing_index = (
        db.table("user_index")
        .select("topic_count, commitment_count")
        .eq("user_id", user_id)
        .execute()
    )
    if existing_index.data:
        current = existing_index.data[0]
        db.table("user_index").update(
            {
                "topic_count": current["topic_count"] + len(topic_list.topics),
                "commitment_count": current["commitment_count"] + len(commitment_list.commitments),
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()

    logger.info(
        "Extraction persisted — conversation=%s topics=%d commitments=%d entities=%d user=%s",
        conversation_id,
        len(topic_list.topics),
        len(commitment_list.commitments),
        len(entity_list.entities),
        user_id,
    )

    return {
        "conversation_id": conversation_id,
        "topic_count": len(topic_list.topics),
        "commitment_count": len(commitment_list.commitments),
        "entity_count": len(entity_list.entities),
    }
