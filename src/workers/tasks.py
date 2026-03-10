"""
Celery application and task definitions for Farz workers.

All tasks include user_id in their payload to enforce per-user isolation.
Transcript content is never logged — only IDs are written to the log.
"""
import logging

from celery import Celery

from src import celeryconfig

logger = logging.getLogger(__name__)

celery_app = Celery("farz")
celery_app.config_from_object(celeryconfig)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_transcript(
    self,
    transcript_id: str,
    user_id: str,
    raw_text: str,
) -> dict:
    """Enqueue a transcript for processing.

    Args:
        transcript_id: Unique identifier for the transcript record.
        user_id: Owner of the transcript — enforces per-user isolation.
        raw_text: Raw transcript text. Never logged.

    Returns:
        A dict containing transcript_id, user_id, and status.

    Raises:
        ValueError: If transcript_id or user_id are empty.
    """
    if not transcript_id:
        raise ValueError("transcript_id is required and must be non-empty")
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")

    logger.info("Processing transcript %s for user %s", transcript_id, user_id)

    # Actual extraction logic is implemented in Phase 1.
    return {
        "transcript_id": transcript_id,
        "user_id": user_id,
        "status": "queued",
    }


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def generate_brief(
    self,
    conversation_id: str,
    user_id: str,
) -> dict:
    """Enqueue a brief generation job for a conversation.

    Args:
        conversation_id: Unique identifier for the conversation record.
        user_id: Owner of the conversation — enforces per-user isolation.

    Returns:
        A dict containing conversation_id, user_id, and status.

    Raises:
        ValueError: If conversation_id or user_id are empty.
    """
    if not conversation_id:
        raise ValueError("conversation_id is required and must be non-empty")
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")

    logger.info(
        "Generating brief for conversation %s, user %s", conversation_id, user_id
    )

    # Actual brief generation logic is implemented in Phase 1.
    return {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "status": "queued",
    }
