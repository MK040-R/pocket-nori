# Farz — Linear Issues Pending Creation

> **Status:** Partially created — Linear free tier issue limit reached again at FAR-304.
> Free up space (archive/delete Done issues) then create the 22 remaining sub-tasks below.

---

## What Was Created (This Session)

| Issues | Description |
|---|---|
| FAR-276 | Commitment Tracker (parent epic) |
| FAR-277 | Data Lifecycle — User Hard Delete (parent epic) |
| FAR-278 | User Data Export (parent epic) |
| FAR-279 | Render.com Deployment (parent epic) |
| FAR-280 | Insights Page: Backend (4 analytics endpoints) |
| FAR-281 | Web UI — Insights Page (Screen 7) |
| FAR-282 | Shared Brief: Token, Public Route, Preview + Revoke |
| FAR-283 | Connections: seen_by_user + Mark-as-Seen API |
| FAR-284 | Activity Feed Endpoint (GET /activity) |
| FAR-285 | Index Stats Endpoint + PATCH /commitments/:id |
| FAR-286–290 | Dashboard sub-tasks (5 tasks under FAR-35) |
| FAR-291–297 | Commitment Tracker sub-tasks (7 tasks under FAR-276) |
| FAR-298–304 | Security — Isolation CI Test sub-tasks (7 tasks under FAR-104) |

---

## Still Pending — 22 Sub-Tasks

### Area 4: Data Lifecycle — User Hard Delete (9 sub-tasks)
**Parent:** FAR-277 | **Project:** Phase 2 — Intelligence Surface

1. **Backend Endpoint — DELETE /account** | High | backend, security, database
   - `DELETE /account` requires email confirmation in body. Validates JWT email matches. Queues Celery task `delete_user_account`, returns 202 with status URL. Returns 400 if email mismatch.

2. **Celery Task — Hard Delete All Postgres Rows** | High | backend, database
   - Deletes all rows where `user_id = {user_id}` from all 9 entity tables. Uses user JWT (never service_role) for all DB ops. Logs deletion count per table.

3. **Hard Delete pgvector Embeddings** | High | backend, database
   - Extends `delete_user_account` to delete all pgvector embeddings where `user_id = {user_id}`. Same transaction as Postgres deletion.

4. **Hard Delete Supabase Storage Files** | High | backend, infrastructure
   - Extends task to delete all files under `/users/{user_id}/` via Supabase Storage API. Retries up to 3 times on partial failure.

5. **Flush Redis Cache Keys for User** | High | backend, infrastructure
   - Extends task to flush all keys matching `user:{user_id}:*` using Redis SCAN + DEL in batches.

6. **Hard Delete Supabase Auth User** | High | backend, security
   - Final step: calls Supabase Admin API to delete user from Auth. Only acceptable use of `service_role` key in the codebase. Done last.

7. **Frontend — Delete Account Confirmation Dialog** | High | frontend, ui
   - "Delete Account" button in `/settings/account`. Opens modal with email confirmation input (disabled until email matches). Calls `DELETE /account` on submit.

8. **Frontend — Deletion Progress & Confirmation** | Medium | frontend, ui
   - Loading screen polling task status every 2s. On success, navigates to `/goodbye`. On failure, shows error + retry button.

9. **Hard Delete — Celery Task Monitoring & Logging** | Medium | backend, testing
   - Privacy-safe logging (user_id stripped). Unit tests covering success and failure paths. Both DB and storage mocked.

---

### Area 5: User Data Export (5 sub-tasks)
**Parent:** FAR-278 | **Project:** Phase 2 — Intelligence Surface

1. **Backend Endpoint — GET /export (Async Trigger)** | High | backend, security
   - Queues `export_user_data` Celery job. Returns 202 with `/export/status/{job_id}` polling URL immediately.

2. **Celery Task — Serialize User Data to JSON** | High | backend, database
   - Queries all 9 entities via RLS-enforced queries. Serializes to nested JSON with metadata (`export_timestamp`, `user_email`, `record_counts`).

3. **Compress & Upload Export to Supabase Storage** | High | backend, infrastructure
   - gzip compresses JSON. Uploads to `/users/{user_id}/exports/{timestamp}.json.gz`. Returns signed 24-hour download URL.

4. **Frontend — Export Data Button & Download Link** | Medium | frontend, ui
   - "Export My Data" in `/settings/account`. Modal with progress polling every 3s. Shows download link + expiration time on completion.

5. **Export — Celery Task Monitoring & Error Handling** | Medium | backend, testing
   - Unit tests for success, empty data, and storage failure paths. 5-minute timeout. Cleanup job to delete exports older than 7 days.

---

### Area 6: Render.com Deployment (8 sub-tasks)
**Parent:** FAR-279 | **Project:** Security & Infrastructure

1. **Render.com Account Setup & FastAPI Web Service** | High | infrastructure
   - Connect GitHub repo, create Web Service. Runtime: Python 3.13. Build: `pip install -e .`. Start: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`.

2. **Environment Variables — Backend Configuration** | High | infrastructure, security
   - Add all vars from `.env.example` to Render environment: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, UPSTASH_REDIS_URL, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET.

3. **Supabase PostgreSQL Connection (External URL)** | High | infrastructure, database
   - Set `DATABASE_URL` to Supabase external connection string. Test with `SELECT 1;`. Fallback: Render PostgreSQL add-on if Supabase connection limits hit.

4. **Render Redis Add-On (Celery Broker Fallback)** | Medium | infrastructure
   - If Upstash free tier fails, provision Render Redis (~$7/month). Update `REDIS_URL` in Render environment.

5. **Render Web Service — Next.js Frontend** | High | infrastructure
   - Second Web Service. Runtime: Node.js 20. Build: `npm install && npm run build`. Start: `npm start`. Set `NEXT_PUBLIC_API_URL` to backend URL. Match region.

6. **Custom Domain & DNS Configuration** | High | infrastructure
   - Add custom domain to frontend service. Add Render-provided CNAME to registrar. SSL auto-provisioned. Document final production URLs.

7. **Deploy Hooks — Auto-Deploy on Git Push** | Medium | infrastructure
   - Enable auto-deploy on `main` branch pushes for both services. Document Render webhook URLs.

8. **Smoke Tests — Health Check & OAuth Flow** | High | infrastructure, testing
   - Verify: `GET /health` → 200, frontend loads, Google OAuth end-to-end works, one authenticated API endpoint works with test JWT. Document in deployment checklist.
