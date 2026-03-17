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
from src.cache_utils import bump_user_cache_version
from src.celery_app import celery_app
from src.commitment_utils import sanitize_commitment_rows
from src.database import get_client
from src.topic_cluster_store import (
    assign_cluster_for_topic,
    assign_clusters_to_existing_topics,
    clear_user_topic_clusters,
    load_cluster_registry,
    load_recluster_source_rows,
    load_topic_clusters,
    merge_recent_topic_rows_semantically,
    purge_placeholder_topics,
    refresh_clusters_metadata,
    stabilize_reclustered_cluster_ids,
    upsert_topic_arcs_for_clusters,
)
from src.topic_utils import sanitize_topic_rows

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
        .select("id, user_id, meeting_date")
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
        bump_user_cache_version(user_id)
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

    meeting_date = str(conv_result.data[0].get("meeting_date") or "")
    sanitized_topic_rows = sanitize_topic_rows(
        [
            {
                "label": topic.label,
                "summary": topic.summary,
                "status": topic.status,
                "key_quotes": topic.key_quotes,
                "conversation_id": conversation_id,
                "meeting_date": meeting_date,
            }
            for topic in topic_list.topics
            if not topic.is_background
        ]
    )
    sanitized_commitment_rows = sanitize_commitment_rows(
        [
            {
                "text": commitment.text,
                "owner": commitment.owner,
                "due_date": commitment.due_date,
                "status": commitment.status,
            }
            for commitment in commitment_list.commitments
        ]
    )

    logger.info(
        "Extraction complete — conversation=%s topics=%d commitments=%d entities=%d",
        conversation_id,
        len(sanitized_topic_rows),
        len(sanitized_commitment_rows),
        len(entity_list.entities),
    )

    # --- Persist Topics ---
    self.update_state(state="PROGRESS", meta={"status": "saving_topics"})
    topic_ids: list[str] = []
    cluster_registry = load_cluster_registry(db, user_id)
    affected_cluster_ids: set[str] = set()

    for topic_row in sanitized_topic_rows:
        cluster_id = assign_cluster_for_topic(
            db,
            user_id,
            topic_row=topic_row,
            clusters=cluster_registry,
        )
        topic_id = str(uuid.uuid4())
        db.table("topics").insert(
            {
                "id": topic_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "cluster_id": cluster_id,
                "label": topic_row["label"],
                "summary": topic_row.get("summary", ""),
                "status": topic_row.get("status", "open"),
                "key_quotes": topic_row.get("key_quotes") or [],
            }
        ).execute()
        topic_ids.append(topic_id)
        affected_cluster_ids.add(cluster_id)

        # Link topic → all segments (simple: link to all, since topics span the conversation)
        if segment_ids:
            db.table("topic_segment_links").insert(
                [
                    {"user_id": user_id, "topic_id": topic_id, "segment_id": seg_id}
                    for seg_id in segment_ids
                ]
            ).execute()

    if affected_cluster_ids:
        refresh_clusters_metadata(db, user_id, affected_cluster_ids)
        upsert_topic_arcs_for_clusters(db, user_id, affected_cluster_ids)

    # --- Persist Commitments ---
    self.update_state(state="PROGRESS", meta={"status": "saving_commitments"})

    for commitment in sanitized_commitment_rows:
        commitment_id = str(uuid.uuid4())

        # Parse due_date if present
        due_date: str | None = None
        if commitment.get("due_date"):
            try:
                due_date = datetime.fromisoformat(str(commitment["due_date"])).isoformat()
            except ValueError:
                due_date = None

        db.table("commitments").insert(
            {
                "id": commitment_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "text": commitment["text"],
                "owner": commitment["owner"],
                "due_date": due_date,
                "status": commitment.get("status", "open"),
                "action_type": commitment.get("action_type", "commitment"),
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

    # --- Generate meeting digest (one LLM call, stored for semantic search) ---
    self.update_state(state="PROGRESS", meta={"status": "generating_digest"})
    try:
        digest = llm_client.generate_meeting_digest(
            topics=[
                {"label": row["label"], "summary": row.get("summary", "")}
                for row in sanitized_topic_rows
            ],
            commitments=[
                {
                    "text": c["text"],
                    "owner": c["owner"],
                    "due_date": c.get("due_date"),
                }
                for c in sanitized_commitment_rows
            ],
            entities=[{"name": e.name, "type": e.type} for e in entity_list.entities],
        )
        if digest:
            db.table("conversations").update({"digest": digest}).eq("id", conversation_id).eq(
                "user_id", user_id
            ).execute()
            logger.info("Digest stored — conversation=%s", conversation_id)
    except Exception as exc:
        # Digest failure is non-fatal — search degrades gracefully without it
        logger.warning(
            "Digest generation failed — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

    # --- Auto-classify meeting category ---
    self.update_state(state="PROGRESS", meta={"status": "classifying_category"})
    try:
        conv_title = str(conv_result.data[0].get("title", "") if conv_result.data else "")
        topic_labels = [row["label"] for row in sanitized_topic_rows[:5]]
        entity_names = [e.name for e in entity_list.entities[:5]]
        category = llm_client.classify_meeting_category(conv_title, topic_labels, entity_names)
        if category:
            db.table("conversations").update({"category": category}).eq("id", conversation_id).eq(
                "user_id", user_id
            ).execute()
            logger.info(
                "Category classified — conversation=%s category=%s", conversation_id, category
            )
    except Exception as exc:
        # Category classification is non-fatal
        logger.warning(
            "Category classification failed — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

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
                "topic_count": current["topic_count"] + len(sanitized_topic_rows),
                "commitment_count": current["commitment_count"] + len(sanitized_commitment_rows),
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()

    logger.info(
        "Extraction persisted — conversation=%s topics=%d commitments=%d entities=%d user=%s",
        conversation_id,
        len(sanitized_topic_rows),
        len(sanitized_commitment_rows),
        len(entity_list.entities),
        user_id,
    )
    bump_user_cache_version(user_id)

    return {
        "conversation_id": conversation_id,
        "topic_count": len(sanitized_topic_rows),
        "commitment_count": len(sanitized_commitment_rows),
        "entity_count": len(entity_list.entities),
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=900,
    time_limit=1200,
)
def recluster_topics_for_user(
    self: Any,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Rebuild durable topic clusters and arcs for a user."""
    if not all([user_id, user_jwt]):
        raise ValueError("user_id and user_jwt are both required")

    logger.info("Topic recluster started — user=%s", user_id)
    db = get_client(user_jwt)

    previous_clusters = load_topic_clusters(db, user_id, min_conversations=1)

    self.update_state(state="PROGRESS", meta={"status": "purging_placeholders"})
    purged_count = purge_placeholder_topics(db, user_id)

    self.update_state(state="PROGRESS", meta={"status": "loading_topics"})
    topic_rows = load_recluster_source_rows(db, user_id)

    self.update_state(state="PROGRESS", meta={"status": "rebuilding_clusters_lexical"})
    clear_user_topic_clusters(db, user_id)
    affected_cluster_ids = assign_clusters_to_existing_topics(
        db,
        user_id,
        topic_rows,
        enable_semantic=False,
    )
    refreshed_clusters = refresh_clusters_metadata(db, user_id, affected_cluster_ids)
    final_cluster_ids = {cluster.id for cluster in refreshed_clusters}

    self.update_state(state="PROGRESS", meta={"status": "rebuilding_clusters_semantic_recent"})
    recent_semantic_cluster_ids, semantic_check_count = merge_recent_topic_rows_semantically(
        db,
        user_id,
        topic_rows,
    )
    if recent_semantic_cluster_ids:
        affected_cluster_ids.update(recent_semantic_cluster_ids)
        refresh_clusters_metadata(db, user_id, affected_cluster_ids)

    final_cluster_ids = stabilize_reclustered_cluster_ids(db, user_id, previous_clusters)
    refreshed_clusters = refresh_clusters_metadata(db, user_id, final_cluster_ids)
    final_cluster_ids = {cluster.id for cluster in refreshed_clusters}

    self.update_state(state="PROGRESS", meta={"status": "rebuilding_arcs"})
    upsert_topic_arcs_for_clusters(
        db,
        user_id,
        final_cluster_ids,
    )

    bump_user_cache_version(user_id)
    logger.info(
        "Topic recluster complete — user=%s clusters=%d topics=%d purged=%d semantic_checks=%d",
        user_id,
        len(final_cluster_ids),
        len(topic_rows),
        purged_count,
        semantic_check_count,
    )
    return {
        "user_id": user_id,
        "cluster_count": len(final_cluster_ids),
        "topic_count": len(topic_rows),
        "purged_topic_count": purged_count,
        "semantic_check_count": semantic_check_count,
    }
