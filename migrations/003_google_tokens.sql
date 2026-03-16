-- ============================================================
-- Pocket Nori — Migration 003: Google OAuth token storage + Drive dedup
--
-- Adds two columns to user_index so the ingest pipeline can
-- call Google APIs on behalf of the user without redirecting
-- them through the OAuth flow every time.
--
-- Adds drive_file_id to conversations to prevent the same
-- Drive recording being imported twice.
--
-- Safe to run: all operations are additive / IF NOT EXISTS.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Google token storage in user_index
-- ------------------------------------------------------------

ALTER TABLE user_index
    ADD COLUMN IF NOT EXISTS google_access_token  TEXT,
    ADD COLUMN IF NOT EXISTS google_refresh_token TEXT;

-- ------------------------------------------------------------
-- 2. Drive file ID on conversations (idempotency / deduplication)
-- ------------------------------------------------------------

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS drive_file_id TEXT;

-- Unique index: prevents the same recording being imported twice
-- per user. NULLs are exempt from uniqueness in PostgreSQL, so
-- conversations from other sources (drive_file_id = NULL) are
-- unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS conversations_user_drive_file_unique
    ON conversations (user_id, drive_file_id)
    WHERE drive_file_id IS NOT NULL;

-- Index for fast look-up by drive_file_id
CREATE INDEX IF NOT EXISTS conversations_drive_file_id_idx
    ON conversations (drive_file_id)
    WHERE drive_file_id IS NOT NULL;
