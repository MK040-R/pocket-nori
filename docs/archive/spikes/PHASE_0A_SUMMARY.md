# Phase 0a — Technical Spikes: QA Summary

**QA Date:** 2026-03-09
**Reviewer:** QA Agent (Claude Sonnet 4.6)
**Scope:** All 5 spike directories reviewed — every source file, test, SQL migration, config, and FINDINGS.md read in full.

---

## Go/No-Go per Spike

| Spike | Decision | Confidence | Key Finding | Blocker? |
|-------|----------|------------|-------------|----------|
| Spike 1: Electron Audio Capture | CONDITIONAL GO | High | Electron + desktopCapturer captures system audio on macOS 13+; pipeline is fully implemented and syntactically correct; live Meet test (FAR-45) is the only remaining gate | No (human test only) |
| Spike 2: Deepgram Accuracy Validation | CONDITIONAL GO (pending data) | Low | Code scaffolding is complete and correct; FINDINGS.md Section 6 decision was blank — reopened; actual WER/diarization numbers cannot exist until human provides recordings + API key | Yes — FAR-6 blocked on recordings |
| Spike 3: LLM Extraction Quality | CONDITIONAL GO | Medium | Pydantic v2 models, prompts, runner, and evaluator are complete and well-formed; pipeline was not executed (no API key); synthetic transcripts are present; FAR-53 real transcripts are still needed | No (API key + transcripts needed) |
| Spike 4: Supabase RLS Isolation | CONDITIONAL GO | High | SQL migration and RLS policy are correct (FORCE RLS present); test suite logic is sound; found a supabase-py v2 API bug in `set_session` — fixed; tests cannot run until FAR-60 Supabase project is provisioned | Yes — FAR-60 blocked on project creation |
| Spike 5: Celery + Redis Broker | CONDITIONAL GO | High | Configuration is well-reasoned; found a hard import-time KeyError that broke all unit tests — fixed; unit tests now runnable without Redis; integration tests blocked on FAR-67 Upstash credentials | Partial — unit tests now unblocked; integration still needs FAR-67 |

---

## QA Findings (Issues Found & Fixed)

### Issue 1 — FAR-49 / Spike 2: Blank go/no-go decision in FINDINGS.md
**File:** `spikes/spike2_deepgram/FINDINGS.md`, Section 6
**Problem:** The issue was marked Done but the decision section contained only unchecked `[ ]` boxes and `_pending_` placeholders. This is not a valid spike conclusion — the "Done" state was a false positive.
**Fix:** Updated Section 6 with an honest "Conditional Go (pending data)" interim state, a clear explanation of why the decision is pending, and numbered next steps for the human who will run the evaluation. Issue reopened to In Progress.

### Issue 2 — FAR-68 / Spike 5: `celeryconfig.py` raises `KeyError` at import time
**File:** `spikes/spike5_celery_redis/celeryconfig.py`, line 13
**Problem:** `REDIS_URL = os.environ["UPSTASH_REDIS_URL"]` executes at module import time. Since `conftest.py` imports `from tasks import app` at the top level, and `tasks.py` imports `celeryconfig`, every pytest collection run would immediately raise `KeyError` if `UPSTASH_REDIS_URL` was absent — including the unit tests that were explicitly designed to run without Redis (`task_always_eager=True`). The claim that "unit tests run immediately without credentials" was false.
**Fix:** Changed to `os.environ.get("UPSTASH_REDIS_URL", "")` with a deferred `EnvironmentError` that only triggers when Celery is started as a worker/beat process (detected via `sys.argv`). Unit tests now import and collect correctly. Issue reopened to In Progress.

### Issue 3 — FAR-62 / Spike 4: `set_session` called with empty `refresh_token`
**File:** `spikes/spike4_supabase_rls/test_rls_isolation.py`, `_user_client()` function
**Problem:** `client.auth.set_session(access_token, "")` — supabase-py v2's `GoTrueClient.set_session` raises `ValueError` when `refresh_token` is an empty string. The `setup_test_users.py` already persists `refresh_token` in `test_credentials.json`, so the fix was straightforward.
**Fix:** `_user_client()` signature changed to accept both `access_token` and `refresh_token`; both user fixtures now pass both tokens from `credentials`. Issue reopened to In Progress.

### Issue 4 — Spike 4: `pytest-asyncio` listed as dependency with no async tests
**File:** `spikes/spike4_supabase_rls/requirements.txt`
**Problem:** `pytest-asyncio` was listed as a dependency. There are no `async def` test functions in this spike — the package was unused and would add install overhead for no benefit.
**Fix:** Removed from requirements.txt. Also pinned `python-dotenv>=1.0.0` and `pytest>=8.0.0`.

### Issue 5 — Spikes 2, 3: `python-dotenv` unpinned in requirements.txt
**Files:** `spikes/spike2_deepgram/requirements.txt`, `spikes/spike3_llm_extraction/requirements.txt`
**Problem:** `python-dotenv` had no version constraint, violating the project's pin-versions rule.
**Fix:** Added `>=1.0.0` floor pin to both files.

---

## Issues Requiring Human Action

These are architectural blockers that cannot be resolved by code changes alone:

### 1. FAR-45 — Live Google Meet audio test (Spike 1)
A human must install the Electron app (`npm install && npm start`), grant Screen Recording permission, join a real Google Meet session, capture 10–30 seconds of audio, and verify the output WAV is audible. Until this test passes, the Electron approach is conditional. If Meet audio is silent, the fallback is a Chrome extension using `chrome.tabCapture`.

### 2. FAR-52/FAR-6 — Deepgram real recordings (Spike 2)
A human must provide a Deepgram API key (add to `.env`) and place at least 3 real multi-speaker meeting recordings in `spikes/spike2_deepgram/recordings/`. Run `test_deepgram.py` then `evaluate_accuracy.py` and `evaluate_diarization.py`. Fill in the results table in `FINDINGS.md` Section 3 and record the final Go/No-Go decision in Section 6.

### 3. FAR-53 — Real meeting transcripts for LLM extraction (Spike 3)
A human must provide 5 real meeting transcripts as `.txt` files in `spikes/spike3_llm_extraction/transcripts/` (named `meeting_01.txt` through `meeting_05.txt`) and an `ANTHROPIC_API_KEY` in `.env`. Run `python runner.py` then `python evaluate.py` to generate `evaluation_report.md`.

### 4. FAR-60 — Supabase project provisioning (Spike 4)
A human must create a Supabase project at supabase.com, run migration `migrations/001_rls_test_setup.sql` in the SQL editor, and populate `.env` with `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`. Then run `python setup_test_users.py` and `pytest test_rls_isolation.py -v`. All 5 tests passing = GO.

### 5. FAR-67 — Upstash Redis credentials (Spike 5)
A human must create an Upstash account, provision a Redis database, and add `UPSTASH_REDIS_URL=rediss://...` to `.env`. Then start a Celery worker (`celery -A tasks worker --loglevel=info`) and run `pytest tests/ -v --timeout=30 -m integration` to validate dispatch, retry, timeout, and worker-recovery behaviour.

---

## Recommended Next Steps for Phase 0

Based on spike results, recommended build order for Phase 0 foundation:

1. **Unblock FAR-67 first (Upstash credentials)** — Spike 5 unit tests now run locally without Redis. Provisioning Upstash (free tier, ~5 minutes) unblocks all integration tests and validates the broker before any other async work is built on top of it.

2. **Unblock FAR-60 (Supabase provisioning)** — The RLS spike code is correct and the fixed test suite is ready to execute. Provisioning the Supabase project validates the most critical architectural constraint (per-user isolation) before any data model work begins.

3. **Run Spike 3 with API key** — `runner.py` and `evaluate.py` need only an `ANTHROPIC_API_KEY` and the synthetic transcripts (already present) to produce the first real extraction quality numbers. This is the lowest-effort of the five human gates.

4. **FAR-45 live audio test and FAR-52 recordings** — These require more effort (live Meet session, real recordings) but are straightforward once the infra spikes (Supabase, Celery) are validated.

5. **Phase 0 foundation build order (after all spikes GO):**
   - Supabase schema + migrations (conversations, topics, commitments, entities tables with RLS)
   - FastAPI skeleton with Google OAuth
   - Celery + Redis worker wired to the LLM extraction pipeline
   - Deepgram integration in the transcript ingestion task

---

## Spike Code Quality Summary

| Spike | No Hardcoded Secrets | Error Handling | Imports Valid | Tests Have Real Logic |
|-------|---------------------|----------------|---------------|----------------------|
| Spike 1 (Electron) | Yes | Yes | Yes (wavefile listed but unused — no issue) | N/A (no test files) |
| Spike 2 (Deepgram) | Yes | Yes | Yes | Yes (not stub — real WER, diarization logic) |
| Spike 3 (LLM) | Yes | Yes | Yes | Yes (heuristic evaluator is substantive) |
| Spike 4 (RLS) | Yes | Yes | Yes | Yes (5 real test cases with meaningful assertions) |
| Spike 5 (Celery) | Yes | Yes (after fix) | Yes | Yes (unit + integration tests complete) |
