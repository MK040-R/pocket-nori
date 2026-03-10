# Farz Technical Requirements Review V2

**Date:** 2026-03-09  
**Input Docs:** `farz-prd.md`, `farz-tech-requirements.md`  
**Goal:** One final, prioritized review list balanced across Intelligence Quality, Technology Choices, Execution/Roadmap, and Security/Privacy.

## Consolidated Prioritized Findings (Single Source of Truth)

### 1) ZDR policy is not enforceable end-to-end
- **Priority:** `P0`
- **Domain:** `Security`
- **Finding:** ZDR is declared as non-negotiable, but runtime enforcement is API-key presence, not provider-policy validation; embedding provider policy is also inconsistent.
- **Why it matters:** This creates a direct compliance escape hatch where non-attested providers can be used while claiming ZDR compliance.
- **Evidence:**
  - `PRD:` `farz-prd.md:67`, `farz-prd.md:68`, `farz-prd.md:421`
  - `Tech:` `farz-tech-requirements.md:36`, `farz-tech-requirements.md:225`, `farz-tech-requirements.md:231`, `farz-tech-requirements.md:331`
- **Exact recommendation:** Add a mandatory allowlist of `(provider, model, purpose)` with `zdr_attested=true`; fail startup if any enabled inference or embedding model lacks attestation; route all SDK calls via one validated client.
- **Priority rationale:** Violates a stated non-negotiable product constraint.

### 2) Per-user isolation is incomplete without role-boundary controls
- **Priority:** `P0`
- **Domain:** `Security`
- **Finding:** RLS is specified, but role/bypass boundaries and forced-RLS requirements are not documented.
- **Why it matters:** Privileged/service-role execution can bypass intended isolation and create cross-user exposure paths.
- **Evidence:**
  - `PRD:` `farz-prd.md:65`, `farz-prd.md:177`, `farz-prd.md:425`
  - `Tech:` `farz-tech-requirements.md:104`, `farz-tech-requirements.md:281`, `farz-tech-requirements.md:286`
- **Exact recommendation:** Define a DB role matrix (`authenticated`, `worker`, `migration_admin`), require `FORCE ROW LEVEL SECURITY` on user-owned tables, ban unrestricted runtime reads with admin/service roles, and add CI isolation tests for API + worker flows.
- **Priority rationale:** Isolation is also a non-negotiable boundary in both PRD and tech doc.

### 3) Phase-1 ingestion strategy conflicts with PRD architecture
- **Priority:** `P0`
- **Domain:** `Execution`
- **Finding:** PRD Phase 1 assumes Google Meet transcription as input; tech requirements define manual upload + Deepgram for Phase 1.
- **Why it matters:** Team will build to different acceptance criteria and timeline assumptions.
- **Evidence:**
  - `PRD:` `farz-prd.md:317`, `farz-prd.md:417`
  - `Tech:` `farz-tech-requirements.md:168`, `farz-tech-requirements.md:366`, `farz-tech-requirements.md:367`
- **Exact recommendation:** Choose one canonical Phase-1 ingestion path and mark the other as explicit spike/alternative. If manual upload remains Phase 1, update PRD Phase 1 input statement to match.
- **Priority rationale:** Critical architecture and milestone contradiction.

### 4) Intelligence quality contract is too narrow for launch confidence
- **Priority:** `P1`
- **Domain:** `Intelligence`
- **Finding:** Only commitment-capture quality is quantified; Topic, Connection, and Brief quality gates are missing.
- **Why it matters:** Product value depends on all intelligence surfaces, not only commitments.
- **Evidence:**
  - `PRD:` `farz-prd.md:100`, `farz-prd.md:399`
  - `Tech:` `farz-tech-requirements.md:373`, `farz-tech-requirements.md:408`
- **Exact recommendation:** Define an evaluation contract covering Topic, Connection, Commitment, and Brief with explicit metrics and release gates (see contract section below).
- **Priority rationale:** High risk of shipping intelligence that appears complete but is not trustworthy.

### 5) Traceability requirement is not encoded in output schema
- **Priority:** `P1`
- **Domain:** `Intelligence`
- **Finding:** PRD requires every generated claim to be traceable to source meeting and timestamp; tech pipeline does not define citation payload fields.
- **Why it matters:** Without first-class citations, users cannot verify outputs and hallucination handling is weak.
- **Evidence:**
  - `PRD:` `farz-prd.md:92`, `farz-prd.md:135`, `farz-prd.md:175`
  - `Tech:` `farz-tech-requirements.md:239`, `farz-tech-requirements.md:242`, `farz-tech-requirements.md:378`
- **Exact recommendation:** Require citation fields (`conversation_id`, `start_ts`, `end_ts`, `speaker`, `evidence_text`) on Topic Arc, Connection, Commitment, and Brief claims.
- **Priority rationale:** Directly impacts user trust and debuggability of intelligence outputs.

### 6) Retrieval design is under-specified for the PRD query behavior
- **Priority:** `P1`
- **Domain:** `Intelligence`
- **Finding:** Hybrid retrieval is described conceptually, but chunking, fusion formula, and reranking policy are unspecified.
- **Why it matters:** Query behavior for synonym/context search can vary dramatically without deterministic retrieval design.
- **Evidence:**
  - `PRD:` `farz-prd.md:92`, `farz-prd.md:429`
  - `Tech:` `farz-tech-requirements.md:329`, `farz-tech-requirements.md:332`, `farz-tech-requirements.md:337`
- **Exact recommendation:** Define chunk unit, fusion method, top-k limits, reranker policy, and response citation assembly in a retrieval contract.
- **Priority rationale:** Core intelligence behavior depends on retrieval quality more than model choice.

### 7) Topic/connection merge logic lacks confidence controls and correction loop
- **Priority:** `P1`
- **Domain:** `Intelligence`
- **Finding:** Current merge flow says “find similar + merge duplicates” without false-positive controls or user correction feedback.
- **Why it matters:** Over-merging or bad links will degrade Topic Arc and dashboard quality over time.
- **Evidence:**
  - `PRD:` `farz-prd.md:100`, `farz-prd.md:132`, `farz-prd.md:137`
  - `Tech:` `farz-tech-requirements.md:341`, `farz-tech-requirements.md:345`
- **Exact recommendation:** Add dual-threshold merge policy (`auto-merge`, `needs-review`), confidence storage on all links, and a simple user correction mechanism feeding the clustering job.
- **Priority rationale:** High downstream quality risk with compounding error.

### 8) Celery + serverless Redis suitability is not validated for workload guarantees
- **Priority:** `P1`
- **Domain:** `Tech Stack`
- **Finding:** Queue stack is chosen, but broker behavior for retries/visibility/reconnection is not validated against brief-generation timing needs.
- **Why it matters:** Reliability gaps here will surface as missing extractions and late briefs.
- **Evidence:**
  - `PRD:` `farz-prd.md:100`, `farz-prd.md:106`
  - `Tech:` `farz-tech-requirements.md:177`, `farz-tech-requirements.md:299`, `farz-tech-requirements.md:301`
- **Exact recommendation:** Run a broker qualification spike (delayed jobs, retry storms, worker restarts); if limits are hit, keep Upstash for cache and move task broker to a dedicated Redis/RabbitMQ tier.
- **Priority rationale:** High operational risk, but not a product-definition blocker.

### 9) Data model granularity may be insufficient for “who said what” and timestamp evidence
- **Priority:** `P1`
- **Domain:** `Tech Stack`
- **Finding:** Model lists core entities but does not explicitly include speaker-turn/utterance-level storage required for reliable attribution and claim citations.
- **Why it matters:** Commitment assignment and evidence linking require stable utterance-level references.
- **Evidence:**
  - `PRD:` `farz-prd.md:92`, `farz-prd.md:141`
  - `Tech:` `farz-tech-requirements.md:102`, `farz-tech-requirements.md:170`, `farz-tech-requirements.md:239`
- **Exact recommendation:** Add `TranscriptSegment` (or equivalent) to technical data model with fields: `conversation_id`, `speaker_id`, `start_ts`, `end_ts`, `text`, `segment_confidence`; link derived entities to segment IDs.
- **Priority rationale:** Needed for product-grade attribution and traceability.

### 10) Brief trigger window is inconsistent across docs
- **Priority:** `P1`
- **Domain:** `Execution`
- **Finding:** PRD states 10-15 minutes pre-meeting; tech doc states 5 minutes.
- **Why it matters:** This changes scheduler behavior, cache warm-up strategy, and user expectation.
- **Evidence:**
  - `PRD:` `farz-prd.md:106`
  - `Tech:` `farz-tech-requirements.md:26`, `farz-tech-requirements.md:380`
- **Exact recommendation:** Standardize to one default (recommended: `T-12m`) and add fallback behavior (`late brief` label if generated after trigger).
- **Priority rationale:** High UX and reliability impact; easy to fix early.

### 11) Data lifecycle policy is ambiguous for uploaded audio and user deletion/export
- **Priority:** `P1`
- **Domain:** `Security`
- **Finding:** “No audio storage” is stated, but Phase-1 upload flow includes audio ingestion without explicit transient retention/deletion/export behavior.
- **Why it matters:** Privacy claims require exact lifecycle semantics, not intent language.
- **Evidence:**
  - `PRD:` `farz-prd.md:70`, `farz-prd.md:71`, `farz-prd.md:73`
  - `Tech:` `farz-tech-requirements.md:126`, `farz-tech-requirements.md:366`, `farz-tech-requirements.md:30`
- **Exact recommendation:** Define transient-audio lifecycle (ingest -> transcribe -> hard-delete), irreversible user-delete cascade across all stores, and complete user-export contract.
- **Priority rationale:** High compliance/trust risk but can be addressed with clear policy + implementation gates.

### 12) Model routing and budget controls are under-defined
- **Priority:** `P1`
- **Domain:** `Tech Stack`
- **Finding:** Current model assignment is static and cost range is broad; no explicit routing policy for complexity, latency, or budget.
- **Why it matters:** Cost volatility and latency spikes can appear early during internal testing.
- **Evidence:**
  - `PRD:` `farz-prd.md:429`
  - `Tech:` `farz-tech-requirements.md:222`, `farz-tech-requirements.md:223`, `farz-tech-requirements.md:303`
- **Exact recommendation:** Add model-routing contract by task complexity and token budget with deterministic fallback chain and monthly spend alert thresholds.
- **Priority rationale:** Strong quality/cost lever; not a foundational blocker.

### 13) Scale-trigger criteria for adding Pinecone/Neo4j/Kafka are vague
- **Priority:** `P2`
- **Domain:** `Tech Stack`
- **Finding:** Upgrade paths are listed as “when needed” without measurable trigger thresholds.
- **Why it matters:** Teams tend to either migrate too early or too late without objective triggers.
- **Evidence:**
  - `PRD:` `farz-prd.md:425`
  - `Tech:` `farz-tech-requirements.md:319`, `farz-tech-requirements.md:320`, `farz-tech-requirements.md:321`
- **Exact recommendation:** Add explicit trigger thresholds (p95 query latency, index size, write throughput, link-traversal depth) for each migration decision.
- **Priority rationale:** Optimization concern, not immediate blocker.

### 14) Cold-start and multilingual constraints are not translated into build milestones
- **Priority:** `P2`
- **Domain:** `Execution`
- **Finding:** PRD identifies both as open product risks, but tech roadmap does not include explicit mitigation milestones.
- **Why it matters:** Early user experience quality may underperform even if core pipeline works.
- **Evidence:**
  - `PRD:` `farz-prd.md:401`, `farz-prd.md:403`
  - `Tech:` `farz-tech-requirements.md:363`, `farz-tech-requirements.md:375`
- **Exact recommendation:** Add Phase-1/2 tasks for cold-start utility mode and language-scope decision with acceptance criteria.
- **Priority rationale:** Important for adoption quality, but can follow core architecture alignment.

## Public Interfaces / Contracts

### Intelligence Evaluation Contract
- **Required metrics:**
  - Commitment extraction: precision, recall, F1.
  - Topic quality: duplicate rate and human coherence score.
  - Connection quality: precision at top-k surfaced links.
  - Brief quality: factual claim accuracy and citation coverage.
- **Recommended v1 dataset size:** 30 labeled transcripts (train/tune) + 10 holdout transcripts (release gate).
- **Recommended v1 thresholds:**
  - Commitment precision `>= 0.85`, recall `>= 0.75`.
  - Connection precision@5 `>= 0.80`.
  - Brief citation coverage `>= 0.95` of factual claims.
  - Topic duplicate rate `<= 0.15` on holdout.
- **Release gate:** No release to next roadmap phase unless all thresholds pass on holdout.

### Retrieval Contract
- **Chunk unit:** Speaker-turn-first segments, hard cap `220` tokens, overlap `40` tokens.
- **Candidate generation:** top `50` vector hits + top `50` lexical hits per query, user-scoped before ranking.
- **Hybrid ranking formula:** `0.65 * normalized_vector_score + 0.35 * normalized_lexical_score`.
- **Reranking policy:** Re-rank top `20` candidates with one deterministic reranker step; return top `8` evidence chunks.
- **Citation payload (required):** `conversation_id`, `start_ts`, `end_ts`, `speaker_id`, `snippet`.

### Model Routing Contract
- **Task mapping:**
  - Extraction/classification jobs -> default fast model.
  - Brief generation -> default fast model; escalate to high-reasoning model only when context length or ambiguity threshold is exceeded.
- **Fallback behavior:** strict ordered fallback list by provider/model; preserve schema contract across fallbacks.
- **Budget guardrails:**
  - Max tokens per extraction job.
  - Max tokens per brief.
  - Daily and monthly spend alerts with automatic downgrade to lower-cost model tier when thresholds are exceeded.

## 30/60/90-Day Execution Order

### Days 0-30 (Blockers)
1. Resolve all `P0` contradictions (ZDR enforcement, isolation role model, Phase-1 ingestion source).
2. Freeze canonical Phase-1 architecture statement across PRD + tech requirements.
3. Implement baseline policy checks (provider allowlist + forced RLS controls).

### Days 31-60 (Quality Foundation)
1. Implement the three contracts: Intelligence Evaluation, Retrieval, Model Routing.
2. Add citation payload requirements and utterance-level segment linkage.
3. Run queue broker qualification tests and confirm broker decision.
4. Standardize brief trigger timing and late-delivery behavior.

### Days 61-90 (Stabilization and Scale Readiness)
1. Add merge-threshold + user-correction loop for Topic/Connection quality.
2. Finalize data lifecycle semantics for transient audio + delete/export.
3. Define objective scale triggers for Pinecone/Neo4j/Kafka migration.
4. Add roadmap milestones for cold-start and multilingual strategy.

## V2 Review Quality Checks
1. **Coverage test:** Pass. At least one `P0/P1` finding exists for each domain (`Intelligence`, `Tech Stack`, `Execution`, `Security`).
2. **Evidence test:** Pass. Every `P0/P1` finding cites both PRD and tech requirement lines.
3. **Priority test:** Pass. `P0` is used only for explicit blocker contradictions/non-negotiables.
4. **Actionability test:** Pass. Each finding has one exact recommendation.
5. **Finality test:** Pass. One consolidated prioritized list only.

## Assumptions Used
- File name `farz-tech-review-v2.md` is the intended “v2” deliverable.
- Prioritization is execution-first (blockers first), then quality/system design, then optimizations.
- Existing files remain unchanged: `farz-tech-review.md`, `farz-tech-requirements.md`, `farz-prd.md`.
