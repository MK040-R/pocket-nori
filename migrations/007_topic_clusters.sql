-- ============================================================
-- Farz — Migration 007: Durable topic clusters
--
-- Adds a canonical topic cluster layer so topics can be merged at
-- ingestion time and read cheaply without clustering on every request.
-- ============================================================

-- ------------------------------------------------------------
-- topic_clusters
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topic_clusters (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_label     TEXT        NOT NULL,
    canonical_summary   TEXT        NOT NULL,
    status              TEXT        NOT NULL CHECK (status IN ('open', 'resolved')),
    first_mentioned_at  TIMESTAMPTZ NOT NULL,
    last_mentioned_at   TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE topic_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_clusters FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'topic_clusters' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON topic_clusters
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS topic_clusters_user_id_idx
    ON topic_clusters (user_id);
CREATE INDEX IF NOT EXISTS topic_clusters_user_label_idx
    ON topic_clusters (user_id, canonical_label);
CREATE INDEX IF NOT EXISTS topic_clusters_user_last_mentioned_idx
    ON topic_clusters (user_id, last_mentioned_at DESC);

-- ------------------------------------------------------------
-- topics.cluster_id
-- ------------------------------------------------------------
ALTER TABLE topics
    ADD COLUMN IF NOT EXISTS cluster_id UUID REFERENCES topic_clusters(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS topics_user_cluster_id_idx
    ON topics (user_id, cluster_id);

-- ------------------------------------------------------------
-- topic_arcs.cluster_id
-- ------------------------------------------------------------
ALTER TABLE topic_arcs
    ADD COLUMN IF NOT EXISTS cluster_id UUID REFERENCES topic_clusters(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS topic_arcs_user_cluster_id_idx
    ON topic_arcs (user_id, cluster_id);
