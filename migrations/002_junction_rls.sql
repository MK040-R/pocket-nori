-- ============================================================
-- Farz — Migration 002: Junction table RLS enforcement
--
-- Context: 001_core_schema.sql was applied before junction tables
-- had user_id columns or RLS policies. This migration adds them
-- to all 8 junction tables on the live database.
--
-- Safe to run: all operations are additive (ADD COLUMN IF NOT EXISTS,
-- CREATE POLICY IF NOT EXISTS, etc.). Will no-op on a fresh DB
-- that ran the updated 001.
-- ============================================================

-- ============================================================
-- topic_segment_links
-- ============================================================
ALTER TABLE topic_segment_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

-- Backfill user_id from the parent topic row
UPDATE topic_segment_links tsl
SET user_id = t.user_id
FROM topics t
WHERE tsl.topic_id = t.id
  AND tsl.user_id IS NULL;

-- Enforce non-null now that backfill is done
ALTER TABLE topic_segment_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE topic_segment_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_segment_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'topic_segment_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON topic_segment_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS topic_segment_links_user_id_idx ON topic_segment_links (user_id);

-- ============================================================
-- commitment_segment_links
-- ============================================================
ALTER TABLE commitment_segment_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE commitment_segment_links csl
SET user_id = c.user_id
FROM commitments c
WHERE csl.commitment_id = c.id
  AND csl.user_id IS NULL;

ALTER TABLE commitment_segment_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE commitment_segment_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE commitment_segment_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'commitment_segment_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON commitment_segment_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS commitment_segment_links_user_id_idx ON commitment_segment_links (user_id);

-- ============================================================
-- entity_segment_links
-- ============================================================
ALTER TABLE entity_segment_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE entity_segment_links esl
SET user_id = e.user_id
FROM entities e
WHERE esl.entity_id = e.id
  AND esl.user_id IS NULL;

ALTER TABLE entity_segment_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE entity_segment_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_segment_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'entity_segment_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON entity_segment_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS entity_segment_links_user_id_idx ON entity_segment_links (user_id);

-- ============================================================
-- topic_arc_conversation_links
-- ============================================================
ALTER TABLE topic_arc_conversation_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE topic_arc_conversation_links tacl
SET user_id = ta.user_id
FROM topic_arcs ta
WHERE tacl.topic_arc_id = ta.id
  AND tacl.user_id IS NULL;

ALTER TABLE topic_arc_conversation_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE topic_arc_conversation_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_arc_conversation_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'topic_arc_conversation_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON topic_arc_conversation_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS topic_arc_conversation_links_user_id_idx ON topic_arc_conversation_links (user_id);

-- ============================================================
-- brief_topic_arc_links
-- ============================================================
ALTER TABLE brief_topic_arc_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE brief_topic_arc_links btal
SET user_id = b.user_id
FROM briefs b
WHERE btal.brief_id = b.id
  AND btal.user_id IS NULL;

ALTER TABLE brief_topic_arc_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE brief_topic_arc_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_topic_arc_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'brief_topic_arc_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON brief_topic_arc_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS brief_topic_arc_links_user_id_idx ON brief_topic_arc_links (user_id);

-- ============================================================
-- brief_commitment_links
-- ============================================================
ALTER TABLE brief_commitment_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE brief_commitment_links bcl
SET user_id = b.user_id
FROM briefs b
WHERE bcl.brief_id = b.id
  AND bcl.user_id IS NULL;

ALTER TABLE brief_commitment_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE brief_commitment_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_commitment_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'brief_commitment_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON brief_commitment_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS brief_commitment_links_user_id_idx ON brief_commitment_links (user_id);

-- ============================================================
-- brief_connection_links
-- ============================================================
ALTER TABLE brief_connection_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE brief_connection_links bcl
SET user_id = b.user_id
FROM briefs b
WHERE bcl.brief_id = b.id
  AND bcl.user_id IS NULL;

ALTER TABLE brief_connection_links
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE brief_connection_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_connection_links FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'brief_connection_links' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON brief_connection_links
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS brief_connection_links_user_id_idx ON brief_connection_links (user_id);

-- ============================================================
-- connection_linked_items
-- ============================================================
ALTER TABLE connection_linked_items
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

UPDATE connection_linked_items cli
SET user_id = c.user_id
FROM connections c
WHERE cli.connection_id = c.id
  AND cli.user_id IS NULL;

ALTER TABLE connection_linked_items
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE connection_linked_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE connection_linked_items FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'connection_linked_items' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON connection_linked_items
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS connection_linked_items_user_id_idx ON connection_linked_items (user_id);
