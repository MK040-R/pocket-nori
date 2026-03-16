"""
create_linear_issues.py

Creates all Pocket Nori MVP issues in Linear via the GraphQL API.

Setup:
    export LINEAR_API_KEY=lin_api_xxxxxxxxxxxx
    export LINEAR_TEAM_NAME="Pocket Nori"   # must match your team name exactly
    source .venv/bin/activate
    python scripts/create_linear_issues.py

The script will:
  1. Find your team by name
  2. Create 12 labels (skips existing ones)
  3. Create 5 projects (one per phase)
  4. Create all parent issues + sub-issues (~311 total)

Idempotency note: The script does NOT check for duplicate issues.
Run it only once. If you need to re-run, delete the created issues in Linear first.
"""

import os
import sys
import time
import json
import requests as _requests

# ── Config ────────────────────────────────────────────────────────────────────

LINEAR_API_URL = "https://api.linear.app/graphql"
API_KEY = os.environ.get("LINEAR_API_KEY", "")
TEAM_NAME = os.environ.get("LINEAR_TEAM_NAME", "")
REQUEST_DELAY = 0.08  # seconds between API calls (~750 req/min, well under 1500 limit)

PRIORITY = {"Urgent": 1, "High": 2, "Medium": 3, "Low": 4}

LABEL_COLORS = {
    "spike":          "#F2C94C",
    "backend":        "#2F80ED",
    "frontend":       "#9B51E0",
    "database":       "#219653",
    "llm":            "#F2994A",
    "celery":         "#56CCF2",
    "security":       "#EB5757",
    "infrastructure": "#828282",
    "search":         "#6FCF97",
    "ui":             "#BB87FC",
    "testing":        "#4EA7FC",
    "data-lifecycle": "#E8A87C",
}


# ── GraphQL client ────────────────────────────────────────────────────────────

def gql(query: str, variables: dict | None = None) -> dict:
    resp = _requests.post(
        LINEAR_API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json", "Authorization": API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    time.sleep(REQUEST_DELAY)
    return data["data"]


# ── API helpers ───────────────────────────────────────────────────────────────

def get_team_id(team_name: str) -> str:
    data = gql("{ teams { nodes { id name } } }")
    for team in data["teams"]["nodes"]:
        if team["name"].lower() == team_name.lower():
            return team["id"]
    available = [t["name"] for t in data["teams"]["nodes"]]
    raise RuntimeError(
        f"Team '{team_name}' not found. Available teams: {available}\n"
        f"Set LINEAR_TEAM_NAME to one of those names."
    )


def get_existing_labels(team_id: str) -> dict[str, str]:
    """Returns {label_name: label_id} for all existing labels."""
    data = gql("{ issueLabels { nodes { id name } } }")
    return {n["name"]: n["id"] for n in data["issueLabels"]["nodes"]}


def create_label(name: str, team_id: str, color: str) -> str:
    data = gql(
        """
        mutation($name: String!, $teamId: String!, $color: String!) {
          issueLabelCreate(input: { name: $name, teamId: $teamId, color: $color }) {
            success
            issueLabel { id }
          }
        }
        """,
        {"name": name, "teamId": team_id, "color": color},
    )
    return data["issueLabelCreate"]["issueLabel"]["id"]


def ensure_labels(team_id: str) -> dict[str, str]:
    """Creates missing labels; returns {label_name: label_id} for all needed labels."""
    existing = get_existing_labels(team_id)
    result: dict[str, str] = {}
    for name, color in LABEL_COLORS.items():
        if name in existing:
            result[name] = existing[name]
            print(f"  label exists: {name}")
        else:
            lid = create_label(name, team_id, color)
            result[name] = lid
            print(f"  created label: {name}")
    return result


def create_project(name: str, team_id: str) -> str:
    data = gql(
        """
        mutation($name: String!, $teamIds: [String!]!) {
          projectCreate(input: { name: $name, teamIds: $teamIds }) {
            success
            project { id }
          }
        }
        """,
        {"name": name, "teamIds": [team_id]},
    )
    return data["projectCreate"]["project"]["id"]


def create_issue(
    title: str,
    team_id: str,
    priority: str,
    label_names: list[str],
    label_map: dict[str, str],
    project_id: str,
    parent_id: str | None = None,
) -> str:
    label_ids = [label_map[n] for n in label_names if n in label_map]
    variables: dict = {
        "title": title,
        "teamId": team_id,
        "priority": PRIORITY.get(priority, 3),
        "labelIds": label_ids,
        "projectId": project_id,
    }
    if parent_id:
        variables["parentId"] = parent_id

    data = gql(
        """
        mutation(
          $title: String!
          $teamId: String!
          $priority: Int!
          $labelIds: [String!]
          $projectId: String
          $parentId: String
        ) {
          issueCreate(input: {
            title: $title
            teamId: $teamId
            priority: $priority
            labelIds: $labelIds
            projectId: $projectId
            parentId: $parentId
          }) {
            success
            issue { id }
          }
        }
        """,
        variables,
    )
    return data["issueCreate"]["issue"]["id"]


# ── Issue definitions ─────────────────────────────────────────────────────────

def build_issue_tree() -> list[dict]:
    """
    Returns a flat list of dicts:
      { project, title, priority, labels, parent (title or None) }

    All sub-issues reference their parent by title string.
    The runner resolves titles → IDs at creation time.
    """

    rows: list[dict] = []

    def parent(title, project, priority="High", labels=""):
        rows.append({"project": project, "title": title, "priority": priority,
                     "labels": [l.strip() for l in labels.split(",") if l.strip()],
                     "parent": None})

    def sub(title, parent_title, project, priority="Medium", labels=""):
        rows.append({"project": project, "title": title, "priority": priority,
                     "labels": [l.strip() for l in labels.split(",") if l.strip()],
                     "parent": parent_title})

    P0A = "Phase 0a — Technical Spikes"
    P0  = "Phase 0 — Foundation"
    P1  = "Phase 1 — Manual Upload + Intelligence"
    P2  = "Phase 2 — Intelligence Surface"
    SEC = "Security & Infrastructure"

    # ── Phase 0a ──────────────────────────────────────────────────────────────

    p = "Spike 1 — Electron Audio Capture"
    parent(p, P0A, "Urgent", "spike,infrastructure")
    for t in [
        "Research Core Audio API on macOS for system audio capture",
        "Set up minimal Electron + TypeScript app boilerplate",
        "Implement system audio capture via Core Audio / Chromium tab capture",
        "Write captured audio to local .wav file",
        "Test capture with active Google Meet session",
        "Document go/no-go decision for Electron approach",
    ]:
        sub(t, p, P0A, "Urgent", "spike,infrastructure")

    p = "Spike 2 — Deepgram Accuracy Validation"
    parent(p, P0A, "Urgent", "spike,backend")
    for t in [
        "Collect 3 real meeting recordings for testing",
        "Set up Deepgram API account and store API key in .env",
        "Write test script: send recordings to Deepgram Nova-3",
        "Evaluate transcription accuracy vs manual check",
        "Evaluate speaker diarization quality",
        "Document go/no-go result for Deepgram spike",
    ]:
        sub(t, p, P0A, "Urgent", "spike,backend")

    p = "Spike 3 — LLM Extraction Quality"
    parent(p, P0A, "Urgent", "spike,llm")
    for t in [
        "Prepare 5 real meeting transcripts for testing",
        "Write test prompts for topic extraction (TopicList model)",
        "Write test prompts for commitment extraction (CommitmentExtraction model)",
        "Write test prompts for entity extraction (EntityList model)",
        "Run all 5 transcripts through all 3 extraction types",
        "Evaluate: coherent topics? real commitments? accurate entities?",
        "Document go/no-go result for LLM extraction spike",
    ]:
        sub(t, p, P0A, "Urgent", "spike,llm")

    p = "Spike 4 — Supabase RLS Isolation"
    parent(p, P0A, "Urgent", "spike,security,database")
    for t in [
        "Create Supabase test project",
        "Create two test users (user_a, user_b)",
        "Create sample user-owned table with FORCE RLS policy",
        "Test: user_a JWT cannot read user_b rows",
        "Write automated pytest test for cross-user isolation",
        "Verify isolation test runs in GitHub Actions CI",
        "Document go/no-go result for RLS spike",
    ]:
        sub(t, p, P0A, "Urgent", "spike,security,database")

    p = "Spike 5 — Celery + Redis Broker"
    parent(p, P0A, "Urgent", "spike,celery,backend")
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
        sub(t, p, P0A, "Urgent", "spike,celery,backend")

    # ── Phase 0 ───────────────────────────────────────────────────────────────

    p = "Project Setup & Tooling"
    parent(p, P0, "High", "backend,infrastructure")
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
        sub(t, p, P0, "High", "backend,infrastructure")

    p = "Database Schema — 9 Entities"
    parent(p, P0, "High", "database")
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
        sub(t, p, P0, "High", "database")

    p = "Row-Level Security Policies"
    parent(p, P0, "High", "security,database")
    for t in [
        "Write RLS policy: authenticated users can read/write own rows (all 9 tables)",
        "Write RLS policy: anon role has no access to any user table",
        "Document that service_role is DDL-only — enforce in code review",
        "Automated pytest: User A JWT cannot read User B rows (all 9 tables)",
        "Add RLS isolation test to GitHub Actions CI (blocks PR on failure)",
    ]:
        sub(t, p, P0, "High", "security,database")

    p = "FastAPI Skeleton"
    parent(p, P0, "High", "backend")
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
        sub(t, p, P0, "High", "backend")

    p = "Google OAuth Integration"
    parent(p, P0, "High", "backend")
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
        sub(t, p, P0, "High", "backend")

    p = "Cost Controls Setup"
    parent(p, P0, "Medium", "infrastructure")
    for t in [
        "Set $100/month spend alert on Anthropic API dashboard",
        "Set $10/day spend alert on Anthropic API dashboard",
        "Document all provider API keys in .env.example",
    ]:
        sub(t, p, P0, "Medium", "infrastructure")

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    p = "File Upload Endpoint"
    parent(p, P1, "High", "backend")
    for t in [
        "Create endpoint: POST /api/v1/conversations/upload",
        "Accept MIME types: text/plain, audio/mpeg, audio/wav, audio/x-m4a",
        "Validate file type and size (reject oversized files with HTTP 413)",
        "Store uploaded audio to temp Supabase Storage path: /users/{user_id}/temp/{uuid}",
        "Create Conversation DB record with status=processing",
        "Return conversation_id immediately (async processing begins)",
        "Write unit tests for upload validation",
    ]:
        sub(t, p, P1, "High", "backend")

    p = "Deepgram Transcription Service"
    parent(p, P1, "High", "backend,llm")
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
        sub(t, p, P1, "High", "backend,llm")

    p = "Audio Lifecycle Management"
    parent(p, P1, "High", "backend,data-lifecycle,security")
    for t in [
        "Hard-delete audio immediately after TranscriptSegments successfully persisted",
        "Celery beat task: scan temp storage, hard-delete audio older than 1 hour",
        "Audit log on every deletion: {event: audio_deleted, file_hash: sha256, ts: iso8601}",
        "Verify: no audio content in audit log (hash + timestamp only)",
        "Integration test: audio file absent from storage after successful transcription",
        "Integration test: audio file absent after 1-hour cleanup job runs",
    ]:
        sub(t, p, P1, "High", "backend,data-lifecycle,security")

    p = "TranscriptSegment Storage"
    parent(p, P1, "High", "backend,database")
    for t in [
        "Create TranscriptSegment Pydantic model with all required fields",
        "Bulk insert TranscriptSegments after Deepgram response is parsed",
        "Store per segment: conversation_id, user_id, speaker_id, start_ts, end_ts, text, segment_confidence",
        "Create btree index on (conversation_id, start_ts) for retrieval performance",
        "Verify: all TranscriptSegment rows include user_id for RLS coverage",
        "Write unit tests for bulk insert logic",
    ]:
        sub(t, p, P1, "High", "backend,database")

    p = "LLM Client Module"
    parent(p, P1, "High", "backend,llm,security")
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
        sub(t, p, P1, "High", "backend,llm,security")

    p = "LLM Extraction Pipeline"
    parent(p, P1, "High", "backend,llm")
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
        sub(t, p, P1, "High", "backend,llm")

    p = "Celery Async Pipeline"
    parent(p, P1, "High", "celery,backend")
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
        sub(t, p, P1, "High", "celery,backend")

    p = "pgvector Embeddings"
    parent(p, P1, "High", "backend,database,search")
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
        sub(t, p, P1, "High", "backend,database,search")

    p = "Topic Clustering"
    parent(p, P1, "High", "backend,llm")
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
        sub(t, p, P1, "High", "backend,llm")

    p = "Hybrid Search"
    parent(p, P1, "High", "backend,search")
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
        sub(t, p, P1, "High", "backend,search")

    p = "Web UI — Next.js Project Setup"
    parent(p, P1, "High", "frontend")
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
        sub(t, p, P1, "High", "frontend")

    p = "Web UI — Upload Interface"
    parent(p, P1, "High", "frontend,ui")
    for t in [
        "Create upload page: /upload",
        "Drag-and-drop file input (audio or .txt transcript)",
        "Client-side file type validation before sending to API",
        "Upload progress indicator (percentage bar)",
        "On success: redirect to /conversations/[id]",
        "On failure: display user-friendly error message",
        "Mobile-responsive layout",
    ]:
        sub(t, p, P1, "High", "frontend,ui")

    p = "Web UI — Conversation Detail"
    parent(p, P1, "High", "frontend,ui")
    for t in [
        "Create conversation detail page: /conversations/[id]",
        "Fetch and display extracted topics list with importance scores",
        "Fetch and display commitments with assignee and deadline",
        "Fetch and display entities (persons, projects, products)",
        "Click topic/commitment/entity → show source quote with speaker + timestamp",
        "Source quote viewer: displays TranscriptSegment text with surrounding context",
    ]:
        sub(t, p, P1, "High", "frontend,ui")

    p = "Web UI — Search"
    parent(p, P1, "High", "frontend,ui")
    for t in [
        "Create search page: /search",
        "Search input with 300ms debounce",
        "Display results with citation payload (speaker name, timestamp, snippet)",
        "Click result → navigate to /conversations/[id] at that timestamp",
        "Empty state: 'Search across all your meetings'",
        "Loading state during search API call",
    ]:
        sub(t, p, P1, "High", "frontend,ui")

    p = "Phase 1 Quality Gate"
    parent(p, P1, "High", "testing")
    for t in [
        "Run 10 real meeting transcripts through full extraction pipeline",
        "Evaluate topics: coherent? duplicates merged correctly?",
        "Evaluate commitments: real ones extracted? any missed?",
        "Evaluate connections: genuine cross-meeting links surfaced?",
        "Evaluate briefs: accurate and useful?",
        "Document results against quality thresholds",
        "Go/no-go decision for Phase 2 (written record)",
    ]:
        sub(t, p, P1, "High", "testing")

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    p = "Topic Arc"
    parent(p, P2, "High", "backend,llm,frontend")
    for t in [
        "Create TopicArc DB migration (topic_id, conversation_ids[], summary, generated_at)",
        "Celery job: build Topic Arc from Topic × Conversations ordered by time",
        "Topic Arc synthesis LLM prompt (claude-sonnet-4-6; escalate to claude-opus-4-6 if >20 source segments)",
        "Every claim in Topic Arc cites a source TranscriptSegment ID",
        "Topic Arc API endpoint: GET /api/v1/topics/{id}/arc",
        "Web UI: Topic Arc timeline page /topics/[id]/arc",
        "Display synthesized narrative with clickable citations to source transcript",
    ]:
        sub(t, p, P2, "High", "backend,llm,frontend")

    p = "Connection Detection"
    parent(p, P2, "High", "backend,llm,frontend")
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
        sub(t, p, P2, "High", "backend,llm,frontend")

    p = "Pre-Meeting Brief Generation"
    parent(p, P2, "High", "backend,llm,celery")
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
        sub(t, p, P2, "High", "backend,llm,celery")

    p = "Google Calendar Sync"
    parent(p, P2, "High", "backend")
    for t in [
        "Create Google Calendar API client using stored OAuth refresh token",
        "Handle OAuth token refresh when access token expires",
        "Fetch upcoming events for authenticated user (next 7 days)",
        "Auto-link uploaded conversations to calendar events by time window (±15 min)",
        "Calendar sync endpoint: POST /api/v1/calendar/sync",
        "Celery beat task: sync calendar every 15 minutes per active user",
        "Integration test: uploaded meeting correctly linked to calendar event",
    ]:
        sub(t, p, P2, "High", "backend")

    p = "Dashboard"
    parent(p, P2, "Medium", "frontend,ui")
    for t in [
        "Create dashboard page: / (home, authenticated)",
        "Topics overview: all user topics sorted by most recently active",
        "Upcoming meeting card: next calendar event + link to brief if ready",
        "Recent conversations list (last 5 uploads)",
        "Quick-search bar linking to /search",
        "Navigation links: Upload, Search, Commitments, Connections",
    ]:
        sub(t, p, P2, "Medium", "frontend,ui")

    p = "Commitment Tracker"
    parent(p, P2, "Medium", "backend,frontend,ui")
    for t in [
        "Create commitment tracker page: /commitments",
        "API: GET /api/v1/commitments (supports filter by status: open/resolved)",
        "List all open commitments: text, assignee, deadline, source conversation",
        "API: PATCH /api/v1/commitments/{id} with {status: resolved}",
        "Mark commitment resolved from the UI",
        "Filter controls: open, resolved, by deadline",
        "Sort by nearest deadline first",
    ]:
        sub(t, p, P2, "Medium", "backend,frontend,ui")

    # ── Security & Infrastructure ─────────────────────────────────────────────

    p = "Security — Isolation CI Tests"
    parent(p, SEC, "Urgent", "security,testing")
    for t in [
        "CI test: API endpoint isolation — User A JWT blocked from reading User B conversations",
        "CI test: vector search isolation — user_id filter applied before ANN (no cross-user results)",
        "CI test: cache key isolation — user:{user_id}: namespace enforced",
        "CI test: storage path isolation — /users/{user_id}/ prefix enforced",
        "CI test: Celery worker — user_id validated before every DB read/write",
        "CI test: service_role key never used for data reads (static analysis check)",
        "Add all 6 isolation tests to GitHub Actions — block PR merge on failure",
    ]:
        sub(t, p, SEC, "Urgent", "security,testing")

    p = "Data Lifecycle — User Hard Delete"
    parent(p, SEC, "High", "backend,security,data-lifecycle")
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
        sub(t, p, SEC, "High", "backend,security,data-lifecycle")

    p = "User Data Export"
    parent(p, SEC, "High", "backend,data-lifecycle")
    for t in [
        "Export endpoint: GET /api/v1/account/export",
        "JSON export: all Conversations, TranscriptSegments, Topics, Commitments, Entities, Connections, Briefs",
        "Generate signed download link (expires in 24 hours)",
        "Audit log: {event: user_export, user_id_hash: sha256, ts: iso8601}",
        "Web UI: 'Export my data' button in /account/settings",
    ]:
        sub(t, p, SEC, "High", "backend,data-lifecycle")

    p = "Render.com Deployment"
    parent(p, SEC, "Medium", "infrastructure")
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
        sub(t, p, SEC, "Medium", "infrastructure")

    return rows


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not API_KEY:
        print("ERROR: LINEAR_API_KEY environment variable not set.")
        print("       Get your key from: Linear → Settings → API → Personal API keys")
        sys.exit(1)
    if not TEAM_NAME:
        print("ERROR: LINEAR_TEAM_NAME environment variable not set.")
        print("       Set it to your Linear team name, e.g. export LINEAR_TEAM_NAME='Pocket Nori'")
        sys.exit(1)

    print(f"Connecting to Linear as team: {TEAM_NAME}")
    team_id = get_team_id(TEAM_NAME)
    print(f"Team ID: {team_id}\n")

    print("Setting up labels...")
    label_map = ensure_labels(team_id)
    print(f"Labels ready: {list(label_map.keys())}\n")

    # Build all issue definitions
    all_issues = build_issue_tree()
    projects_needed = sorted({i["project"] for i in all_issues})

    # Create projects
    print("Creating projects...")
    project_map: dict[str, str] = {}
    for proj_name in projects_needed:
        pid = create_project(proj_name, team_id)
        project_map[proj_name] = pid
        print(f"  created project: {proj_name}")
    print()

    # Create issues: parents first, then children
    parent_issues = [i for i in all_issues if i["parent"] is None]
    sub_issues = [i for i in all_issues if i["parent"] is not None]

    parent_id_map: dict[str, str] = {}  # title → Linear issue ID

    print(f"Creating {len(parent_issues)} parent issues...")
    for issue in parent_issues:
        iid = create_issue(
            title=issue["title"],
            team_id=team_id,
            priority=issue["priority"],
            label_names=issue["labels"],
            label_map=label_map,
            project_id=project_map[issue["project"]],
            parent_id=None,
        )
        parent_id_map[issue["title"]] = iid
        print(f"  [{issue['project']}] {issue['title']}")

    print(f"\nCreating {len(sub_issues)} sub-issues...")
    created_sub = 0
    for issue in sub_issues:
        parent_linear_id = parent_id_map.get(issue["parent"])
        if not parent_linear_id:
            print(f"  WARNING: parent not found for: {issue['title']} (parent: {issue['parent']})")
            continue
        create_issue(
            title=issue["title"],
            team_id=team_id,
            priority=issue["priority"],
            label_names=issue["labels"],
            label_map=label_map,
            project_id=project_map[issue["project"]],
            parent_id=parent_linear_id,
        )
        created_sub += 1
        print(f"  [{issue['parent'][:40]}...] {issue['title'][:60]}")

    total = len(parent_issues) + created_sub
    print(f"\nDone! Created {total} issues ({len(parent_issues)} parent + {created_sub} sub-issues)")
    print("Open Linear to verify your projects and issues.")


if __name__ == "__main__":
    main()
