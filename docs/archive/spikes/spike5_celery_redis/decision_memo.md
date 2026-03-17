# Broker Decision Memo — Upstash Redis vs Render Redis

**Spike:** FAR-9 — Spike 5: Celery + Redis Broker
**Date:** 2026-03-09
**Status:** Upstash confirmed for Phase 0 spike; Phase 1 decision pending spike results

---

## Options Evaluated

### Option A — Upstash Redis (Serverless)

| Attribute | Detail |
|---|---|
| Pricing | Free tier: 10,000 req/day, 256 MB storage. Pay-per-use thereafter (~$0.20 / 100K commands) |
| Protocol | Redis-compatible; **TLS required** — use `rediss://` (double-s), not `redis://` |
| Connection model | Serverless / stateless — connections are not persistent; suited to short-lived workers |
| Latency | ~1–5 ms (global edge replicas available on paid plans) |
| Setup | Web UI + instant provisioning; no infra to manage |
| Data residency | US-East-1 by default; configurable on paid plans |
| Visibility timeout | Fully supported via Celery Redis transport |
| Free tier limits | 10K req/day is ~7 req/min continuous — adequate for spike testing; insufficient for production |

**Advantages for Phase 0:**
- Zero cost for spike volume
- No infrastructure provisioning
- TLS enforced by default (aligns with privacy principles in the PRD)

**Disadvantages:**
- Free tier request cap will be hit immediately in production
- Serverless connection model adds ~1–2 ms cold overhead vs persistent connection
- Requires `rediss://` scheme — easy to misconfigure

---

### Option B — Render Redis (Managed)

| Attribute | Detail |
|---|---|
| Pricing | ~$7/month flat (Starter plan, 25 MB RAM, persistent) |
| Protocol | Standard Redis; `redis://` or `rediss://` depending on plan |
| Connection model | Persistent connections; standard Celery Redis transport |
| Latency | ~0.5–2 ms (co-located with Render web services) |
| Setup | Provisioned via Render dashboard; ~2 min |
| Data residency | US region; same region as Render web services |
| Visibility timeout | Fully supported |
| Free tier | No longer available on Render Redis |

**Advantages for Phase 1:**
- Predictable flat cost
- Persistent connections reduce per-call overhead
- Co-location with Render API services eliminates cross-datacenter latency
- Standard Redis protocol — no TLS gotchas

**Disadvantages:**
- $7/month cost even during development/staging
- Requires Render account and project setup

---

## Recommendation

### Phase 0 (Spike — now)

**Use Upstash.**

Rationale:
- Free tier is sufficient for the spike test volume (< 10K req/day).
- Zero provisioning cost during validation.
- Confirms the Celery + Redis transport works before committing to paid infra.

Action required (FAR-67): Human must create Upstash account and add `UPSTASH_REDIS_URL` to `.env`.

### Phase 1 (Production — after spike validates)

**Evaluate based on throughput.**

Decision criteria:
- If meeting processing stays under ~5K Celery task dispatches/day → Upstash pay-per-use is cost-competitive with Render ($7/month).
- If processing scales to tens of thousands of tasks/day → Render Redis flat rate becomes cheaper.
- If Pocket Nori deploys to Render (likely, given FastAPI + uvicorn stack) → co-location latency advantage favours Render Redis.

**Provisional Phase 1 recommendation: Render Redis** ($7/month), provisioned alongside the Render web service, to eliminate cross-datacenter latency and use standard Redis protocol.

---

## Configuration Notes

Both options work with the same `celeryconfig.py`. The only difference is the URL scheme:

```bash
# Upstash
UPSTASH_REDIS_URL=rediss://:password@host.upstash.io:6379

# Render Redis (if switching)
UPSTASH_REDIS_URL=redis://:password@host.render.com:6379
# or with TLS:
UPSTASH_REDIS_URL=rediss://:password@host.render.com:6380
```

The environment variable name `UPSTASH_REDIS_URL` can be renamed to `CELERY_BROKER_URL` in a future cleanup pass.
