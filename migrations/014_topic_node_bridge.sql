-- ============================================================
-- Pocket Nori — Migration 014: Topic node bridge
--
-- Keeps the existing canonical topic storage in place while adding the
-- metadata needed to expose it as TopicNode semantics throughout runtime.
-- ============================================================

ALTER TABLE topic_clusters
    ADD COLUMN IF NOT EXISTS mention_count INT NOT NULL DEFAULT 0;

WITH mention_totals AS (
    SELECT cluster_id AS id, COUNT(*)::INT AS mention_count
    FROM topics
    WHERE cluster_id IS NOT NULL
    GROUP BY cluster_id
)
UPDATE topic_clusters tc
SET mention_count = mt.mention_count
FROM mention_totals mt
WHERE tc.id = mt.id;
