-- ============================================================
-- Pocket Nori — Migration 017: Durable entity nodes
--
-- Adds a canonical entity node layer so entity identity is
-- resolved at write time and reused by search, graph materialization,
-- and browse surfaces.
-- ============================================================

CREATE TABLE IF NOT EXISTS entity_nodes (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_name      TEXT        NOT NULL,
    entity_type         TEXT        NOT NULL CHECK (entity_type IN ('person', 'project', 'company', 'product')),
    mention_count       INT         NOT NULL DEFAULT 0,
    first_mentioned_at  TIMESTAMPTZ NOT NULL,
    last_mentioned_at   TIMESTAMPTZ NOT NULL,
    embedding           vector(1536),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE entity_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_nodes FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'entity_nodes' AND policyname = 'user_isolation'
  ) THEN
    CREATE POLICY "user_isolation" ON entity_nodes
      FOR ALL
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS entity_nodes_user_id_idx
    ON entity_nodes (user_id);

CREATE INDEX IF NOT EXISTS entity_nodes_user_name_idx
    ON entity_nodes (user_id, entity_type, canonical_name);

CREATE INDEX IF NOT EXISTS entity_nodes_user_last_mentioned_idx
    ON entity_nodes (user_id, last_mentioned_at DESC);

CREATE INDEX IF NOT EXISTS entity_nodes_embedding_idx
    ON entity_nodes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS entity_node_id UUID REFERENCES entity_nodes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS entities_user_entity_node_id_idx
    ON entities (user_id, entity_node_id);
