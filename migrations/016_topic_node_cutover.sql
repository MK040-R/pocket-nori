-- ============================================================
-- Pocket Nori — Migration 016: Topic node cutover
--
-- Apply only after runtime code is fully bridge-backed and no route or worker
-- depends on the legacy cluster terminology directly.
-- ============================================================

-- ------------------------------------------------------------
-- Canonical topic table rename
-- ------------------------------------------------------------
ALTER TABLE topic_clusters RENAME TO topic_nodes;

ALTER TABLE topic_nodes RENAME COLUMN canonical_label TO label;
ALTER TABLE topic_nodes RENAME COLUMN canonical_summary TO summary;

-- ------------------------------------------------------------
-- Mention + arc foreign-key rename
-- ------------------------------------------------------------
ALTER TABLE topics RENAME COLUMN cluster_id TO topic_node_id;
ALTER TABLE topic_arcs RENAME COLUMN cluster_id TO topic_node_id;

-- ------------------------------------------------------------
-- Index rename
-- ------------------------------------------------------------
ALTER INDEX IF EXISTS topic_clusters_user_id_idx
    RENAME TO topic_nodes_user_id_idx;

ALTER INDEX IF EXISTS topic_clusters_user_label_idx
    RENAME TO topic_nodes_user_label_idx;

ALTER INDEX IF EXISTS topic_clusters_user_last_mentioned_idx
    RENAME TO topic_nodes_user_last_mentioned_idx;

ALTER INDEX IF EXISTS topic_clusters_embedding_idx
    RENAME TO topic_nodes_embedding_idx;

ALTER INDEX IF EXISTS topics_user_cluster_id_idx
    RENAME TO topics_user_topic_node_id_idx;

ALTER INDEX IF EXISTS topic_arcs_user_cluster_id_idx
    RENAME TO topic_arcs_user_topic_node_id_idx;
