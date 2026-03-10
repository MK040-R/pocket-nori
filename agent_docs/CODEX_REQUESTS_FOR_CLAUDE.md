# Codex -> Claude: Backend Requests (Post Wave 3 QA)

Date: 2026-03-10

Scope: These are backend-only requests discovered during frontend integration QA. Frontend has local compatibility shims in place, but these fixes should land server-side to restore a clean contract.

## 1) Block cross-user job status visibility (High)

Why:
- `/onboarding/import/status` and `/onboarding/import/status/{job_id}` read Celery job state directly by job ID and do not verify that the job belongs to `current_user`.
- Any authenticated user who learns another job ID can potentially read status/result metadata.

Evidence:
- [src/api/routes/onboarding.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/onboarding.py:280)
- [src/api/routes/onboarding.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/onboarding.py:350)

Request:
1. Persist ownership at enqueue time (`job_id -> user_id`, and optionally `file_id`) in Redis/DB.
2. Enforce ownership check in both status endpoints before returning any job data.
3. Return `404` (preferred) or `403` on mismatch.
4. Add tests for:
   - owner can read own job
   - different user cannot read job
   - aggregate endpoint rejects/masks foreign job IDs

## 2) Align `/topics` and `/topics/{id}` with CODEX_BRIEF contract (Medium)

Why:
- `CODEX_BRIEF.md` specifies:
  - `GET /topics -> [{ id, label, conversation_count, latest_date }]`
  - `GET /topics/{id} -> { id, label, summary, conversations: [...], key_quotes: [...] }`
- Current backend returns per-conversation rows for `/topics` and a single-row detail for `/topics/{id}`.

Evidence:
- Contract in [CODEX_BRIEF.md](/Users/Murali/Desktop/Work/claude-code-1/Farz/agent_docs/CODEX_BRIEF.md:275)
- Current response model in [src/api/routes/topics.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/topics.py:50)
- Current detail shape in [src/api/routes/topics.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/topics.py:113)

Request:
1. Make `/topics` return summary rows (`conversation_count`, `latest_date`) grouped at topic level.
2. Make `/topics/{id}` return aggregated detail with `conversations[]`.
3. Keep IDs stable and deterministic for topic-level records.
4. Add route tests for summary aggregation and detail aggregation.

## 3) Accept `status` as commitments filter (Medium)

Why:
- Contract says `/commitments` is filterable by status.
- Current backend only accepts `filter_status`; this creates avoidable client coupling.

Evidence:
- Current parameter in [src/api/routes/commitments.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/commitments.py:52)

Request:
1. Support `status` as canonical query param (`open|resolved`).
2. Keep `filter_status` as backward-compatible alias for now.
3. Prefer one consistent name in OpenAPI + CODEX_BRIEF after implementation.

## 4) Aggregate import status payload consistency (Low)

Why:
- `CODEX_BRIEF.md` aggregate status example includes `jobs: [{ job_id, file_id, status, detail }]`.
- Current backend returns `job_id/status/detail/result` with no `file_id`.

Evidence:
- Brief example in [CODEX_BRIEF.md](/Users/Murali/Desktop/Work/claude-code-1/Farz/agent_docs/CODEX_BRIEF.md:144)
- Current model in [src/api/routes/onboarding.py](/Users/Murali/Desktop/Work/claude-code-1/Farz/src/api/routes/onboarding.py:55)

Request:
1. Either add `file_id` into aggregate `jobs[]` output,
2. Or update brief/OpenAPI to make `file_id` explicitly optional/absent.

## 5) Contract test coverage for Wave 3 routes (Low)

Why:
- Core tests pass, but endpoint-contract regressions can slip in if route-level response shapes are not pinned.

Request:
1. Add API tests for:
   - `/topics` and `/topics/{id}` response shapes
   - `/commitments` filtering by canonical param
   - onboarding status ownership checks
2. Ensure OpenAPI examples match actual payloads.
