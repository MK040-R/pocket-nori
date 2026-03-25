"""
Ingest worker — Google Meet transcript pipeline.

Pipeline per transcript:
  1. Refresh Google access token (refresh_token → fresh access_token)
  2. Export transcript text from Google Drive (Google Doc → plain text)
  3. Parse plain text into speaker segments
  4. Persist Conversation + TranscriptSegments to Postgres (via RLS-scoped client)
  5. Update user_index.last_updated

Rules:
- Transcript content is NEVER logged — only IDs and counts.
- user_jwt is used for all DB operations (RLS enforced, never service_role).
- drive_file_id uniqueness prevents double-import (handled by DB unique index).
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import chain

from src.celery_app import celery_app as celery_app
from src.config import settings  # noqa: F401 — imported for startup validation
from src.database import get_client
from src.drive_client import export_transcript_sync, refresh_access_token_sync
from src.workers.embed import embed_conversation
from src.workers.extract import extract_from_conversation

logger = logging.getLogger(__name__)

# Average speaking rate used to estimate end_ms when the transcript has no
# end timestamp for a segment (130 words per minute → ~462 ms per word).
_MS_PER_WORD = int(60_000 / 130)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _timestamp_to_ms(ts: str) -> int:
    """Convert a MM:SS or HH:MM:SS timestamp string to milliseconds."""
    parts = ts.strip().split(":")
    try:
        if len(parts) == 2:  # MM:SS
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        if len(parts) == 3:  # HH:MM:SS
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    except ValueError:
        pass
    return 0


def _parse_google_transcript(text: str) -> list[dict[str, Any]]:
    """Parse a Google Meet plain-text transcript export into speaker segments.

    Google Meet exports transcripts in this format:
        Speaker Name
        00:00
        What they said

        Other Speaker
        00:15
        Their response

    Returns a list of dicts with keys:
        speaker_id (str), start_ms (int), end_ms (int), text (str)

    If timestamps are missing, start_ms is estimated from position and end_ms
    is estimated from word count at 130 wpm.
    """
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into non-empty blocks separated by blank lines
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]

    ts_re = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")

    segments: list[dict[str, Any]] = []
    cursor_ms = 0

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        speaker = lines[0]

        # Identify timestamp line (MM:SS or HH:MM:SS)
        ts_ms: int | None = None
        text_lines: list[str] = []
        for ln in lines[1:]:
            if ts_ms is None and ts_re.match(ln):
                ts_ms = _timestamp_to_ms(ln)
            else:
                text_lines.append(ln)

        segment_text = " ".join(text_lines).strip()
        if not segment_text:
            continue

        start_ms = ts_ms if ts_ms is not None else cursor_ms
        word_count = len(segment_text.split())
        estimated_duration = max(word_count * _MS_PER_WORD, 1000)

        segments.append(
            {
                "speaker_id": speaker,
                "start_ms": start_ms,
                "end_ms": start_ms + estimated_duration,
                "text": segment_text,
            }
        )
        cursor_ms = start_ms + estimated_duration

    # Back-fill end_ms: use next segment's start_ms when available
    for i in range(len(segments) - 1):
        next_start = segments[i + 1]["start_ms"]
        if next_start > segments[i]["start_ms"]:
            segments[i]["end_ms"] = next_start

    logger.info("Parsed %d segments from transcript", len(segments))
    return segments


_TS_DETECT_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$", re.MULTILINE)


def _parse_gemini_notes(text: str) -> list[dict[str, Any]]:
    """Parse a Google Meet 'Notes by Gemini' document into content segments.

    Gemini Notes are AI-generated meeting summaries with sections like
    Summary, Next steps, Action items — no speaker timestamps.

    Each non-empty paragraph becomes a segment with speaker_id='Gemini Notes'
    and start_ms estimated sequentially from word count.

    Returns a list of dicts with keys:
        speaker_id (str), start_ms (int), end_ms (int), text (str)
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]

    segments: list[dict[str, Any]] = []
    cursor_ms = 0

    for i, block in enumerate(blocks):
        # Skip the document title (first block, typically the meeting name)
        if i == 0 and len(block.splitlines()) == 1:
            continue

        word_count = len(block.split())
        if word_count == 0:
            continue

        duration_ms = max(word_count * _MS_PER_WORD, 1000)
        segments.append(
            {
                "speaker_id": "Gemini Notes",
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + duration_ms,
                "text": block,
            }
        )
        cursor_ms += duration_ms

    logger.info("Parsed %d segments from Gemini Notes document", len(segments))
    return segments


def _detect_and_parse(text: str) -> tuple[list[dict[str, Any]], str]:
    """Auto-detect document format and return (segments, source_type).

    - If the text contains MM:SS or HH:MM:SS timestamp lines → standard
      Google Meet transcript format; source_type = 'google_meet_transcript'
    - Otherwise → Gemini Notes format; source_type = 'gemini_notes'
    """
    if _TS_DETECT_RE.search(text):
        return _parse_google_transcript(text), "google_meet_transcript"
    return _parse_gemini_notes(text), "gemini_notes"


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=600,
)
def ingest_recording(
    self: Any,
    drive_file_id: str,
    file_name: str,
    created_time_iso: str,
    user_id: str,
    user_jwt: str,
    google_refresh_token: str,
) -> dict[str, Any]:
    """Export, parse, and persist a single Google Meet transcript.

    Args:
        drive_file_id: Google Drive file ID of the transcript Google Doc.
        file_name: Human-readable name (used as conversation title).
        created_time_iso: ISO-8601 timestamp of the transcript (from Drive metadata).
        user_id: Supabase user UUID (for per-user isolation).
        user_jwt: Supabase JWT — used for all DB writes (RLS enforced).
        google_refresh_token: Used to obtain a fresh Google access token.

    Returns:
        dict with conversation_id, segment_count, and already_existed flag.
    """
    required = [drive_file_id, file_name, created_time_iso, user_id, user_jwt, google_refresh_token]
    if not all(required):
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
        logger.info("Transcript already imported — conversation=%s, skipping", conversation_id)
        return {
            "conversation_id": conversation_id,
            "segment_count": 0,
            "already_existed": True,
            "user_id": user_id,
            "drive_file_id": drive_file_id,
        }

    # --- Step 1: Refresh Google access token ---
    self.update_state(state="PROGRESS", meta={"status": "authenticating", "user_id": user_id})
    access_token = refresh_access_token_sync(google_refresh_token)

    # --- Step 2: Export transcript text from Google Drive ---
    self.update_state(state="PROGRESS", meta={"status": "fetching_transcript", "user_id": user_id})
    transcript_text = export_transcript_sync(access_token, drive_file_id)

    # --- Step 3: Parse transcript into segments (auto-detects format) ---
    self.update_state(state="PROGRESS", meta={"status": "parsing", "user_id": user_id})
    utterances, source_type = _detect_and_parse(transcript_text)

    # --- Step 4: Persist to Postgres ---
    self.update_state(state="PROGRESS", meta={"status": "saving", "user_id": user_id})

    try:
        meeting_date = datetime.fromisoformat(created_time_iso)
    except ValueError:
        meeting_date = datetime.now(tz=UTC)

    duration_seconds: int | None = None
    if utterances:
        duration_seconds = utterances[-1]["end_ms"] // 1000

    conversation_row = {
        "user_id": user_id,
        "title": file_name,
        "source": source_type,
        "meeting_date": meeting_date.isoformat(),
        "duration_seconds": duration_seconds,
        "drive_file_id": drive_file_id,
    }
    conv_result = db.table("conversations").insert(conversation_row).execute()
    conversation_id = conv_result.data[0]["id"]

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

    # --- Step 5: Update user_index conversation_count + last_updated ---
    existing_index = (
        db.table("user_index").select("conversation_count").eq("user_id", user_id).execute()
    )
    if existing_index.data:
        current_conversation_count = int(existing_index.data[0].get("conversation_count") or 0)
        db.table("user_index").update(
            {
                "conversation_count": current_conversation_count + 1,
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()

    logger.info(
        "Ingest complete — conversation=%s segments=%d user=%s",
        conversation_id,
        len(utterances),
        user_id,
    )

    # --- Chain downstream tasks: extraction then embedding (ordered) ---
    chain(
        extract_from_conversation.si(
            conversation_id=conversation_id,
            user_id=user_id,
            user_jwt=user_jwt,
            google_refresh_token=google_refresh_token,
        ),
        embed_conversation.si(
            conversation_id=conversation_id,
            user_id=user_id,
            user_jwt=user_jwt,
        ),
    ).apply_async()

    return {
        "conversation_id": conversation_id,
        "segment_count": len(utterances),
        "already_existed": False,
        "user_id": user_id,
        "drive_file_id": drive_file_id,
    }
