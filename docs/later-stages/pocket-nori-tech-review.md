# Pocket Nori Technical Requirements Review

**Date:** 2026-03-09  
**Scope:** Review of `pocket-nori-tech-requirements.md` against `pocket-nori-prd.md`  
**Baseline:** Lean internal MVP with early guardrails to avoid privacy/compliance rework

## Executive Summary
The technical requirements document is strong on stack pragmatism and sequencing for fast validation. The biggest gaps are in enforceable privacy contracts and implementation-level isolation guarantees, not in technology choice.

Critical issues to fix before implementation:
- `P0`: Zero-data-retention (ZDR) policy is not operationalized end-to-end and has provider inconsistencies.
- `P0`: PRD privacy principles are only partially carried into technical MUST requirements.
- `P0`: RLS is specified, but role/bypass boundaries are not, which can invalidate isolation.

## Severity-Ranked Findings

### P0-1: ZDR enforcement is under-specified and internally inconsistent
**Evidence**
- `pocket-nori-tech-requirements.md:36` requires signed ZDR agreements.
- `pocket-nori-tech-requirements.md:215` treats default provider policy as sufficient for Phase 1.
- `pocket-nori-tech-requirements.md:225` startup enforcement checks only for API key presence.
- `pocket-nori-tech-requirements.md:331` allows embedding providers not clearly covered by signed ZDR controls.
- `pocket-nori-tech-requirements.md:414` defers formal ZDR agreement to later phase.
- `pocket-nori-prd.md:67` requires no model training and vendor-level zero-data-retention agreements.

**Why this is a blocker**
The architecture currently describes ZDR as both non-negotiable and phase-dependent. This creates compliance ambiguity and opens a path to non-compliant provider use at runtime.

**Exact change needed in tech requirements**
1. Add a normative section: `LLM Provider Policy (MUST)`.
2. Require every enabled inference and embedding provider to have documented ZDR evidence before runtime enablement.
3. Replace API-key-only startup validation with policy validation of provider allowlist, model allowlist, and ZDR attestations.
4. Clarify provider ownership for each model name; remove or correct mislabeled providers.
5. Add log redaction and no-payload observability rules for model calls.

**Suggested MUST statements**
- The system MUST load model providers only from a static allowlist in configuration.
- The system MUST fail startup if any enabled provider lacks a recorded ZDR attestation.
- The system MUST apply the same ZDR gate to embedding providers as to generation providers.
- The system MUST prohibit direct SDK calls outside one centralized client module.
- The system MUST redact transcript content from application logs, traces, and error payloads.

### P0-2: PRD privacy principles are incompletely translated into technical requirements
**Evidence**
- `pocket-nori-tech-requirements.md:30` defines only two non-negotiables.
- `pocket-nori-prd.md:70` requires immediate irreversible delete/export.
- `pocket-nori-prd.md:73` prohibits admin visibility into personal intelligence.
- `pocket-nori-prd.md:76` defines encryption and least-privilege with audit logging.

**Why this is a blocker**
The technical doc omits explicit implementation contracts for deletion, admin visibility, and audit/compliance controls. Missing these now increases re-architecture risk once real users are onboarded.

**Exact change needed in tech requirements**
1. Expand non-negotiables to include all PRD Section 3 principles as technical requirements.
2. Add explicit `Delete/Export Contract` and `No Admin Visibility Contract` sections.
3. Add encryption, key management, and access-audit requirements.
4. Add a compliance sequencing table for SOC 2, GDPR, and UAE frameworks aligned to roadmap phases.

**Suggested MUST statements**
- The system MUST support user-initiated export of all user-owned data.
- The system MUST perform hard delete (no soft-delete) across primary store, vectors, cache, objects, and derived artifacts.
- The system MUST prevent admin and support roles from accessing user intelligence content.
- The system MUST encrypt all data at rest and in transit and keep auditable access logs.

### P0-3: Per-user isolation depends on RLS, but role/bypass model is missing
**Evidence**
- `pocket-nori-tech-requirements.md:104` defines RLS predicate.
- `pocket-nori-tech-requirements.md:281` claims DB-level enforcement.

**Why this is a blocker**
RLS alone is insufficient without role boundaries because privileged/service roles can bypass policies. Background workers and internal tooling can accidentally become cross-user read paths.

**Exact change needed in tech requirements**
1. Add a DB role matrix (`anon`, `authenticated`, `worker`, `migration_admin`) and allowed operations per role.
2. Require `FORCE ROW LEVEL SECURITY` on all user-owned tables.
3. Ban runtime application use of unrestricted service roles for read paths.
4. Define worker pattern: user-scoped jobs, ownership check, and restricted RPCs for system actions.
5. Add isolation tests for both API tokens and worker execution context.

**Suggested MUST statements**
- User-owned tables MUST enable and force RLS.
- Runtime API and workers MUST not execute arbitrary cross-user `SELECT` queries.
- Worker jobs MUST carry `user_id` and verify ownership before read/write.
- Isolation tests MUST run in CI for API, vector search, cache keys, and object paths.

### P1-4: PRD and tech roadmap mismatch on capture approach and phase timing
**Evidence**
- `pocket-nori-prd.md:417` states Phase 1 leverages Google Meet native transcription.
- `pocket-nori-tech-requirements.md:168` states Phase 1 uses Deepgram via manual upload.
- `pocket-nori-tech-requirements.md:385` puts productized Electron capture in Phase 3.
- `pocket-nori-tech-requirements.md:444` requires Electron spike validation in first two weeks.

**Why this matters**
The current documents mix product milestones with technical risk spikes, causing confusion on what is required for MVP delivery versus what is only feasibility validation.

**Exact change needed in tech requirements**
1. Add an explicit `Phase 0a: Technical Spikes` subsection.
2. Define Electron work in Phase 0a as feasibility-only (capture to local file), not product feature.
3. Keep Phase 3 as productized automated capture milestone.
4. Add one canonical statement on Phase 1 ingestion source and reference PRD alignment.

**Suggested MUST statements**
- Phase 0a MUST only validate high-risk assumptions and MUST NOT be treated as production scope.
- Phase 1 MUST have one declared ingestion path for MVP acceptance criteria.
- Phase 3 MUST be the first phase where end-user automated capture is considered complete.

### P1-5: Brief timing mismatch and audio-retention lifecycle ambiguity
**Evidence**
- `pocket-nori-prd.md:106` specifies pre-meeting brief delivery approximately 10-15 minutes before meeting.
- `pocket-nori-tech-requirements.md:26` and `pocket-nori-tech-requirements.md:380` specify 5 minutes.
- `pocket-nori-tech-requirements.md:126` says no audio storage.
- `pocket-nori-tech-requirements.md:366` allows audio file upload in Phase 1.

**Why this matters**
Timing inconsistency affects product behavior, user expectation, and scheduling logic. Audio ingestion without a strict retention lifecycle creates privacy ambiguity against stated principles.

**Exact change needed in tech requirements**
1. Choose one default brief trigger window and apply it across objective, roadmap, and feature sections.
2. Define fallback behavior when generation misses schedule.
3. Define transient audio lifecycle for uploads and streaming paths with hard-delete guarantees.
4. Add deletion audit events for audio ingestion artifacts.

**Suggested MUST statements**
- Default brief generation MUST target a single configured window (recommended: T-12 minutes).
- If generation misses schedule, the system MUST deliver immediately with a stale-context marker.
- Uploaded audio MUST be transient and hard-deleted after transcript persistence (or expiry timeout on failure).
- The system MUST emit auditable deletion records for transient audio artifacts.

### P2-6: Feasibility gaps to validate without blocking MVP
**Evidence**
- `pocket-nori-tech-requirements.md:177` selects Celery + Redis.
- `pocket-nori-tech-requirements.md:332` claims vector + BM25 hybrid ranking.

**Why this matters**
These are execution risks, not architectural blockers. Clarifying them now avoids implementation churn.

**Exact change needed in tech requirements**
1. Add a short broker compatibility spike for Celery with chosen Redis provider.
2. If broker reliability is weak, designate fallback broker for jobs and keep serverless Redis for cache only.
3. Replace generic "BM25" wording with exact Postgres ranking method and score fusion formula.
4. Define minimum search quality benchmark dataset and acceptance threshold.

**Suggested MUST statements**
- Queue broker choice MUST pass retry, visibility timeout, and reconnection tests before Phase 1 buildout.
- Search ranking MUST define deterministic fusion logic and evaluation metrics before launch.

## Contracts To Add

### 1) LLM Provider Policy
**Intent:** Enforce ZDR and model safety at startup and runtime.

**Required fields**
- `provider_id`
- `model_id`
- `purpose` (`generation`, `embedding`)
- `zdr_attested` (`true/false`)
- `zdr_evidence_ref` (contract/DPA reference)
- `enabled` (`true/false`)

**Runtime requirements**
- Startup fails if any enabled provider has `zdr_attested = false`.
- Only approved `(provider_id, model_id, purpose)` tuples are callable.
- All model calls route through one internal client with logging redaction.

### 2) Isolation Contract
**Intent:** Preserve per-user boundary from auth token to storage and retrieval.

**Required propagation**
- API: `user_id` from JWT is required for every request.
- DB: RLS + forced RLS on user tables.
- Vector: `user_id` predicate applied before similarity ordering.
- Cache: key namespace includes `user_id`.
- Objects: path prefix constrained to `users/{user_id}/...`.
- Workers: each job contains `user_id` and verifies ownership on execution.

**Operational requirements**
- Service roles are restricted to migration/maintenance paths.
- Isolation tests run in CI and block release on failure.

### 3) Data Lifecycle Contract
**Intent:** Make retention and deletion behavior explicit and auditable.

**Lifecycle requirements**
- Raw uploaded audio: transient only, encrypted, hard-delete after transcription or timeout.
- Streaming audio chunks: memory-only buffer unless explicitly required for recovery.
- Transcript and derived entities: retained until user hard-delete.
- User delete: irreversible cascade across DB, vectors, cache, object storage, and derived artifacts.
- Export: user can request a complete export of owned data.

**Audit requirements**
- Log export and delete operations with timestamps and actor identity.
- Do not log raw transcript/audio payload in application logs.

## Cross-Doc Consistency Matrix (P0/P1)
| Finding | PRD reference | Tech reference | Status |
|---|---|---|---|
| P0-1 ZDR consistency | `pocket-nori-prd.md:67` | `pocket-nori-tech-requirements.md:215`, `:225`, `:331`, `:414` | Fails now |
| P0-2 Privacy completeness | `pocket-nori-prd.md:70`, `:73`, `:76` | `pocket-nori-tech-requirements.md:30` | Fails now |
| P0-3 Isolation enforceability | `pocket-nori-prd.md:65`, `:177` | `pocket-nori-tech-requirements.md:104`, `:281` | Partial |
| P1-4 Phase alignment | `pocket-nori-prd.md:417` | `pocket-nori-tech-requirements.md:168`, `:385`, `:444` | Fails now |
| P1-5 Brief timing + retention | `pocket-nori-prd.md:106` | `pocket-nori-tech-requirements.md:26`, `:126`, `:366`, `:380` | Fails now |

## Implementation-Ready Edits For `pocket-nori-tech-requirements.md`
1. Update Section `Non-Negotiable Constraints` to include all PRD Section 3 principles as enforceable technical requirements.
2. Add new sections: `LLM Provider Policy`, `Isolation Contract`, `Data Lifecycle Contract`.
3. Update `LLM Integration` and `Search & Indexing` sections to remove provider ambiguity and enforce ZDR on embeddings.
4. Add `Phase 0a: Technical Spikes` and clearly separate feasibility spikes from phase deliverables.
5. Normalize pre-meeting brief trigger timing in Objective + Roadmap + Feature descriptions.
6. Add a concise `Security & Compliance Controls` subsection with encryption, least-privilege access, and audit requirements.

## Review Quality Checks
1. Cross-doc consistency check: completed for all `P0/P1` findings.
2. Constraint completeness check (PRD Section 3 -> technical MUSTs): currently failing in source tech doc; remediation defined above.
3. Contradiction check (timing/phasing/provider): currently failing in source tech doc; remediation defined above.
4. Engineer handoff check (risk + exact change): satisfied in this review document.

## Assumptions Used In This Review
- Output target is `pocket-nori-tech-review.md` in repository root.
- Review style is severity-first, actionable, and implementation-oriented.
- Product baseline remains lean internal MVP, without relaxing privacy or isolation constraints.
