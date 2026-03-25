-- ============================================================
-- Pocket Nori — Migration 015: Provenance link metadata
--
-- Adds deterministic link metadata so topic, commitment, and entity citations
-- can be explained and backfilled without fabricating evidence.
-- ============================================================

ALTER TABLE topic_segment_links
    ADD COLUMN IF NOT EXISTS match_score REAL,
    ADD COLUMN IF NOT EXISTS match_origin TEXT NOT NULL DEFAULT 'legacy_backfill'
    CHECK (match_origin IN ('llm_quote', 'exact_substring', 'token_overlap', 'legacy_backfill'));

ALTER TABLE commitment_segment_links
    ADD COLUMN IF NOT EXISTS match_score REAL,
    ADD COLUMN IF NOT EXISTS match_origin TEXT NOT NULL DEFAULT 'legacy_backfill'
    CHECK (match_origin IN ('llm_quote', 'exact_substring', 'token_overlap', 'legacy_backfill'));

ALTER TABLE entity_segment_links
    ADD COLUMN IF NOT EXISTS match_score REAL,
    ADD COLUMN IF NOT EXISTS match_origin TEXT NOT NULL DEFAULT 'legacy_backfill'
    CHECK (match_origin IN ('llm_quote', 'exact_substring', 'token_overlap', 'legacy_backfill'));
