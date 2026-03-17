# Spike 5 — Celery + Redis Broker: Findings

**Spike:** FAR-9
**Date:** 2026-03-09
**Status:** Code complete. Integration tests pending Upstash credentials (FAR-67).

---

## Configuration Summary

### Stack

| Component | Version / Choice |
|---|---|
| Celery | `>=5.3.0` (celery[redis] extra) |
| Redis transport | `redis>=5.0.0` (Celery Redis transport, not celery-redis) |
| Broker | Upstash Redis (serverless, TLS, `rediss://`) |
| Result backend | Same Upstash Redis URL |
| Serialisation | JSON (never pickle) |
| Python | 3.13 |

### Configuration Highlights

| Setting | Value | Rationale |
|---|---|---|
| `task_acks_late` | `True` | Ack after completion; task returns to queue on worker crash |
| `task_reject_on_worker_lost` | `True` | Explicit reject on SIGTERM so broker redelivers |
| `task_acks_on_failure_or_timeout` | `True` | Consistent ack behaviour on error paths |
| `visibility_timeout` | `3600 s` | Must exceed longest task duration; prevents premature redelivery |
| `worker_prefetch_multiplier` | `1` | One task per worker slot; reduces duplicate work on crash |
| `task_max_retries` | `3` | Default ceiling; individual tasks can override |
| `result_expires` | `86400 s` | Results cleared after 24 h to limit Redis memory usage |
| `task_serializer` | `json` | Safe across Python versions; auditable in Redis |

---

## Files Created

```
spikes/spike5_celery_redis/
├── .env.example               # Credential schema
├── .gitignore                 # Excludes .env, __pycache__, celerybeat-schedule
├── requirements.txt           # Pinned dependencies
├── celeryconfig.py            # All Celery settings (FAR-68)
├── tasks.py                   # process_transcript, failing_task, slow_task (FAR-69)
├── decision_memo.md           # Upstash vs Render comparison (FAR-74, FAR-75)
├── FINDINGS.md                # This file
└── tests/
    ├── __init__.py
    ├── conftest.py             # Fixtures: eager_app (unit), require_redis (integration)
    ├── test_tasks_unit.py      # Unit tests — no Redis required (FAR-70)
    ├── test_dispatch.py        # Integration: dispatch + result retrieval (FAR-70)
    ├── test_retry.py           # Integration: retry behaviour (FAR-71)
    ├── test_timeout.py         # Integration: visibility timeout (FAR-72)
    └── test_worker_recovery.py # Integration: worker restart recovery (FAR-73)
```

---

## Test Strategy

### Unit tests (`test_tasks_unit.py`)

Run without any broker or worker:

```bash
cd spikes/spike5_celery_redis
source ../../.venv/bin/activate
pip install -r requirements.txt
pytest tests/test_tasks_unit.py -v
```

Uses `task_always_eager=True` — tasks execute synchronously in the test process.
Validates task logic, input validation, and return value shapes.

**Expected result:** All tests pass with no network access.

### Integration tests

Require Upstash credentials and a running worker:

```bash
# Terminal 1 — start worker
source ../../.venv/bin/activate
celery -A tasks worker --loglevel=info --concurrency=2

# Terminal 2 — run integration tests
pytest tests/ -v --timeout=30 -m integration
```

Tests marked `integration` are automatically skipped if `UPSTASH_REDIS_URL` is
not configured (see `conftest.py::require_redis` fixture).

---

## Test Results Summary

### Unit tests

| Test | Status |
|---|---|
| `test_tasks_unit.py::TestProcessTranscriptUnit` | Ready to run (no credentials needed) |
| `test_tasks_unit.py::TestFailingTaskUnit` | Ready to run |
| `test_tasks_unit.py::TestSlowTaskUnit` | Ready to run |

### Integration tests

| Test file | Status | Blocker |
|---|---|---|
| `test_dispatch.py` | Pending | FAR-67 — Upstash credentials |
| `test_retry.py` | Pending | FAR-67 — Upstash credentials |
| `test_timeout.py` (config assertions) | Ready | No broker needed for config tests |
| `test_timeout.py` (live tests) | Pending | FAR-67 — Upstash credentials |
| `test_worker_recovery.py` (config assertions) | Ready | No broker needed |
| `test_worker_recovery.py` (crash test) | Manual | Requires worker process management |

---

## Key Findings

### 1. Celery + Redis transport is well-suited to the Pocket Nori use case

Meeting transcript processing is inherently async (minutes-long LLM calls). Celery provides:
- Reliable at-least-once delivery via `task_acks_late`
- Built-in retry with backoff
- Result storage with TTL
- Per-worker concurrency control

### 2. Upstash TLS requirement is a known gotcha

Upstash requires `rediss://` (double-s, TLS). Using `redis://` will fail with a
connection reset. The `.env.example` and `FINDINGS.md` document this prominently.

### 3. Visibility timeout must be set correctly

Celery Redis transport's visibility timeout defaults to 1 hour. Tasks longer than
this value will be redelivered to another worker (duplicate execution). Our
`slow_task` test exercises this scenario. Production setting should be:

```
visibility_timeout >= (longest expected task duration) + buffer
```

For Phase 1 (LLM transcript processing, estimated 30–120 s), 3600 s is safe.

### 4. Tasks must be idempotent

With `task_acks_late=True` and Redis visibility timeout semantics, a task CAN be
executed more than once (worker crashes after completion but before ack). All
Pocket Nori tasks must be designed to be idempotent — running them twice must not
produce incorrect state (e.g. deduplicate by `transcript_id` before indexing).

### 5. Prefetch multiplier = 1 is correct for long tasks

Setting `worker_prefetch_multiplier=1` ensures each worker slot holds at most
one unacknowledged task. This limits the blast radius of a worker crash and
prevents fast workers from hoarding tasks from slow queues.

---

## Go / No-Go Recommendation

**Conditional Go.**

- The Celery + Redis configuration is sound. All reliability settings (`acks_late`,
  `reject_on_worker_lost`, `visibility_timeout`, `prefetch=1`) are correctly set.
- Unit tests validate task logic without any infrastructure.
- Integration tests are written and ready to execute once Upstash credentials
  are provisioned (FAR-67).

**Proceed to Phase 1 broker provisioning once:**
1. FAR-67 is unblocked (Upstash account + credentials added to `.env`).
2. Integration tests pass against live Upstash Redis.
3. Broker choice (Upstash vs Render) is confirmed per `decision_memo.md`.

---

## Status: Pending FAR-67

> Upstash credentials not yet provisioned. Integration tests will auto-skip
> until `UPSTASH_REDIS_URL` is added to `.env`. Unit tests run immediately.
