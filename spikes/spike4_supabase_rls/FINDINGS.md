# Spike 4 — Supabase RLS Isolation: Findings

**Spike:** FAR-8
**Status:** Pending Supabase project creation (FAR-60)
**Date:** 2026-03-09

---

## Objective

Validate that Supabase Row Level Security (RLS) can reliably enforce per-user data isolation — the core architectural constraint for Farz. No user must be able to read, write, or enumerate another user's data at any layer.

---

## Approach

### Table design

A representative table (`conversations`) is created with a `user_id UUID NOT NULL` column that references `auth.users`. This mirrors the data model Farz will use in production (see `farz-prd.md` Section 5 — `Conversation` entity).

### RLS policy

```sql
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

CREATE POLICY "users_own_conversations"
  ON conversations
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
```

- `ENABLE ROW LEVEL SECURITY` — activates RLS on the table.
- `FORCE ROW LEVEL SECURITY` — **critical**: ensures the policy applies even to the table owner role (i.e., the `postgres` superuser role used internally by Supabase). Without `FORCE`, the table owner can bypass RLS entirely.
- `FOR ALL` — covers SELECT, INSERT, UPDATE, and DELETE in one policy.
- `USING (auth.uid() = user_id)` — filters rows on read; only rows matching the authenticated user's ID are visible.
- `WITH CHECK (auth.uid() = user_id)` — validates rows on write; prevents a user from inserting or updating a row with a spoofed `user_id`.

### Two-user test design

| Actor | Key used | Expected behaviour |
|---|---|---|
| `user_a` | Anon key + user JWT | Sees only `user_a` rows |
| `user_b` | Anon key + user JWT | Sees only `user_b` rows |
| `user_a` reading `user_b`'s row by ID | Anon key + user_a JWT | Empty result (row silently hidden by RLS) |
| Service role | Service key | Sees all rows (admin bypass — server-side only) |
| `user_a` INSERT with `user_b`'s ID | Anon key + user_a JWT | Error: RLS WITH CHECK violation |

---

## Test Plan

All tests live in `test_rls_isolation.py`. The test suite is parameterised by real JWTs produced by `setup_test_users.py`.

| Test | Assertion |
|---|---|
| `test_user_a_sees_only_own_rows` | All rows in result have `user_id == user_a.id` |
| `test_user_b_sees_only_own_rows` | All rows in result have `user_id == user_b.id` |
| `test_cross_user_isolation` | Fetching `user_b`'s row ID as `user_a` returns `[]` |
| `test_service_key_sees_all` | Service key result contains rows for both users |
| `test_insert_enforces_user_id` | Inserting with spoofed `user_id` raises exception |

---

## CI Integration

The workflow `.github/workflows/rls-test.yml` runs on every push and pull request:

1. Installs dependencies from `requirements.txt`
2. Runs `setup_test_users.py` (idempotent — safe to re-run)
3. Executes the full pytest suite with verbose output

Secrets required in the GitHub repo settings:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_ANON_KEY`

---

## Known Limitations

### Service key always bypasses RLS

The Supabase service role key (used with `SUPABASE_SERVICE_KEY`) bypasses RLS unconditionally. This is intentional for server-side admin operations (user setup, migrations, background jobs). **The service key must never be exposed to clients or embedded in front-end code.** In production, only the API server (running in a trusted environment) may hold this key.

### JWT expiry in CI

User JWTs written to `test_credentials.json` by `setup_test_users.py` expire after the Supabase project's configured JWT lifetime (default: 1 hour). The setup script re-signs in on each run, so CI always uses fresh tokens. For local development, re-run `setup_test_users.py` if tests fail with auth errors.

### `test_credentials.json` is gitignored

The file contains real JWTs. It is listed in `.gitignore` and must never be committed. In CI it is generated at runtime and discarded with the ephemeral runner.

### RLS does not protect against service-key misuse

If the service key leaks, RLS provides no protection. Key hygiene and secret rotation are the mitigations — not RLS itself.

---

## Go / No-Go Recommendation

**Recommendation: GO** (conditional on successful test run)

Supabase RLS with `FORCE ROW LEVEL SECURITY` and a correctly scoped policy provides strong, database-enforced per-user isolation that:

- Cannot be accidentally bypassed by application code (the database enforces it)
- Covers all DML operations (SELECT, INSERT, UPDATE, DELETE) in one policy
- Integrates naturally with Supabase Auth JWTs (`auth.uid()` is populated from the verified JWT automatically)
- Is auditable and version-controlled via migration SQL

The only server-side bypass (service key) is acceptable provided it is kept strictly server-side and never returned to clients.

**Blocker:** Tests cannot run until FAR-60 is complete (human must provision the Supabase project and populate `.env`).

---

## Current Status

> **Pending** — Supabase project creation (FAR-60) requires human action:
> 1. Create a project at [supabase.com](https://supabase.com)
> 2. Run migration `migrations/001_rls_test_setup.sql` in the SQL editor
> 3. Add `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY` to `.env` (copy from `.env.example`)
> 4. Run `python setup_test_users.py`
> 5. Run `pytest test_rls_isolation.py -v` — all 5 tests should pass
> 6. Update this document with actual results and flip status to GO or NO-GO
