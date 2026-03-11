-- ============================================================
-- Migration 005 — Align commitments.status to open/resolved
--
-- Context:
-- Earlier schema versions allowed ('open', 'done', 'cancelled') while the API
-- and product contract use ('open', 'resolved'). This migration normalizes old
-- rows and enforces the canonical enum moving forward.
-- ============================================================

ALTER TABLE commitments
    DROP CONSTRAINT IF EXISTS commitments_status_check;

UPDATE commitments
SET status = 'resolved'
WHERE status IN ('done', 'cancelled');

ALTER TABLE commitments
    ADD CONSTRAINT commitments_status_check
    CHECK (status IN ('open', 'resolved'));
