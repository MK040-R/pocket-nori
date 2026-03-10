"""
Ingest worker — full pipeline from Google Drive recording to stored transcript.

Pipeline per recording:
  1. Refresh Google access token (refresh_token → fresh access_token)
  2. Download audio/video bytes from Drive to memory
  3. Transcribe via Deepgram Nova-3 with speaker diarisation
  4. Hard-delete audio bytes from memory immediately
  5. Persist Conversation + TranscriptSegments to Postgres (via RLS-scoped client)
  6. Update user_index.last_updated

Rules:
- Audio bytes are NEVER written to disk and NEVER stored anywhere.
- Transcript content is NEVER logged — only IDs and counts.
- user_jwt is used for all DB operations (RLS enforced, never service_role).
- drive_file_id uniqueness prevents double-import (handled by DB unique index).
"""

import gc
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import Celery
from deepgram import DeepgramClient, PrerecordedOptions

from src import celeryconfig
from src.config import settings
from src.database import get_client
from src.drive_client import download_recording_sync, refresh_access_token_sync

logger = logging.getLogger(__name__)

celery_app = Celery("farz")
celery_app.config_from_object(celeryconfig)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _transcribe_bytes(audio_bytes: bytes, mime_type: str = "video/mp4") -> list[dict[str, Any]]:
    """Send audio bytes to Deepgram and return a list of utterance dicts.

    Each dict has keys: speaker_id (str), start_ms (int), end_ms (int), text (str).

    IMPORTANT: audio_bytes is not stored or logged. Caller must del it after this call.
    """
    deepgram = DeepgramClient(settings.DEEPGRAM_API_KEY)
    options = PrerecordedOptions(
        model="nova-3",
        diarize=True,
        punctuate=True,
        utterances=True,
        language="en-US",
    )
    payload: dict[str, Any] = {"buffer": audio_bytes, "mimetype": mime_type}
    response = deepgram.listen.rest.v("1").transcribe_file(payload, options)

    utterances: list[dict[str, Any]] = []
    if response.results and response.results.utterances:
        for utt in response.results.utterances:
            utterances.append(
                {
                    "speaker_id": f"speaker_{utt.speaker}",
                    "start_ms": int(utt.start * 1000),
                    "end_ms": int(utt.end * 1000),
                    "text": utt.transcript,
                }
            )
    logger.info("Transcription complete — %d utterances returned", len(utterances))
    return utterances


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=900,
)
def ingest_recording(
    self: Any,
    drive_file_id: str,
    file_name: str,
    created_time_iso: str,
    mime_type: str,
    user_id: str,
    user_jwt: str,
    google_refresh_token: str,
) -> dict[str, Any]:
    """Download, transcribe, and persist a single Google Drive recording.

    Args:
        drive_file_id: Google Drive file ID.
        file_name: Human-readable name (used as conversation title).
        created_time_iso: ISO-8601 timestamp of the recording (from Drive metadata).
        mime_type: MIME type of the Drive file (e.g. "video/mp4").
        user_id: Supabase user UUID (for per-user isolation).
        user_jwt: Supabase JWT — used for all DB writes (RLS enforced).
        google_refresh_token: Used to obtain a fresh Google access token.

    Returns:
        dict with conversation_id, segment_count, and already_existed flag.

    Raises:
        ValueError: If any required argument is empty.
    """
    if not all([drive_file_id, file_name, created_time_iso, user_id, user_jwt, google_refresh_token]):
        raise ValueError("All arguments to ingest_recording are required")

    logger.info("Ingest started — file_id=%s user=%s", drive_file_id, user_id)
    db = get_client(user_jwt)

    # --- Idempotency check: skip if already imported ---
    existing = (
        db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("drive_file_id", drive_file_id)
        .execute()
    )
    if existing.data:
        conversation_id = existing.data[0]["id"]
        logger.info("Recording already imported — conversation=%s, skipping", conversation_id)
        return {
            "conversation_id": conversation_id,
            "segment_count": 0,
            "already_existed": True,
        }

    # --- Step 1: Refresh Google access token ---
    self.update_state(state="PROGRESS", meta={"status": "authenticating"})
    access_token = refresh_access_token_sync(google_refresh_token)

    # --- Step 2: Download audio to memory ---
    self.update_state(state="PROGRESS", meta={"status": "downloading"})
    audio_bytes = download_recording_sync(access_token, drive_file_id)

    # --- Step 3: Transcribe ---
    self.update_state(state="PROGRESS", meta={"status": "transcribing"})
    try:
        utterances = _transcribe_bytes(audio_bytes, mime_type=mime_type)
    finally:
        # --- Step 4: Hard-delete audio bytes from memory ---
        del audio_bytes
        gc.collect()
        logger.info("Audio bytes deleted from memory — file_id=%s", drive_file_id)

    # --- Step 5: Persist to Postgres ---
    self.update_state(state="PROGRESS", meta={"status": "saving"})

    # Parse recording timestamp
    try:
        meeting_date = datetime.fromisoformat(created_time_iso)
    except ValueError:
        meeting_date = datetime.now(tz=timezone.utc)

    # Duration from last utterance end time
    duration_seconds: int | None = None
    if utterances:
        duration_seconds = utterances[-1]["end_ms"] // 1000

    # Insert Conversation
    conversation_row = {
        "user_id": user_id,
        "title": file_name,
        "source": "google_drive",
        "meeting_date": meeting_date.isoformat(),
        "duration_seconds": duration_seconds,
        "drive_file_id": drive_file_id,
    }
    conv_result = db.table("conversations").insert(conversation_row).execute()
    conversation_id: str = conv_result.data[0]["id"]

    # Bulk insert TranscriptSegments
    if utterances:
        segments = [
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "speaker_id": utt["speaker_id"],
                "start_ms": utt["start_ms"],
                "end_ms": utt["end_ms"],
                "text": utt["text"],
            }
            for utt in utterances
        ]
        db.table("transcript_segments").insert(segments).execute()

    # --- Step 6: Update user_index last_updated ---
    db.table("user_index").update(
        {"last_updated": datetime.now(tz=timezone.utc).isoformat()}
    ).eq("user_id", user_id).execute()

    logger.info(
        "Ingest complete — conversation=%s segments=%d user=%s",
        conversation_id,
        len(utterances),
        user_id,
    )
    return {
        "conversation_id": conversation_id,
        "segment_count": len(utterances),
        "already_existed": False,
    }
