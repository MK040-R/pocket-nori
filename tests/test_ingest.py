"""
tests/test_ingest.py — Unit tests for the ingest_recording Celery task.

All tests use unittest.mock to patch external services (Google Drive, Supabase).
No network calls, no credentials needed.

Run:
    pytest tests/test_ingest.py -v -m unit
"""

import uuid
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.workers.ingest import (
    _detect_and_parse,
    _parse_gemini_notes,
    _parse_google_transcript,
    ingest_recording,
)

# ---------------------------------------------------------------------------
# _parse_google_transcript unit tests
# ---------------------------------------------------------------------------

_SAMPLE_TRANSCRIPT = """\
Alice
00:00
Hello everyone, welcome to the meeting.

Bob
00:15
Thanks for joining us today.

Alice
00:30
Let's go through the agenda.
"""


@pytest.mark.unit
class TestParseGoogleTranscript:
    def test_parses_basic_transcript(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        assert len(segments) == 3
        assert segments[0]["speaker_id"] == "Alice"
        assert segments[1]["speaker_id"] == "Bob"
        assert segments[2]["speaker_id"] == "Alice"

    def test_parses_timestamps_to_ms(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        assert segments[0]["start_ms"] == 0
        assert segments[1]["start_ms"] == 15_000
        assert segments[2]["start_ms"] == 30_000

    def test_text_content_preserved(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        assert "Hello everyone" in segments[0]["text"]
        assert "Thanks for joining" in segments[1]["text"]
        assert "agenda" in segments[2]["text"]

    def test_end_ms_backfilled_from_next_segment(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        # First segment end_ms should equal second segment start_ms
        assert segments[0]["end_ms"] == segments[1]["start_ms"]
        assert segments[1]["end_ms"] == segments[2]["start_ms"]

    def test_last_segment_end_ms_estimated_from_word_count(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        # Last segment has no next — estimated from word count
        last = segments[-1]
        assert last["end_ms"] > last["start_ms"]

    def test_empty_input_returns_empty_list(self) -> None:
        assert _parse_google_transcript("") == []

    def test_hh_mm_ss_timestamp_parsed(self) -> None:
        text = "Alice\n01:02:03\nSomething was said.\n"
        segments = _parse_google_transcript(text)
        assert len(segments) == 1
        expected_ms = (1 * 3600 + 2 * 60 + 3) * 1000
        assert segments[0]["start_ms"] == expected_ms

    def test_block_without_timestamp_gets_estimated_start(self) -> None:
        text = "Alice\nHello world this is my segment.\n"
        segments = _parse_google_transcript(text)
        assert len(segments) == 1
        assert segments[0]["start_ms"] == 0  # cursor starts at 0

    def test_minimum_end_ms_duration(self) -> None:
        """Even a single-word segment must have end_ms > start_ms."""
        text = "Alice\n00:00\nHi.\n"
        segments = _parse_google_transcript(text)
        assert segments[0]["end_ms"] > segments[0]["start_ms"]

    def test_crlf_line_endings_normalised(self) -> None:
        text = "Alice\r\n00:00\r\nHello world.\r\n\r\nBob\r\n00:10\r\nHi there.\r\n"
        segments = _parse_google_transcript(text)
        assert len(segments) == 2

    def test_all_segments_have_required_keys(self) -> None:
        segments = _parse_google_transcript(_SAMPLE_TRANSCRIPT)
        for seg in segments:
            assert "speaker_id" in seg
            assert "start_ms" in seg
            assert "end_ms" in seg
            assert "text" in seg


# ---------------------------------------------------------------------------
# ingest_recording unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIngestRecordingUnit:
    def _run_task(
        self,
        eager_ingest: Any,
        drive_file_id: str = "file-abc",
        file_name: str = "Meeting 2025-03-01",
        created_time_iso: str = "2025-03-01T10:00:00+00:00",
        user_id: str = "user-123",
        user_jwt: str = "jwt-token",
        google_refresh_token: str = "refresh-token",
    ) -> dict[str, Any]:
        result = ingest_recording.delay(
            drive_file_id=drive_file_id,
            file_name=file_name,
            created_time_iso=created_time_iso,
            user_id=user_id,
            user_jwt=user_jwt,
            google_refresh_token=google_refresh_token,
        ).get()
        return cast(dict[str, Any], result)

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
        """Happy path: export transcript → parse → save → return conversation_id."""
        new_conv_id = str(uuid.uuid4())
        transcript_text = (
            "Alice\n00:00\nHello everyone welcome to the meeting.\n\n"
            "Bob\n00:15\nThanks for joining us today.\n"
        )

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="access-token"),
            patch("src.workers.ingest.export_transcript_sync", return_value=transcript_text),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.return_value.execute.return_value.data = [
                {"id": new_conv_id}
            ]
            mock_get_client.return_value = db

            result = self._run_task(eager_ingest)

        assert result["already_existed"] is False
        assert result["conversation_id"] == new_conv_id
        assert result["segment_count"] == 2

    def test_ingest_chains_extract_and_embed(self, eager_ingest: Any) -> None:
        """After a successful ingest, extract and embed tasks must be queued."""
        new_conv_id = str(uuid.uuid4())
        transcript_text = "Alice\n00:00\nHello.\n"

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch("src.workers.ingest.export_transcript_sync", return_value=transcript_text),
            patch("src.workers.ingest.extract_from_conversation.delay") as mock_extract,
            patch("src.workers.ingest.embed_conversation.delay") as mock_embed,
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.return_value.execute.return_value.data = [
                {"id": new_conv_id}
            ]
            mock_get_client.return_value = db

            self._run_task(eager_ingest)

        mock_extract.assert_called_once()
        mock_embed.assert_called_once()

    def test_export_error_propagates(self, eager_ingest: Any) -> None:
        """If export_transcript_sync raises, the task should propagate the error."""
        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch(
                "src.workers.ingest.export_transcript_sync",
                side_effect=RuntimeError("Drive API down"),
            ),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            mock_get_client.return_value = db

            with pytest.raises(RuntimeError, match="Drive API down"):
                self._run_task(eager_ingest)

    def test_user_id_isolation_in_conversation_insert(self, eager_ingest: Any) -> None:
        """The user_id passed to the task must appear in the inserted conversation row."""
        expected_user_id = "user-isolation-test"
        inserted_rows: list[dict[str, Any]] = []
        transcript_text = "Alice\n00:00\nHello world.\n"

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
            patch("src.workers.ingest.export_transcript_sync", return_value=transcript_text),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.side_effect = capture_insert
            mock_get_client.return_value = db

            self._run_task(eager_ingest, user_id=expected_user_id)

        assert any(row.get("user_id") == expected_user_id for row in inserted_rows)

    def test_empty_transcript_saves_zero_segments(self, eager_ingest: Any) -> None:
        """A transcript with no parseable content creates a conversation with 0 segments."""
        new_conv_id = str(uuid.uuid4())

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch("src.workers.ingest.export_transcript_sync", return_value=""),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.return_value.execute.return_value.data = [
                {"id": new_conv_id}
            ]
            mock_get_client.return_value = db

            result = self._run_task(eager_ingest)

        assert result["segment_count"] == 0
        assert result["already_existed"] is False

    def test_result_includes_drive_file_id(self, eager_ingest: Any) -> None:
        """Result dict must include drive_file_id for the caller to correlate jobs."""
        file_id = "drive-file-xyz"
        transcript_text = "Alice\n00:00\nHello.\n"

        with (
            patch("src.workers.ingest.get_client") as mock_get_client,
            patch("src.workers.ingest.refresh_access_token_sync", return_value="token"),
            patch("src.workers.ingest.export_transcript_sync", return_value=transcript_text),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.return_value.execute.return_value.data = [
                {"id": str(uuid.uuid4())}
            ]
            mock_get_client.return_value = db

            result = self._run_task(eager_ingest, drive_file_id=file_id)

        assert result["drive_file_id"] == file_id


# ---------------------------------------------------------------------------
# _parse_gemini_notes unit tests
# ---------------------------------------------------------------------------

_SAMPLE_GEMINI_NOTES = """\
Natasha / Murali - 2026/03/03 14:30 - Notes by Gemini

Summary
This meeting covered project status updates and upcoming deadlines for Q1.

Next steps
• Murali to send updated roadmap by Friday
• Natasha to review the design mockups

Key decisions
The team agreed to postpone the launch by two weeks to allow for additional testing.
"""


@pytest.mark.unit
class TestParseGeminiNotes:
    def test_creates_segments_from_sections(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        assert len(segments) >= 3  # Summary, Next steps, Key decisions

    def test_speaker_id_is_gemini_notes(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        for seg in segments:
            assert seg["speaker_id"] == "Gemini Notes"

    def test_all_segments_have_required_keys(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        for seg in segments:
            assert "speaker_id" in seg
            assert "start_ms" in seg
            assert "end_ms" in seg
            assert "text" in seg

    def test_end_ms_greater_than_start_ms(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        for seg in segments:
            assert seg["end_ms"] > seg["start_ms"]

    def test_title_line_skipped(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        for seg in segments:
            assert "Notes by Gemini" not in seg["text"]

    def test_empty_input_returns_empty_list(self) -> None:
        assert _parse_gemini_notes("") == []

    def test_content_preserved(self) -> None:
        segments = _parse_gemini_notes(_SAMPLE_GEMINI_NOTES)
        all_text = " ".join(s["text"] for s in segments)
        assert "project status" in all_text.lower() or "summary" in all_text.lower()


# ---------------------------------------------------------------------------
# _detect_and_parse unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectAndParse:
    def test_timestamped_text_uses_transcript_parser(self) -> None:
        text = "Alice\n00:00\nHello everyone.\n\nBob\n00:15\nHi there.\n"
        segments, source_type = _detect_and_parse(text)
        assert source_type == "google_meet_transcript"
        assert segments[0]["speaker_id"] == "Alice"

    def test_notes_text_uses_gemini_parser(self) -> None:
        segments, source_type = _detect_and_parse(_SAMPLE_GEMINI_NOTES)
        assert source_type == "gemini_notes"
        assert all(s["speaker_id"] == "Gemini Notes" for s in segments)

    def test_source_type_stored_in_ingest_result(self, eager_ingest: Any) -> None:
        """source field in the conversation row must reflect the detected format."""
        inserted_rows: list[dict[str, Any]] = []

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
            patch("src.workers.ingest.export_transcript_sync", return_value=_SAMPLE_GEMINI_NOTES),
            patch("src.workers.ingest.extract_from_conversation.delay"),
            patch("src.workers.ingest.embed_conversation.delay"),
        ):
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            db.table.return_value.insert.side_effect = capture_insert
            mock_get_client.return_value = db

            from src.workers.ingest import ingest_recording as _ingest

            _ingest.delay(
                drive_file_id="geminidoc",
                file_name="Meeting Notes",
                created_time_iso="2026-03-03T10:00:00+00:00",
                user_id="user-1",
                user_jwt="jwt",
                google_refresh_token="refresh",
            ).get()

        conv_rows = [r for r in inserted_rows if r.get("source")]
        assert any(r["source"] == "gemini_notes" for r in conv_rows)
