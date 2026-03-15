-- Migration 009: Rich embeddings for intelligent search
--
-- Adds:
--   1. conversations.digest          — LLM-generated plain-text meeting summary (stored once at ingest)
--   2. conversations.digest_embedding — vector(1536) embedding of the digest
--   3. topic_clusters.embedding      — vector(1536) embedding of canonical_label + canonical_summary
--   4. entities.embedding            — vector(1536) embedding of name + type
--
-- All embeddings are generated once at ingest time (one small LLM call per meeting, cheap
-- OpenAI embedding calls). At query time, only the user's query is embedded — zero LLM
-- tokens consumed per search request.
--
-- IVFFlat indexes are created with lists=100 (appropriate for up to ~1M rows per user index).
-- The pgvector extension is already enabled from migration 001.

-- 1. Meeting-level digest and its embedding
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS digest TEXT,
    ADD COLUMN IF NOT EXISTS digest_embedding vector(1536);

-- 2. Topic cluster semantic embedding
ALTER TABLE topic_clusters
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- 3. Entity semantic embedding
ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- 4. ANN indexes for cosine similarity search
CREATE INDEX IF NOT EXISTS topic_clusters_embedding_idx
    ON topic_clusters USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS entities_embedding_idx
    ON entities USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS conversations_digest_embedding_idx
    ON conversations USING ivfflat (digest_embedding vector_cosine_ops)
    WITH (lists = 100);
