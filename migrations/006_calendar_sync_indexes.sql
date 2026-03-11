-- ============================================================
-- Migration 006 — Calendar sync query indexes
--
-- Improves Phase 4 calendar linking query performance:
-- conversations filtered by user_id + meeting_date and
-- conversations looked up by user_id + calendar_event_id.
-- ============================================================

CREATE INDEX IF NOT EXISTS conversations_user_meeting_date_idx
    ON conversations (user_id, meeting_date);

CREATE INDEX IF NOT EXISTS conversations_user_calendar_event_id_idx
    ON conversations (user_id, calendar_event_id)
    WHERE calendar_event_id IS NOT NULL;
