-- ============================================================
-- Pocket Nori — Core Schema Migration 001
-- Hard-delete only: no deleted_at columns anywhere.
-- Per-user isolation enforced via FORCE ROW LEVEL SECURITY.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Extensions
-- ------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- 2. Tables (dependency order)
-- ------------------------------------------------------------

-- user_index: one row per user
CREATE TABLE IF NOT EXISTS user_index (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_count  INT NOT NULL DEFAULT 0,
    topic_count         INT NOT NULL DEFAULT 0,
    commitment_count    INT NOT NULL DEFAULT 0,
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_index_user_id_unique UNIQUE (user_id)
);

-- conversations
CREATE TABLE IF NOT EXISTS conversations (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title               TEXT        NOT NULL,
    source              TEXT        NOT NULL,
    meeting_date        TIMESTAMPTZ NOT NULL,
    duration_seconds    INT,
    calendar_event_id   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- transcript_segments
CREATE TABLE IF NOT EXISTS transcript_segments (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    speaker_id      TEXT        NOT NULL,
    speaker_name    TEXT,
    start_ms        INT         NOT NULL,
    end_ms          INT         NOT NULL,
    text            TEXT        NOT NULL,
    embedding       vector(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- topics
CREATE TABLE IF NOT EXISTS topics (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    label           TEXT        NOT NULL,
    summary         TEXT        NOT NULL,
    status          TEXT        NOT NULL CHECK (status IN ('open', 'resolved')),
    key_quotes      TEXT[]      NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- commitments
CREATE TABLE IF NOT EXISTS commitments (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    text            TEXT        NOT NULL,
    owner           TEXT        NOT NULL,
    due_date        TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- entities
CREATE TABLE IF NOT EXISTS entities (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    type            TEXT        NOT NULL CHECK (type IN ('person', 'project', 'company', 'product')),
    mentions        INT         NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- topic_arcs
CREATE TABLE IF NOT EXISTS topic_arcs (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    topic_id    UUID        NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    summary     TEXT        NOT NULL,
    trend       TEXT        NOT NULL CHECK (trend IN ('growing', 'stable', 'resolved')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- connections
CREATE TABLE IF NOT EXISTS connections (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    label       TEXT        NOT NULL,
    linked_type TEXT        NOT NULL CHECK (linked_type IN ('conversation', 'topic')),
    summary     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- briefs
CREATE TABLE IF NOT EXISTS briefs (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id     UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    calendar_event_id   TEXT,
    content             TEXT        NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. Junction tables
-- ------------------------------------------------------------

-- topic ↔ segment links
CREATE TABLE IF NOT EXISTS topic_segment_links (
    topic_id    UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    segment_id  UUID NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, segment_id)
);

-- commitment ↔ segment links
CREATE TABLE IF NOT EXISTS commitment_segment_links (
    commitment_id   UUID NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
    segment_id      UUID NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    PRIMARY KEY (commitment_id, segment_id)
);

-- entity ↔ segment links
CREATE TABLE IF NOT EXISTS entity_segment_links (
    entity_id   UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    segment_id  UUID NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, segment_id)
);

-- topic_arc ↔ conversation links
CREATE TABLE IF NOT EXISTS topic_arc_conversation_links (
    topic_arc_id    UUID NOT NULL REFERENCES topic_arcs(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_arc_id, conversation_id)
);

-- brief ↔ topic_arc links
CREATE TABLE IF NOT EXISTS brief_topic_arc_links (
    brief_id        UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    topic_arc_id    UUID NOT NULL REFERENCES topic_arcs(id) ON DELETE CASCADE,
    PRIMARY KEY (brief_id, topic_arc_id)
);

-- brief ↔ commitment links
CREATE TABLE IF NOT EXISTS brief_commitment_links (
    brief_id        UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    commitment_id   UUID NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
    PRIMARY KEY (brief_id, commitment_id)
);

-- brief ↔ connection links
CREATE TABLE IF NOT EXISTS brief_connection_links (
    brief_id        UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    connection_id   UUID NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    PRIMARY KEY (brief_id, connection_id)
);

-- connection linked items (conversation or topic ids)
CREATE TABLE IF NOT EXISTS connection_linked_items (
    connection_id   UUID NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    linked_id       UUID NOT NULL,
    PRIMARY KEY (connection_id, linked_id)
);

-- ------------------------------------------------------------
-- 4. Row Level Security
-- ------------------------------------------------------------

-- user_index
ALTER TABLE user_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_index FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON user_index
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON conversations
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- transcript_segments
ALTER TABLE transcript_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcript_segments FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON transcript_segments
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- topics
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON topics
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- commitments
ALTER TABLE commitments ENABLE ROW LEVEL SECURITY;
ALTER TABLE commitments FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON commitments
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- entities
ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON entities
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- topic_arcs
ALTER TABLE topic_arcs ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_arcs FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON topic_arcs
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- connections
ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON connections
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- briefs
ALTER TABLE briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefs FORCE ROW LEVEL SECURITY;
CREATE POLICY "user_isolation" ON briefs
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ------------------------------------------------------------
-- 5. Indexes
-- ------------------------------------------------------------

-- user_id lookup indexes on all user-owned tables
CREATE INDEX ON user_index (user_id);
CREATE INDEX ON conversations (user_id);
CREATE INDEX ON transcript_segments (user_id);
CREATE INDEX ON topics (user_id);
CREATE INDEX ON commitments (user_id);
CREATE INDEX ON entities (user_id);
CREATE INDEX ON topic_arcs (user_id);
CREATE INDEX ON connections (user_id);
CREATE INDEX ON briefs (user_id);

-- Foreign key indexes
CREATE INDEX ON transcript_segments (conversation_id);
CREATE INDEX ON topics (conversation_id);
CREATE INDEX ON commitments (conversation_id);
CREATE INDEX ON entities (conversation_id);
CREATE INDEX ON topic_arcs (topic_id);
CREATE INDEX ON briefs (conversation_id);

-- pgvector ANN index on transcript_segments embeddings
CREATE INDEX ON transcript_segments USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
