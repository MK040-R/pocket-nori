# Pocket Nori Post-MVP Hardening Plan (10-User Pilot)

**Status:** Deferred until the local intelligence stack is deployed, backfilled, and production-QA'd
**Date:** 2026-03-11
**Scope:** Move from MVP-complete build to a controlled pilot-ready product for ~10 users (internal + one external company)

---

## Why This Exists

MVP execution phases are complete (Phases 1-5). This document is the single handoff point for the next stage: hardening the product so real pilot users can use it safely and reliably while feedback is collected.

Use this file as the first reference in any new Codex session for post-MVP work.

**Current note (2026-03-25):** Do not treat this as the active execution plan yet. Pocket Nori now has the local deterministic topic spine, Entity Nodes, Knowledge Graph, and advanced resolution implemented, but operational rollout is still pending. Resume this hardening plan only after migrations `014`, `015`, `017`, and `018` are deployed, per-user rebuild/backfill is complete, and signed-in production QA passes.

**Topic pipeline prerequisites (must complete before H-06 rollout gate):**
- Annotation validation: 20–30 manually annotated transcripts, human-evaluated precision/recall
- Idempotency testing: same 5 transcripts processed 3x each; identical graph >90%
- Cost validation: actual per-meeting cost within $0.05–0.20 target

---

## Current Baseline (Starting Point)

- Product features delivered through Phase 5 (dashboard included)
- Full quality gate green:
  - `ruff check src tests`
  - `mypy src tests`
  - `pytest -q` -> 97 passed, 7 skipped
  - `frontend: npm run lint && npm run build`
- Core privacy constraints already implemented:
  - FORCE RLS
  - user JWT in workers
  - no service_role reads for user data
  - all LLM calls via `src/llm_client.py`

---

## Pilot Target

Enable a safe pilot with about 10 users across:
- company A (internal)
- company B (external design partner)

Primary goal: collect product + performance feedback without introducing avoidable legal, privacy, reliability, or operations risk.

---

## Hardening Milestones

## H-01: Pilot Privacy and Legal Guardrails

**Goal**
- Ensure external pilot usage is contractually and operationally safe.

**Work**
- Confirm provider agreements and no-training posture for external-user handling.
- Add pilot consent and privacy communication flow (product + docs).
- Define pilot terms: what data is collected, retention/deletion behavior, support boundary.

**Acceptance Criteria**
- Pilot legal/privacy checklist exists and is approved.
- External pilot users receive explicit privacy/usage terms.
- Data handling policy is documented in-repo and consistent with implemented architecture.

---

## H-02: Production Observability and Alerting

**Goal**
- Detect and respond to failures quickly in API, workers, and scheduled briefs.

**Work**
- Add centralized error reporting and structured operational logs.
- Add alert rules for:
  - API 5xx spike
  - worker failures / queue backlog growth
  - brief generation failures or late generation
- Add basic operational dashboard (error rate, queue depth, job success rate, latency).

**Acceptance Criteria**
- Triggered test errors appear in monitoring.
- Alerts route to owner channel and are verified with test incidents.
- Runbook exists for top incident classes.

---

## H-03: Reliability and Recovery Controls

**Goal**
- Ensure recoverability and safe operations for pilot data.

**Work**
- Configure and verify backup policy for database/storage.
- Perform one restore drill and document exact recovery steps + timing.
- Validate idempotency and retry safety for ingestion/extraction/brief scheduling paths.
- Validate idempotency and determinism of the topic intelligence pipeline (>90% reproducibility target).

**Acceptance Criteria**
- Backup + restore drill evidence documented.
- Recovery runbook committed.
- Critical background jobs are proven retry-safe.

---

## H-04: Security Operations Baseline

**Goal**
- Reduce practical security risk before external-user pilot.

**Work**
- Rotate and re-issue all critical secrets/tokens for pilot start.
- Validate strict environment separation (dev vs production).
- Review OAuth app configuration (redirects/scopes/consent screen).
- Validate least-privilege access for infra and operations accounts.

**Acceptance Criteria**
- Security checklist completed and signed off.
- Secret rotation date and owner recorded.
- No high-severity config gaps remain open.

---

## H-05: Pilot UX and Support Readiness

**Goal**
- Ensure first pilot users can onboard, use, and get support without manual chaos.

**Work**
- Define pilot onboarding flow and support escalation path.
- Add user lifecycle operational controls:
  - disable user
  - export user data
  - hard-delete user data
- Create quick support playbook for common issues (auth/import/brief/search).

**Acceptance Criteria**
- Support playbook exists and is test-run once.
- User lifecycle actions are executable and documented.
- Pilot onboarding path validated end-to-end with at least one dry run.

---

## H-06: Pilot Readiness Gate and Rollout

**Goal**
- Make a deliberate go/no-go decision with clear evidence.

**Work**
- Run final hardening QA gate.
- Define pilot success metrics:
  - import success rate
  - brief generation success/on-time rate
  - search latency and error rate
  - topic extraction precision (evaluated against annotated samples)
  - pipeline cost per meeting
  - weekly active usage and qualitative feedback
- Run staged rollout (small batch first, then full 10 users).

**Acceptance Criteria**
- Go/no-go checklist complete.
- Metrics dashboard configured for pilot period.
- Staged rollout plan documented and owned.

---

## Execution Rules for Codex Sessions

For every hardening milestone:

1. Implement milestone scope end-to-end.
2. Run full quality gate:
   - `ruff check src tests`
   - `mypy src tests`
   - `pytest -q`
   - `frontend: npm run lint && npm run build`
3. Update docs in same session:
   - `PROGRESS.md`
   - `.planning/ROADMAP.md`
   - `.planning/STATE.md`
   - `.planning/PROJECT.md`
   - `AGENTS.md` / `CLAUDE.md` if stage text changes

Do not close a milestone without both validation evidence and doc sync.

---

## New Chat Kickoff Prompt (Copy/Paste)

```text
Continue Pocket Nori in /Users/Murali/Desktop/Work/claude-code-1/Pocket Nori.

Before coding, read in this order:
1) DOCS.md
2) AGENTS.md
3) .planning/REQUIREMENTS.md
4) .planning/ROADMAP.md
5) .planning/STATE.md
6) .planning/PROJECT.md
7) pocket-nori-tech-requirements-mvp.md
8) POST_MVP_HARDENING_PLAN.md
9) Later stages/pocket-nori-tech-requirements-full.md

Then execute hardening milestone H-01 from POST_MVP_HARDENING_PLAN.md.
After the milestone:
- run full QA gate
- update all planning/progress docs
- summarize exact evidence and next milestone
```

---

## Definition of Done (Post-MVP Pilot Ready)

Pocket Nori is pilot-ready when:
- H-01 to H-06 are complete
- quality gate remains green
- legal/privacy and operational controls are documented and tested
- pilot rollout decision is explicit and evidence-backed
