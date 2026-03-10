"""
tests/test_ingest.py — Unit tests for the ingest_recording Celery task.

All tests use pytest-mock to patch external services (Google Drive, Deepgram,
Supabase). No network calls, no credentials needed.

Run:
    pytest tests/test_ingest.py -v -m unit
"""

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.workers.ingest import _transcribe_bytes, ingest_recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_mock(existing_drive_file: bool = False) -> MagicMock:
    """Return a mock Supabase client that simulates the DB responses."""
    db = MagicMock()

    # conversations.select — used for idempotency check
    existing_data = [{"id": str(uuid.uuid4())}] if existing_drive_file else []
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        existing_data
    )

    # conversations.insert — returns a new conversation row
    new_conv_id = str(uuid.uuid4())
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": new_conv_id}]

    return db, new_conv_id


# ---------------------------------------------------------------------------
# _transcribe_bytes unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTranscribeBytes:
    def test_returns_utterance_list(self) -> None:
        """_transcribe_bytes should return a list of utterance dicts."""
        mock_utt = MagicMock()
        mock_utt.speaker = 0
        mock_utt.start = 0.0
        mock_utt.end = 5.5
        mock_utt.transcript = "Hello from speaker zero."

        mock_response = MagicMock()
        mock_response.results.utterances = [mock_utt]

        with patch("src.workers.ingest.DeepgramClient") as mock_deepgram_cls:
            mock_deepgram_cls.return_value.listen.rest.v.return_value.transcribe_file.return_value = (
                mock_response
            )
            result = _transcribe_bytes(b"fake-audio-bytes")

        assert len(result) == 1
        assert result[0]["speaker_id"] == "speaker_0"
        assert result[0]["start_ms"] == 0
        assert result[0]["end_ms"] == 5500
        assert result[0]["text"] == "Hello from speaker zero."

    def test_returns_empty_list_when_no_utterances(self) -> None:
        mock_response = MagicMock()
        mock_response.results.utterances = []

        with patch("src.workers.ingest.DeepgramClient") as mock_deepgram_cls:
            mock_deepgram_cls.return_value.listen.rest.v.return_value.transcribe_file.return_value = (
                mock_response
            )
            result = _transcribe_bytes(b"silence")

        assert result == []

    def test_returns_empty_list_when_results_none(self) -> None:
        mock_response = MagicMock()
        mock_response.results = None

        with patch("src.workers.ingest.DeepgramClient") as mock_deepgram_cls:
            mock_deepgram_cls.return_value.listen.rest.v.return_value.transcribe_file.return_value = (
                mock_response
            )
            result = _transcribe_bytes(b"audio")

        assert result == []

    def test_millisecond_conversion(self) -> None:
        """Start/end seconds from Deepgram should be converted to milliseconds."""
        mock_utt = MagicMock()
        mock_utt.speaker = 1
        mock_utt.start = 10.25
        mock_utt.end = 45.75
        mock_utt.transcript = "Some content."

        mock_response = MagicMock()
        mock_response.results.utterances = [mock_utt]

        with patch("src.workers.ingest.DeepgramClient") as mock_deepgram_cls:
            mock_deepgram_cls.return_value.listen.rest.v.return_value.transcribe_file.return_value = (
                mock_response
            )
            result = _transcribe_bytes(b"audio")

        assert result[0]["start_ms"] == 10250
        assert result[0]["end_ms"] == 45750


# ---------------------------------------------------------------------------
# ingest_recording unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIngestRecordingUnit:
    def _run_task(
        self,
        eager_ingest: Any,
        drive_file_id: str = "file-abc",
        file_name: str = "Recording 2025-03-01.mp4",
        created_time_iso: str = "2025-03-01T10:00:00+00:00",
        mime_type: str = "video/mp4",
        user_id: str = "user-123",
        user_jwt: str = "jwt-token",
        google_refresh_token: str = "refresh-token",
    ) -> dict[str, Any]:
        return ingest_recording.delay(
            drive_file_id=drive_file_id,
            file_name=file_name,
            created_time_iso=created_time_iso,
            mime_type=mime_type,
            user_id=user_id,
            user_jwt=user_jwt,
            google_refresh_token=google_refresh_token,
        ).get()

    def test_raises_on_empty_drive_file_id(self, eager_ingest: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run_task(eager_ingest, drive_file_id="")

    def test_raises_on_empty_user_id(self, eager_ingest: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run_task(eager_ingest, user_id="")

    def test_raises_on_empty_user_jwt(self, eager_ingest: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run_task(eager_ingest, user_jwt="")

    def test_raises_on_empty_refresh_token(self, eager_ingest: Any) -> None:
        with pytest.raises(ValueError, match="required"):
            self._run_task(eager_ingest, google_refresh_token="")

    def test_skips_already_imported_recording(self, eager_ingest: Any) -> None:
        """When the drive_file_id is already in conversations, returns already_existed=True."""
        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="new-token"),
        ):
            db = MagicMock()
            # Simulate: conversation with this drive_file_id already exists
            existing_id = str(uuid.uuid4())
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"id": existing_id}
            ]
            mock_get_client.return_value = db

            result = self._run_task(eager_ingest)

        assert result["already_existed"] is True
        assert result["conversation_id"] == existing_id
        assert result["segment_count"] == 0

    def test_full_ingest_creates_conversation_and_segments(self, eager_ingest: Any) -> None:
        """Happy path: download → transcribe → save → return conversation_id."""
        new_conv_id = str(uuid.uuid4())

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="access-token"),
            patch("src.workers.ingest.download_recording_sync", return_value=b"audio-bytes"),
            patch("src.workers.ingest._transcribe_bytes") as mock_transcribe,
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            mock_transcribe.return_value = [
                {"speaker_id": "speaker_0", "start_ms": 0, "end_ms": 5000, "text": "Hello."},
                {"speaker_id": "speaker_1", "start_ms": 5100, "end_ms": 10000, "text": "Hi there."},
            ]

            db = MagicMock()
            # No existing conversation
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            # Insert conversation returns new ID
            db.table.return_value.insert.return_value.execute.return_value.data = [{"id": new_conv_id}]
            mock_get_client.return_value = db

            result = self._run_task(eager_ingest)

        assert result["already_existed"] is False
        assert result["conversation_id"] == new_conv_id
        assert result["segment_count"] == 2

    def test_audio_bytes_deleted_even_on_transcription_error(self, eager_ingest: Any) -> None:
        """gc.collect() is called even if transcription raises — audio is never retained."""

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch("src.workers.ingest.download_recording_sync", return_value=b"audio"),
            patch("src.workers.ingest._transcribe_bytes", side_effect=RuntimeError("Deepgram down")),
            patch("src.workers.ingest.gc.collect") as mock_gc,
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            mock_get_client.return_value = db

            with pytest.raises(RuntimeError, match="Deepgram down"):
                self._run_task(eager_ingest)

        mock_gc.assert_called()

    def test_user_id_isolation_in_conversation_insert(self, eager_ingest: Any) -> None:
        """The user_id passed to the task must appear in the inserted conversation row."""
        expected_user_id = "user-isolation-test"
        inserted_rows: list[dict] = []

        def capture_insert(data: Any) -> Any:
            if isinstance(data, dict):
                inserted_rows.append(data)
            elif isinstance(data, list):
                inserted_rows.extend(data)
            mock_result = MagicMock()
            mock_result.execute.return_value.data = [{"id": str(uuid.uuid4())}]
            return mock_result

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch("src.workers.ingest.download_recording_sync", return_value=b"audio"),
            patch("src.workers.ingest._transcribe_bytes", return_value=[]),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.side_effect = capture_insert
            mock_get_client.return_value = db

            self._run_task(eager_ingest, user_id=expected_user_id)

        # The conversation insert should carry the correct user_id
        assert any(row.get("user_id") == expected_user_id for row in inserted_rows)
