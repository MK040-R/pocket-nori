-- Migration 012: Add category column to conversations for meeting tagging.
--
-- Allows auto-classification during AI extraction and manual override via PATCH.
-- Valid categories: strategy, client, 1on1, agency, partner, team, other.

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS category TEXT DEFAULT NULL;

-- Add CHECK constraint (idempotent via DO block)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'conversations_category_check'
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_category_check
            CHECK (category IS NULL OR category IN ('strategy', 'client', '1on1', 'agency', 'partner', 'team', 'other'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_user_category
    ON conversations (user_id, category)
    WHERE category IS NOT NULL;
