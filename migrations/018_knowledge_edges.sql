-- ============================================================
-- Pocket Nori — Migration 018: Knowledge edges and evidence
--
-- Adds typed graph edges plus explainable evidence rows.
-- ============================================================

CREATE TABLE IF NOT EXISTS knowledge_edges (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type     TEXT        NOT NULL CHECK (source_type IN ('topic_node', 'entity_node', 'commitment')),
    source_id       UUID        NOT NULL,
    target_type     TEXT        NOT NULL CHECK (target_type IN ('topic_node', 'entity_node', 'commitment')),
    target_id       UUID        NOT NULL,
    relation_type   TEXT        NOT NULL,
    confidence      REAL        NOT NULL DEFAULT 1.0,
    evidence_count  INT         NOT NULL DEFAULT 1,
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source_type, source_id, target_type, target_id, relation_type)
);

ALTER TABLE knowledge_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edges FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'knowledge_edges' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON knowledge_edges
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS knowledge_edges_user_source_idx
    ON knowledge_edges (user_id, source_type, source_id);

CREATE INDEX IF NOT EXISTS knowledge_edges_user_target_idx
    ON knowledge_edges (user_id, target_type, target_id);

CREATE INDEX IF NOT EXISTS knowledge_edges_user_relation_idx
    ON knowledge_edges (user_id, relation_type, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_edge_evidence (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    edge_id         UUID        NOT NULL REFERENCES knowledge_edges(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    segment_id      UUID        REFERENCES transcript_segments(id) ON DELETE CASCADE,
    snippet         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE knowledge_edge_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edge_evidence FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'knowledge_edge_evidence' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON knowledge_edge_evidence
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS knowledge_edge_evidence_user_conversation_idx
    ON knowledge_edge_evidence (user_id, conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS knowledge_edge_evidence_edge_idx
    ON knowledge_edge_evidence (edge_id, conversation_id, segment_id);
