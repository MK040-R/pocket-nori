# Pocket Nori — Master Brief: Claude Code + Codex Parallel Work Division
# Updated: 2026-03-17

---

## What Is Pocket Nori?

Pocket Nori is a personal intelligence layer for working professionals. It connects to Google Meet (via Google Drive), pulls in past meeting recordings, transcribes them, and uses AI to extract topics, commitments, entities, and connections. Users can search across all their meetings, get pre-meeting briefs, and track actions.

**Live URLs:**
- Frontend: https://pocket-nori.vercel.app
- Backend API: https://farz-personal-intelligence.onrender.com
- API docs: https://farz-personal-intelligence.onrender.com/docs
- GitHub: https://github.com/MK040-R/pocket-nori

---

## Hard Ownership Rules

```
Claude Code owns:   src/            (Python FastAPI backend)
                    tests/          (Python tests)
                    migrations/     (SQL migrations)
                    requirements.txt

Codex owns:         frontend/       (Next.js 15 + TypeScript + Tailwind)
```

**Claude Code must NOT touch:** `frontend/`
**Codex must NOT touch:** `src/`, `tests/`, `migrations/`, any `.py` file

Both agents update `PROGRESS.md` only to record their own completed waves.

---

## What's Already Shipped (MVP — Phases 1–5 + Pilot Polish)

Everything below is live and deployed:

- **Meetings import:** Google Drive transcript picker → Deepgram transcription → Claude extraction → indexed in Supabase with pgvector
- **Topics & topic intelligence:** 5-stage topic intelligence pipeline (segmentation, entity extraction, two-tier candidate identification, filtering, hybrid resolution) producing canonical `TopicNode` graph entities with accumulated aliases, entities, keywords, and graph relationships. Topic endpoint response payloads may include additional fields (`type`, `priority_level`, `entities`, `all_keywords`, `related_topic_ids`, `derived_from_id`) as additive, non-breaking changes
- **Commitments & follow-ups:** AI-extracted + manual creation, `action_type` classification, resolve/reopen
- **Entities:** People, projects, companies extracted from transcripts with mention counts
- **Connections:** Cross-meeting link detection (shared topics, entities, commitment threads)
- **Briefs:** Pre-meeting briefings composed from topic arcs + commitments + connections
- **Search:** Multi-table semantic search (topics, entities, meetings, segments) + `POST /search/ask` Q&A
- **Calendar sync:** Google Calendar integration, today's meetings
- **Home dashboard:** Quick Summary (AI-generated), KPI grid, today's meetings, actions widget
- **Onboarding:** Multi-step wizard with skip option
- **UI polish:** Insightful Dashboard design, persistent global search, profile dropdown, meeting detail tabs

**10 waves of pilot polish shipped (Waves A–J).** All merged and deployed.

---

## Current Milestone: Intelligence Action Layer

Turns the passive archive into an active execution assistant. 4 features ship in Waves A–D.

| # | Feature | What it is | Wave | Owner |
|---|---------|-----------|------|-------|
| 1 | **Chat window** | Multi-turn conversational Q&A against your meeting history | A (backend) + B (frontend) | Claude Code + Codex |
| 2 | **Meeting tagging** | Auto-categorize meetings (Strategy, Client, 1:1, etc.) + manual override + filtering | A (backend) + B (frontend) | Claude Code + Codex |
| 3 | **Draft from commitments** | One-tap: generate a draft email/message from any commitment | C (backend) + D (frontend) | Claude Code + Codex |
| 4 | **Pre-meeting prep push** | Proactive notification 30 min before meetings with brief + open items | C (backend) + D (frontend) | Claude Code + Codex |

---

## Wave A — Claude Code: Chat Backend + Meeting Tagging Backend

### Feature 1: Chat Backend

Multi-turn conversational interface over the user's indexed meeting history. Builds on existing `POST /search/ask` (single-shot Q&A) by adding conversation sessions with memory.

**New DB tables (migration):**

```sql
-- chat_sessions: persistent conversation threads
CREATE TABLE chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id),
    title       TEXT NOT NULL DEFAULT 'New chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY chat_sessions_user_policy ON chat_sessions
    USING (user_id = auth.uid());

-- chat_messages: individual messages within a session
CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES auth.users(id),
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    citations   JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY chat_messages_user_policy ON chat_messages
    USING (user_id = auth.uid());
```

**New endpoints:**

```
POST /chat
     body: { message: str, session_id?: str }
     → text/event-stream (SSE)

     SSE events:
       event: session
       data: { session_id: "uuid" }

       event: delta
       data: { content: "chunk of text" }

       event: citations
       data: [{ result_id, result_type, title, conversation_id, conversation_title, meeting_date }]

       event: done
       data: {}

     How it works:
     1. If no session_id, create a new chat_sessions row
     2. Save user message to chat_messages
     3. Retrieve last 10 messages from this session for context
     4. Run multi-table vector search (same as /search/ask) using the user's message
     5. Call Claude with: system prompt + conversation history + retrieved context
     6. Stream the response via SSE, saving assistant message on completion
     7. Auto-generate session title from first user message (Claude one-liner)

GET  /chat/sessions
     → ChatSessionSummary[]

     ChatSessionSummary: {
       id: str,
       title: str,
       created_at: str,
       updated_at: str,
       last_message_preview: str   // first 100 chars of most recent message
     }

GET  /chat/sessions/{session_id}/messages
     ?limit=50&offset=0
     → ChatMessage[]

     ChatMessage: {
       id: str,
       role: "user" | "assistant",
       content: str,
       citations: Citation[],
       created_at: str
     }

DELETE /chat/sessions/{session_id}
     → 204 No Content
```

**Files Claude Code creates/modifies:**
- `migrations/011_chat_sessions.sql` — new tables with RLS
- `src/api/routes/chat.py` — new route file with all 4 endpoints
- `src/llm_client.py` — add `stream_chat_response()` (yields chunks)
- `src/main.py` — register chat router
- `tests/test_chat.py` — unit tests

### Feature 2: Meeting Tagging Backend

Auto-categorize meetings during AI extraction. Users can also override manually.

**DB change:**

```sql
ALTER TABLE conversations
    ADD COLUMN category TEXT DEFAULT NULL
    CHECK (category IN ('strategy', 'client', '1on1', 'agency', 'partner', 'team', 'other'));
```

**Endpoint changes:**

```
GET  /conversations
     + ?category=strategy|client|1on1|agency|partner|team|other   (new filter)
     → ConversationSummary[]  (now includes category: str | null)

GET  /conversations/{id}
     → ConversationDetail     (conversation object now includes category)

PATCH /conversations/{id}
     body: { category: "strategy" | "client" | "1on1" | "agency" | "partner" | "team" | "other" }
     → 200 ConversationSummary

     New endpoint — allows manual category override.
```

**Auto-classification:**
- During AI extraction in `src/workers/extract.py`, after topics/commitments/entities are extracted, call Claude with the meeting title + first 3 topic labels + participant names to classify the meeting into one of the 7 categories
- Store result in `conversations.category`
- Existing meetings without a category: backfillable via a one-time script (not in this wave)

**Files Claude Code creates/modifies:**
- `migrations/012_conversation_category.sql` — adds column
- `src/api/routes/conversations.py` — add `?category=` filter to list, add `PATCH /{id}`, include category in response
- `src/models/conversation.py` — add `category: str | None = None` to ConversationSummary
- `src/workers/extract.py` — add category classification step
- `src/llm_client.py` — add `classify_meeting_category()` function
- `tests/test_conversations.py` — update tests

---

## Wave B — Codex: Chat UI + Meeting Tag UI

**Depends on:** Wave A API contracts (defined above). Codex can start building against these shapes immediately — use mock data until backend is live.

### Feature 1: Chat UI

**New page:** `/chat`

**What Codex builds:**

- **Chat page layout:** Two-column on desktop (session sidebar + chat area), single column on mobile
- **Session sidebar:**
  - List of past chat sessions from `GET /chat/sessions` (title + timestamp)
  - "New chat" button at top
  - Click a session → load its messages via `GET /chat/sessions/{id}/messages`
  - Delete session (with confirmation) via `DELETE /chat/sessions/{id}`
- **Chat area:**
  - Message input at bottom (textarea, submit on Enter or button click)
  - Messages display: user messages right-aligned, assistant messages left-aligned
  - Streaming response: consume SSE from `POST /chat`, render delta chunks in real-time as they arrive
  - Citations: after response completes, show citation pills below the assistant message (meeting title + date, clickable → navigates to `/meetings/{conversation_id}`)
  - Loading state: typing indicator while waiting for first delta
  - Empty state: "Ask anything about your meetings" prompt with example questions
- **Navigation:** Add "Chat" to the main nav rail (between Home and Meetings)
- **API calls:**
  - `POST /chat` — use `fetch()` with streaming (`response.body.getReader()` or `EventSource`) — NOT a regular JSON call. Auth via `credentials: "include"`.
  - `GET /chat/sessions` — standard fetch
  - `GET /chat/sessions/{id}/messages` — standard fetch
  - `DELETE /chat/sessions/{id}` — standard fetch

**api.ts additions:**
```typescript
// Chat types
interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

interface Citation {
  result_id: string;
  result_type: string;
  title: string;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string;
}

// Chat API functions
getChatSessions(): Promise<ChatSessionSummary[]>
getChatMessages(sessionId: string, limit?: number, offset?: number): Promise<ChatMessage[]>
deleteChatSession(sessionId: string): Promise<void>
// POST /chat is handled via streaming fetch, not a typed API function
```

### Feature 2: Meeting Tag UI

**Files changed:** `frontend/src/app/meetings/page.tsx`, `frontend/src/lib/api.ts`

**What Codex builds:**

- **Category filter bar** at the top of the meetings list (below the "Import past meetings" card):
  - Horizontal row of pill buttons: `All`, `Strategy`, `Client`, `1:1`, `Agency`, `Partner`, `Team`, `Other`
  - Active filter is highlighted with accent color
  - Clicking a filter adds `?category=X` to the `GET /conversations` call
  - `All` clears the filter (no `?category=` param)
- **Category badge on meeting cards:**
  - Small colored pill showing the category label (e.g., "Client", "Strategy")
  - Position: next to the existing topic label chips
  - If category is null, don't show a badge
- **Manual category edit:**
  - On meeting detail page, add a small dropdown or pill selector to change category
  - Calls `PATCH /conversations/{id}` with new category value
  - Optimistic update — show new category immediately, revert on error

**api.ts changes:**
```typescript
// Update ConversationSummary type
interface ConversationSummary {
  // ... existing fields ...
  category: string | null;  // NEW
}

// New API function
updateConversationCategory(id: string, category: string): Promise<ConversationSummary>

// Update getConversations to accept category filter
getConversations(params?: { limit?: number; offset?: number; category?: string }): Promise<ConversationSummary[]>
```

---

## Wave C — Claude Code: Draft from Commitments + Pre-Meeting Prep Backend

### Feature 3: Draft from Commitments

Generate a draft email/message from any commitment, using its linked transcript segments as context.

**New endpoint:**

```
POST /commitments/{id}/draft
     body: { format?: "email" | "message" }   // default: "email"
     → 200 DraftResponse

     DraftResponse: {
       subject: str,
       body: str,
       recipient_suggestion: str,
       commitment_text: str,
       format: "email" | "message"
     }
```

**How it works:**
1. Look up the commitment by ID (verify user ownership)
2. Fetch linked transcript segments via `commitment_segment_links` → `transcript_segments`
3. Fetch the conversation title and meeting date for context
4. Call Claude with: commitment text + transcript context + format instruction
5. Return structured draft (subject line, body, suggested recipient from the commitment owner field)

**Files Claude Code creates/modifies:**
- `src/api/routes/commitments.py` — add `POST /{id}/draft` endpoint
- `src/llm_client.py` — add `generate_commitment_draft()` function
- `tests/test_commitments.py` — update tests

### Feature 4: Pre-Meeting Prep Push Backend

Proactively generate briefs for upcoming meetings and surface them to the frontend.

**New endpoint:**

```
GET  /briefs/upcoming
     → UpcomingBrief[]

     UpcomingBrief: {
       brief_id: str,
       conversation_id: str | null,
       calendar_event_id: str,
       event_title: str,
       event_start: str,            // ISO timestamp
       minutes_until_start: int,
       preview: str,                // first 220 chars of brief content
       open_commitments_count: int,
       related_topic_count: int
     }
```

**How it works:**
1. Query Google Calendar for meetings in the next 2 hours (using existing calendar sync)
2. For each upcoming meeting, check if a brief already exists
3. If no brief exists and the meeting is within 30 minutes, auto-generate one (using existing brief pipeline)
4. Return all upcoming meetings with their brief status + metadata

**New Celery beat task:**
- `prep_upcoming_meetings` — runs every 15 minutes
- For each user with calendar sync enabled: check for meetings starting in 30 min, generate brief if missing
- Brief generation reuses existing `src/workers/` pipeline

**Files Claude Code creates/modifies:**
- `src/api/routes/briefs.py` — add `GET /upcoming` endpoint
- `src/workers/prep.py` — new Celery beat task
- `src/celery_app.py` — register beat schedule
- `tests/test_briefs.py` — update tests

---

## Wave D — Codex: Draft UI + Prep Push UI

**Depends on:** Wave C endpoints being live.

### Feature 3: Draft UI

**Files changed:** Actions page + meeting detail Actions tab

**What Codex builds:**

- **"Draft" button** on each commitment/follow-up card (both on `/commitments` Actions page and meeting detail Actions tab)
  - Small secondary button, icon + "Draft" label
  - Clicking opens a **draft modal/drawer**
- **Draft modal:**
  - Shows loading skeleton while calling `POST /commitments/{id}/draft`
  - Displays: Subject line (editable), Body (editable textarea), Suggested recipient
  - Two actions: "Copy to clipboard" (copies subject + body) and "Close"
  - Format toggle: Email vs. Message (shorter, no subject line)
  - Error state: "Couldn't generate a draft. Try again." with retry button

**api.ts additions:**
```typescript
interface DraftResponse {
  subject: string;
  body: string;
  recipient_suggestion: string;
  commitment_text: string;
  format: "email" | "message";
}

generateDraft(commitmentId: string, format?: "email" | "message"): Promise<DraftResponse>
```

### Feature 4: Pre-Meeting Prep Push UI

**Files changed:** Home page (`frontend/src/app/page.tsx`), layout

**What Codex builds:**

- **Upcoming meeting banner** on the home page (above Quick Summary):
  - Polls `GET /briefs/upcoming` on page load
  - If a meeting is within 60 minutes: show a prominent card with event title, time until start, and "View brief" button
  - "View brief" navigates to `/briefs/{brief_id}` (existing brief detail page)
  - Shows open commitments count + related topics count as small badges
  - If no upcoming meetings: don't render (no empty state needed)
- **Optional: browser notification**
  - On first visit, prompt for notification permission (subtle, non-blocking)
  - If granted + meeting within 30 min: fire a browser notification with event title + "Your brief is ready"
  - If denied: rely on the in-app banner only

**api.ts additions:**
```typescript
interface UpcomingBrief {
  brief_id: string;
  conversation_id: string | null;
  calendar_event_id: string;
  event_title: string;
  event_start: string;
  minutes_until_start: number;
  preview: string;
  open_commitments_count: number;
  related_topic_count: number;
}

getUpcomingBriefs(): Promise<UpcomingBrief[]>
```

---

## API Contract Reference — Full (Updated for Milestone 1)

All endpoints are live at: `https://farz-personal-intelligence.onrender.com`

### Chat (Wave A — new)
```
POST /chat
     body: { message: str, session_id?: str }
     → text/event-stream (SSE)
     Events: session, delta, citations, done

GET  /chat/sessions
     → ChatSessionSummary[]

GET  /chat/sessions/{session_id}/messages
     ?limit=50&offset=0
     → ChatMessage[]

DELETE /chat/sessions/{session_id}
     → 204
```

### Conversations (Wave A — extended)
```
GET  /conversations
     ?limit=50&offset=0
     ?category=strategy|client|1on1|agency|partner|team|other
     → ConversationSummary[]

GET  /conversations/{id}
     → ConversationDetail

GET  /conversations/{id}/connections
     → ConnectionsResponse

PATCH /conversations/{id}                    ← NEW
     body: { category: str }
     → 200 ConversationSummary
```

### Commitments (Wave C — extended)
```
GET  /commitments
     ?action_type=commitment|follow_up
     ?filter_status=open|resolved
     ?assignee=name
     ?topic=label
     ?meeting=id
     → CommitmentOut[]

POST /commitments
     { text, action_type, owner, due_date }
     → 201 CommitmentOut

PATCH /commitments/{id}
     { status: "resolved" | "open" }
     → 200 CommitmentOut

POST /commitments/{id}/draft               ← NEW
     { format?: "email" | "message" }
     → 200 DraftResponse
```

### Briefs (Wave C — extended)
```
GET  /briefs/latest
     ?conversation_id=X | ?calendar_event_id=Y
     → BriefLatestOut

GET  /briefs/{brief_id}
     → BriefDetailOut

GET  /briefs/upcoming                       ← NEW
     → UpcomingBrief[]
```

### Other endpoints (unchanged)
```
GET  /topics                 → TopicSummary[]
GET  /topics/{id}            → TopicDetail
POST /search                 → SearchResult[]
POST /search/ask             → { answer, citations[] }
GET  /calendar/today         → CalendarToday
GET  /index/stats            → IndexStats
GET  /entities               → Entity[]
GET  /home/summary           → { summary, generated_at }
```

---

## Design System

Direction: **Insightful Dashboard** — light mint workspace, white cards, dark navy rail, vivid green accent.

Full tokens: `.interface-design/system.md`

| Token | Value |
|-------|-------|
| Background | `#F3F8FF` |
| Primary text | `#041021` |
| Accent | `#00C27A` |
| Typography | Inter (UI) + JetBrains Mono (data) |

---

## How to Run Locally

```bash
# Backend
source .venv/bin/activate
uvicorn src.main:app --reload    # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.
