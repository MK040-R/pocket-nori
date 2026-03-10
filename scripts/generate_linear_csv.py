"""
generate_linear_csv.py

Generates farz-linear-import.csv for import into Linear.
Import via: Linear → Settings → Import → CSV

CSV columns: Title, Description, Status, Priority, Labels, Project, Parent
- Parent is blank for parent issues (Epics), set to parent title for sub-issues.
- All issues start with Status = Todo.
"""

import csv
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "farz-linear-import.csv")

FIELDNAMES = ["Title", "Description", "Status", "Priority", "Labels", "Project", "Parent"]


def issue(title, description="", priority="Medium", labels="", project="", parent=""):
    return {
        "Title": title,
        "Description": description,
        "Status": "Todo",
        "Priority": priority,
        "Labels": labels,
        "Project": project,
        "Parent": parent,
    }


def parent_issue(title, description="", priority="High", labels="", project=""):
    return issue(title, description, priority, labels, project, parent="")


def sub_issue(title, parent, description="", priority="Medium", labels="", project=""):
    return issue(title, description, priority, labels, project, parent=parent)


# ── Projects ──────────────────────────────────────────────────────────────────
P0A = "Phase 0a — Technical Spikes"
P0  = "Phase 0 — Foundation"
P1  = "Phase 1 — Manual Upload + Intelligence"
P2  = "Phase 2 — Intelligence Surface"
SEC = "Security & Infrastructure"


def build_issues():
    rows = []

    # ── Phase 0a — Technical Spikes ───────────────────────────────────────────

    p = "Spike 1 — Electron Audio Capture"
    rows.append(parent_issue(p, priority="Urgent", labels="spike,infrastructure", project=P0A))
    for t in [
        "Research Core Audio API on macOS for system audio capture",
        "Set up minimal Electron + TypeScript app boilerplate",
        "Implement system audio capture via Core Audio / Chromium tab capture",
        "Write captured audio to local .wav file",
        "Test capture with active Google Meet session",
        "Document go/no-go decision for Electron approach",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="spike,infrastructure", project=P0A))

    p = "Spike 2 — Deepgram Accuracy Validation"
    rows.append(parent_issue(p, priority="Urgent", labels="spike,backend", project=P0A))
    for t in [
        "Collect 3 real meeting recordings for testing",
        "Set up Deepgram API account and store API key in .env",
        "Write test script: send recordings to Deepgram Nova-3",
        "Evaluate transcription accuracy vs manual check",
        "Evaluate speaker diarization quality",
        "Document go/no-go result for Deepgram spike",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="spike,backend", project=P0A))

    p = "Spike 3 — LLM Extraction Quality"
    rows.append(parent_issue(p, priority="Urgent", labels="spike,llm", project=P0A))
    for t in [
        "Prepare 5 real meeting transcripts for testing",
        "Write test prompts for topic extraction (TopicList model)",
        "Write test prompts for commitment extraction (CommitmentExtraction model)",
        "Write test prompts for entity extraction (EntityList model)",
        "Run all 5 transcripts through all 3 extraction types",
        "Evaluate: coherent topics? real commitments? accurate entities?",
        "Document go/no-go result for LLM extraction spike",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="spike,llm", project=P0A))

    p = "Spike 4 — Supabase RLS Isolation"
    rows.append(parent_issue(p, priority="Urgent", labels="spike,security,database", project=P0A))
    for t in [
        "Create Supabase test project",
        "Create two test users (user_a, user_b)",
        "Create sample user-owned table with FORCE RLS policy",
        "Test: user_a JWT cannot read user_b rows",
        "Write automated pytest test for cross-user isolation",
        "Verify isolation test runs in GitHub Actions CI",
        "Document go/no-go result for RLS spike",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="spike,security,database", project=P0A))

    p = "Spike 5 — Celery + Redis Broker"
    rows.append(parent_issue(p, priority="Urgent", labels="spike,celery,backend", project=P0A))
    for t in [
        "Set up Upstash Redis account",
        "Configure Celery to use Upstash as broker",
        "Write test Celery task",
        "Test: task dispatch and result retrieval",
        "Test: retry behavior on task failure",
        "Test: visibility timeout behavior",
        "Test: worker restart recovery",
        "Decision: confirm Upstash OR provision Render Redis fallback (~$7/month)",
        "Document broker choice for Phase 0",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="spike,celery,backend", project=P0A))

    # ── Phase 0 — Foundation ──────────────────────────────────────────────────

    p = "Project Setup & Tooling"
    rows.append(parent_issue(p, priority="High", labels="backend,infrastructure", project=P0))
    for t in [
        "Create GitHub repository with branch protection on main",
        "Define project directory structure: src/api/, src/workers/, src/models/, tests/, migrations/",
        "Create pyproject.toml with all dependencies pinned (no ^ or ~)",
        "Create requirements.txt from pyproject.toml",
        "Create .env.example with all required env vars documented",
        "Add .gitignore (covers .env*, __pycache__, .venv, *.pyc)",
        "Configure ruff for linting",
        "Configure mypy for type checking",
        "Set up GitHub Actions CI: lint + type-check + test on every PR",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,infrastructure", project=P0))

    p = "Database Schema — 9 Entities"
    rows.append(parent_issue(p, priority="High", labels="database", project=P0))
    for t in [
        "Create Supabase project (production)",
        "Write migration: Conversation table",
        "Write migration: TranscriptSegment table",
        "Write migration: Topic table",
        "Write migration: TopicArc table",
        "Write migration: Connection table",
        "Write migration: Commitment table",
        "Write migration: Entity table",
        "Write migration: Brief table",
        "Write migration: Index table",
        "Apply FORCE ROW LEVEL SECURITY to all 9 user-owned tables",
        "Verify: zero deleted_at columns on any table",
        "Enable pgvector extension in Supabase",
        "Write migration: add embedding columns to Conversation, TranscriptSegment, Topic, Commitment",
        "Write migration: create vector indexes (ivfflat or hnsw) with user_id filter support",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="database", project=P0))

    p = "Row-Level Security Policies"
    rows.append(parent_issue(p, priority="High", labels="security,database", project=P0))
    for t in [
        "Write RLS policy: authenticated users can read/write own rows (all 9 tables)",
        "Write RLS policy: anon role has no access to any user table",
        "Document that service_role is DDL-only — enforce in code review",
        "Automated pytest: User A JWT cannot read User B rows (all 9 tables)",
        "Add RLS isolation test to GitHub Actions CI (blocks PR on failure)",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="security,database", project=P0))

    p = "FastAPI Skeleton"
    rows.append(parent_issue(p, priority="High", labels="backend", project=P0))
    for t in [
        "Initialize FastAPI app with lifespan handler",
        "Configure Pydantic Settings class (reads from .env at startup)",
        "Startup validation: raise RuntimeError if ANTHROPIC_API_KEY not set",
        "Startup validation: raise RuntimeError if DATABASE_URL not set",
        "Startup validation: raise RuntimeError if REDIS_URL not set",
        "JWT auth middleware: extract and validate user_id from Supabase JWT",
        "Inject user_id into every DB query via dependency injection",
        "Health check endpoint: GET /health → 200 OK",
        "Enable OpenAPI docs: GET /docs (development only)",
        "Write unit tests for JWT auth middleware",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend", project=P0))

    p = "Google OAuth Integration"
    rows.append(parent_issue(p, priority="High", labels="backend", project=P0))
    for t in [
        "Create Google Cloud project and configure OAuth 2.0 credentials",
        "Configure Supabase Auth: enable Google OAuth provider",
        "Implement OAuth login endpoint: GET /auth/login",
        "Implement OAuth callback handler: GET /auth/callback",
        "Request scopes: calendar.readonly, profile, email",
        "Store Google access + refresh tokens in Supabase Auth",
        "Verify: auth.uid() works in all RLS policies after login",
        "End-to-end manual test: login → calendar.readonly access confirmed",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend", project=P0))

    p = "Cost Controls Setup"
    rows.append(parent_issue(p, priority="Medium", labels="infrastructure", project=P0))
    for t in [
        "Set $100/month spend alert on Anthropic API dashboard",
        "Set $10/day spend alert on Anthropic API dashboard",
        "Document all provider API keys in .env.example",
    ]:
        rows.append(sub_issue(t, p, priority="Medium", labels="infrastructure", project=P0))

    # ── Phase 1 — Manual Upload + Intelligence ────────────────────────────────

    p = "File Upload Endpoint"
    rows.append(parent_issue(p, priority="High", labels="backend", project=P1))
    for t in [
        "Create endpoint: POST /api/v1/conversations/upload",
        "Accept MIME types: text/plain, audio/mpeg, audio/wav, audio/x-m4a",
        "Validate file type and size (reject oversized files with HTTP 413)",
        "Store uploaded audio to temp Supabase Storage path: /users/{user_id}/temp/{uuid}",
        "Create Conversation DB record with status=processing",
        "Return conversation_id immediately (async processing begins)",
        "Write unit tests for upload validation",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend", project=P1))

    p = "Deepgram Transcription Service"
    rows.append(parent_issue(p, priority="High", labels="backend,llm", project=P1))
    for t in [
        "Install Deepgram Python SDK (pin version in pyproject.toml)",
        "Create Deepgram client wrapper in src/services/deepgram.py",
        "Implement async file transcription: Nova-3, diarize=true",
        "Parse Deepgram response: extract words, speaker labels, timestamps",
        "Chunk transcript into speaker-turn segments (hard cap 220 tokens, 40-token overlap)",
        "Handle Deepgram API errors: log error, do not expose to client",
        "Handle Deepgram timeout: trigger 1-hour audio cleanup job",
        "Write unit tests for Deepgram client with mocked API responses",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm", project=P1))

    p = "Audio Lifecycle Management"
    rows.append(parent_issue(p, priority="High", labels="backend,data-lifecycle,security", project=P1))
    for t in [
        "Hard-delete audio immediately after TranscriptSegments successfully persisted",
        "Celery beat task: scan temp storage, hard-delete audio older than 1 hour",
        "Audit log on every deletion: {event: audio_deleted, file_hash: sha256, ts: iso8601}",
        "Verify: no audio content in audit log (hash + timestamp only)",
        "Integration test: audio file absent from storage after successful transcription",
        "Integration test: audio file absent after 1-hour cleanup job runs",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,data-lifecycle,security", project=P1))

    p = "TranscriptSegment Storage"
    rows.append(parent_issue(p, priority="High", labels="backend,database", project=P1))
    for t in [
        "Create TranscriptSegment Pydantic model with all required fields",
        "Bulk insert TranscriptSegments after Deepgram response is parsed",
        "Store per segment: conversation_id, user_id, speaker_id, start_ts, end_ts, text, segment_confidence",
        "Create btree index on (conversation_id, start_ts) for retrieval performance",
        "Verify: all TranscriptSegment rows include user_id for RLS coverage",
        "Write unit tests for bulk insert logic",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,database", project=P1))

    p = "LLM Client Module"
    rows.append(parent_issue(p, priority="High", labels="backend,llm,security", project=P1))
    for t in [
        "Create src/services/llm_client.py as single entry point for all LLM calls",
        "Install anthropic SDK and instructor library (pin versions)",
        "Route all LLM calls through llm_client.py — zero direct SDK calls elsewhere",
        "Startup enforcement: raise error if unconfigured provider is called",
        "Token budget guard: max 8,000 input tokens per extraction call",
        "Token budget guard: max 16,000 input tokens per Brief generation call",
        "Ensure transcript text never appears in application logs or tracebacks",
        "Write unit tests for routing logic and token budget enforcement",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm,security", project=P1))

    p = "LLM Extraction Pipeline"
    rows.append(parent_issue(p, priority="High", labels="backend,llm", project=P1))
    for t in [
        "Define TopicList Pydantic model (topics, sentiment, importance_score, segment_ids)",
        "Define CommitmentExtraction Pydantic model (text, assignee, deadline, confidence_score, segment_ids)",
        "Define EntityList Pydantic model (persons, projects, products, segment_ids)",
        "Write topic extraction prompt + instructor call → TopicList",
        "Write commitment extraction prompt + instructor call → CommitmentExtraction",
        "Write entity extraction prompt + instructor call → EntityList",
        "Link all extracted entities to source TranscriptSegment IDs via segment_ids",
        "Handle instructor validation errors: retry once with simplified prompt, then log + skip",
        "Write unit tests for each extraction type with real transcript fixtures",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm", project=P1))

    p = "Celery Async Pipeline"
    rows.append(parent_issue(p, priority="High", labels="celery,backend", project=P1))
    for t in [
        "Create Celery app in src/workers/celery_app.py",
        "Configure Celery broker URL from REDIS_URL env var",
        "Celery task: trigger full extraction pipeline after transcript stored",
        "Task execution order: entity extraction → topic clustering → commitment detection → embedding generation → brief pre-computation",
        "Pass user JWT in task payload (never service_role key)",
        "Worker verifies user_id ownership before every DB read/write",
        "Configure retry: 3 attempts, exponential backoff (60s, 120s, 240s)",
        "Integration test: end-to-end pipeline from upload trigger to topics/commitments in DB",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="celery,backend", project=P1))

    p = "pgvector Embeddings"
    rows.append(parent_issue(p, priority="High", labels="backend,database,search", project=P1))
    for t in [
        "Confirm embedding provider (Anthropic or OpenAI text-embedding-3-small)",
        "Create embedding generation function in src/services/embeddings.py",
        "Celery task: generate and store embedding for each new Conversation",
        "Celery task: generate and store embedding for each new TranscriptSegment",
        "Celery task: generate and store embedding for each new Topic",
        "Celery task: generate and store embedding for each new Commitment",
        "Verify: user_id filter applied before every ANN search (never global scan)",
        "Write unit tests for embedding generation with mocked API responses",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,database,search", project=P1))

    p = "Topic Clustering"
    rows.append(parent_issue(p, priority="High", labels="backend,llm", project=P1))
    for t in [
        "Celery job: extract candidate topics from new transcript via LLM",
        "Embed each candidate topic using embedding service",
        "Query existing user topic embeddings (user_id filter, top-K cosine similarity)",
        "Auto-merge: similarity ≥ 0.85 → merge into existing Topic, update last_mentioned",
        "Flag for review: similarity 0.65–0.85 → mark topic link as needs_review",
        "Create new Topic: similarity < 0.65",
        "Store confidence_score on every Topic ↔ Conversation link",
        "User correction endpoint: POST /api/v1/topics/{id}/confirm",
        "User correction endpoint: POST /api/v1/topics/{id}/reject",
        "Store user corrections as labeled signal for future tuning",
        "Write unit tests for merge logic (all three threshold branches)",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm", project=P1))

    p = "Hybrid Search"
    rows.append(parent_issue(p, priority="High", labels="backend,search", project=P1))
    for t in [
        "Embed search query via embedding service",
        "pgvector ANN search: top-50 candidates, user_id filter applied first",
        "PostgreSQL full-text search: tsvector/tsquery with ts_rank_cd, top-50 candidates",
        "Normalize both scores to [0, 1] range",
        "Hybrid ranking formula: 0.65 × vector_score + 0.35 × lexical_score",
        "Deterministic reranker: top-20 combined candidates → return top-8",
        "Citation payload on all results: conversation_id, start_ts, end_ts, speaker_id, snippet, score",
        "Search endpoint: POST /api/v1/search with {query: string} body",
        "Write unit tests for hybrid ranking formula",
        "Write integration test: search returns relevant results with citations",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,search", project=P1))

    p = "Web UI — Next.js Project Setup"
    rows.append(parent_issue(p, priority="High", labels="frontend", project=P1))
    for t in [
        "Initialize Next.js 15 project with TypeScript and Tailwind CSS",
        "Configure Next.js API proxy to FastAPI backend (next.config rewrites)",
        "Install and configure Supabase Auth client (@supabase/ssr)",
        "Create auth middleware: redirect to /login if unauthenticated",
        "Create login page: /login with Google OAuth button",
        "Handle OAuth callback and session storage in Next.js",
        "Set up NEXT_PUBLIC_* env vars in .env.example",
        "Configure ESLint + Prettier for TypeScript",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="frontend", project=P1))

    p = "Web UI — Upload Interface"
    rows.append(parent_issue(p, priority="High", labels="frontend,ui", project=P1))
    for t in [
        "Create upload page: /upload",
        "Drag-and-drop file input (audio or .txt transcript)",
        "Client-side file type validation before sending to API",
        "Upload progress indicator (percentage bar)",
        "On success: redirect to /conversations/[id]",
        "On failure: display user-friendly error message",
        "Mobile-responsive layout",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="frontend,ui", project=P1))

    p = "Web UI — Conversation Detail"
    rows.append(parent_issue(p, priority="High", labels="frontend,ui", project=P1))
    for t in [
        "Create conversation detail page: /conversations/[id]",
        "Fetch and display extracted topics list with importance scores",
        "Fetch and display commitments with assignee and deadline",
        "Fetch and display entities (persons, projects, products)",
        "Click topic/commitment/entity → show source quote with speaker + timestamp",
        "Source quote viewer: displays TranscriptSegment text with surrounding context",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="frontend,ui", project=P1))

    p = "Web UI — Search"
    rows.append(parent_issue(p, priority="High", labels="frontend,ui", project=P1))
    for t in [
        "Create search page: /search",
        "Search input with 300ms debounce",
        "Display results with citation payload (speaker name, timestamp, snippet)",
        "Click result → navigate to /conversations/[id] at that timestamp",
        "Empty state: 'Search across all your meetings'",
        "Loading state during search API call",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="frontend,ui", project=P1))

    p = "Phase 1 Quality Gate"
    rows.append(parent_issue(p, priority="High", labels="testing", project=P1))
    for t in [
        "Run 10 real meeting transcripts through full extraction pipeline",
        "Evaluate topics: coherent? duplicates merged correctly?",
        "Evaluate commitments: real ones extracted? any missed?",
        "Evaluate connections: genuine cross-meeting links surfaced?",
        "Evaluate briefs: accurate and useful?",
        "Document results against quality thresholds",
        "Go/no-go decision for Phase 2 (written record)",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="testing", project=P1))

    # ── Phase 2 — Intelligence Surface ────────────────────────────────────────

    p = "Topic Arc"
    rows.append(parent_issue(p, priority="High", labels="backend,llm,frontend", project=P2))
    for t in [
        "Create TopicArc DB migration (topic_id, conversation_ids[], summary, generated_at)",
        "Celery job: build Topic Arc from Topic × Conversations ordered by time",
        "Topic Arc synthesis LLM prompt (claude-sonnet-4-6; escalate to claude-opus-4-6 if >20 source segments)",
        "Every claim in Topic Arc cites a source TranscriptSegment ID",
        "Topic Arc API endpoint: GET /api/v1/topics/{id}/arc",
        "Web UI: Topic Arc timeline page /topics/[id]/arc",
        "Display synthesized narrative with clickable citations to source transcript",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm,frontend", project=P2))

    p = "Connection Detection"
    rows.append(parent_issue(p, priority="High", labels="backend,llm,frontend", project=P2))
    for t in [
        "Connection detection algorithm: find conversations sharing entities or topics",
        "Calculate confidence score per connection (based on entity/topic overlap)",
        "Store: connection_type, source_conversation_ids, linked_segment_ids, confidence_score, review_status",
        "Celery job: run connection detection after each new transcript is indexed",
        "User action: confirm a connection",
        "User action: dismiss a connection",
        "Connection API: GET /api/v1/connections (sorted by confidence desc)",
        "Web UI: connections list page /connections with confidence indicator",
        "Dismiss/confirm buttons update review_status in DB",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm,frontend", project=P2))

    p = "Pre-Meeting Brief Generation"
    rows.append(parent_issue(p, priority="High", labels="backend,llm,celery", project=P2))
    for t in [
        "Brief generation prompt: compose from Topic Arcs + open Commitments + Connections + calendar event title",
        "Use claude-opus-4-6 for brief generation",
        "Every factual claim in brief must cite a source TranscriptSegment",
        "Citation coverage check: ≥ 95% of factual claims must have a citation",
        "Celery beat task: poll upcoming calendar events every 5 minutes",
        "Trigger brief generation at T-12 minutes before event start",
        "Late delivery fallback: if T-12 window missed, generate immediately with is_late=true",
        "Cache generated brief in Redis: user:{user_id}:brief:{calendar_event_id} (TTL = meeting end + 1h)",
        "Brief API: GET /api/v1/briefs/{calendar_event_id}",
        "Web UI: brief view page /briefs/[eventId]",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,llm,celery", project=P2))

    p = "Google Calendar Sync"
    rows.append(parent_issue(p, priority="High", labels="backend", project=P2))
    for t in [
        "Create Google Calendar API client using stored OAuth refresh token",
        "Handle OAuth token refresh when access token expires",
        "Fetch upcoming events for authenticated user (next 7 days)",
        "Auto-link uploaded conversations to calendar events by time window (±15 min)",
        "Calendar sync endpoint: POST /api/v1/calendar/sync",
        "Celery beat task: sync calendar every 15 minutes per active user",
        "Integration test: uploaded meeting correctly linked to calendar event",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend", project=P2))

    p = "Dashboard"
    rows.append(parent_issue(p, priority="Medium", labels="frontend,ui", project=P2))
    for t in [
        "Create dashboard page: / (home, authenticated)",
        "Topics overview: all user topics sorted by most recently active",
        "Upcoming meeting card: next calendar event + link to brief if ready",
        "Recent conversations list (last 5 uploads)",
        "Quick-search bar linking to /search",
        "Navigation links: Upload, Search, Commitments, Connections",
    ]:
        rows.append(sub_issue(t, p, priority="Medium", labels="frontend,ui", project=P2))

    p = "Commitment Tracker"
    rows.append(parent_issue(p, priority="Medium", labels="backend,frontend,ui", project=P2))
    for t in [
        "Create commitment tracker page: /commitments",
        "API: GET /api/v1/commitments (supports filter by status: open/resolved)",
        "List all open commitments: text, assignee, deadline, source conversation",
        "API: PATCH /api/v1/commitments/{id} with {status: resolved}",
        "Mark commitment resolved from the UI",
        "Filter controls: open, resolved, by deadline",
        "Sort by nearest deadline first",
    ]:
        rows.append(sub_issue(t, p, priority="Medium", labels="backend,frontend,ui", project=P2))

    # ── Security & Infrastructure ─────────────────────────────────────────────

    p = "Security — Isolation CI Tests"
    rows.append(parent_issue(p, priority="Urgent", labels="security,testing", project=SEC))
    for t in [
        "CI test: API endpoint isolation — User A JWT blocked from reading User B conversations",
        "CI test: vector search isolation — user_id filter applied before ANN (no cross-user results)",
        "CI test: cache key isolation — user:{user_id}: namespace enforced",
        "CI test: storage path isolation — /users/{user_id}/ prefix enforced",
        "CI test: Celery worker — user_id validated before every DB read/write",
        "CI test: service_role key never used for data reads (static analysis check)",
        "Add all 6 isolation tests to GitHub Actions — block PR merge on failure",
    ]:
        rows.append(sub_issue(t, p, priority="Urgent", labels="security,testing", project=SEC))

    p = "Data Lifecycle — User Hard Delete"
    rows.append(parent_issue(p, priority="High", labels="backend,security,data-lifecycle", project=SEC))
    for t in [
        "Implement DELETE /api/v1/account endpoint (requires re-auth confirmation)",
        "CASCADE delete all Postgres rows across all 9 tables for user",
        "Delete all pgvector embeddings WHERE user_id = $1",
        "Delete all Redis cache keys: SCAN user:{user_id}:* + DEL",
        "Delete all Supabase Storage objects under /users/{user_id}/ prefix",
        "Delete all derived artifacts: Briefs, Topic Arcs, Connections",
        "Audit log: {event: user_delete, user_id_hash: sha256, ts: iso8601} — no content logged",
        "Integration test: all 6 stores empty after delete endpoint called",
        "Web UI: delete account button in /account/settings with confirmation modal",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,security,data-lifecycle", project=SEC))

    p = "User Data Export"
    rows.append(parent_issue(p, priority="High", labels="backend,data-lifecycle", project=SEC))
    for t in [
        "Export endpoint: GET /api/v1/account/export",
        "JSON export: all Conversations, TranscriptSegments, Topics, Commitments, Entities, Connections, Briefs",
        "Generate signed download link (expires in 24 hours)",
        "Audit log: {event: user_export, user_id_hash: sha256, ts: iso8601}",
        "Web UI: 'Export my data' button in /account/settings",
    ]:
        rows.append(sub_issue(t, p, priority="High", labels="backend,data-lifecycle", project=SEC))

    p = "Render.com Deployment"
    rows.append(parent_issue(p, priority="Medium", labels="infrastructure", project=SEC))
    for t in [
        "Create Render.com account and project",
        "Configure FastAPI web service (Python, auto-deploy from GitHub main)",
        "Configure Celery worker service (background worker, same Docker image)",
        "Set all environment variables in Render dashboard",
        "Configure Upstash Redis connection (cache)",
        "Configure Redis broker (Upstash or Render Redis per Spike 5 result)",
        "Verify: GET /health returns 200 after deploy",
        "Monitor Supabase free tier limits (storage + row count dashboard)",
    ]:
        rows.append(sub_issue(t, p, priority="Medium", labels="infrastructure", project=SEC))

    return rows


def main():
    rows = build_issues()
    out = os.path.abspath(OUTPUT_PATH)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    parents = sum(1 for r in rows if not r["Parent"])
    sub = total - parents
    print(f"Written {total} issues ({parents} parent, {sub} sub-issues) → {out}")


if __name__ == "__main__":
    main()
