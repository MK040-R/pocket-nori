# Farz UI Specification
## Product Intelligence Layer — Frontend & Backend Reference

> **Status:** Approved for implementation
> **Audience:** Frontend engineers, backend engineers, product
> **Dependency:** Read `farz-prd.md` (Section 3, 5, 6) before this document

---

## 1. Conceptual Architecture

Before any screen, this section defines what each core object is, why it exists, and what the system must produce to render it. Backend teams should treat this as the object model; frontend teams should treat it as the data contract.

### 1.1 Object Definitions

#### Conversation
The atomic unit of the system. One Google Meet session = one Conversation.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `source_platform` | enum | `google_meet` (Phase 1) |
| `started_at` | timestamp | |
| `duration_seconds` | int | |
| `participants` | string[] | Names or email addresses |
| `raw_transcript` | text | Speaker-attributed, timestamped |
| `summary` | text | LLM-generated. Renders as the hero in Meeting Detail. |
| `topics` | Topic[] | System-extracted, not user-created |
| `commitments` | Commitment[] | System-extracted |

**Key constraint:** Users never interact with a raw Conversation object directly. They interact with the `summary`, `topics`, `commitments`, and `transcript` fields surfaced through Meeting Detail.

---

#### Topic
A recurring subject identified across one or more Conversations. Never user-created.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `label` | string | Canonical label after deduplication (e.g., "Reporting Feature") |
| `aliases` | string[] | Variations the system unified ("reporting feature", "custom reports") |
| `first_mentioned_at` | timestamp | |
| `last_mentioned_at` | timestamp | |
| `status` | enum | `open` / `resolved` |
| `conversation_ids` | UUID[] | All Conversations where this topic appeared |

**Key constraint:** Topics are system-extracted, never user-created. They render in three places: (1) as clickable cards on the Search landing page (the browsable Topic directory), (2) as tags within Meeting Detail linking to their Arc, and (3) as the organizing unit of Topic Arc results.

---

#### Topic Arc
The synthesized chronological narrative of a Topic across all linked Conversations. This is the **output format of Search**, not a stored entity. It is computed on query.

| Field | Type | Notes |
|---|---|---|
| `topic` | Topic | The topic being described |
| `conversation_count` | int | How many Conversations mention this topic |
| `arc_points` | ArcPoint[] | Ordered chronologically |
| `status` | enum | `open` / `resolved` |
| `status_note` | string | e.g., "No delivery date committed. Last discussed Mar 7." |

**ArcPoint:**

| Field | Type | Notes |
|---|---|---|
| `conversation_id` | UUID | Source Conversation |
| `conversation_title` | string | e.g., "Product Review" |
| `occurred_at` | timestamp | |
| `summary` | string | 2–3 sentence synthesis of what was said about this topic in this conversation |
| `transcript_offset_seconds` | int | Timestamp for "Jump to clip" link |

**Key constraint:** An Arc can only be rendered when a Topic appears in 2+ Conversations. With only 1 Conversation, Search returns a single-meeting result with a note that "more context will appear as more meetings are indexed."

**Key constraint:** Every ArcPoint must cite its source `conversation_id` and `transcript_offset_seconds`. No claim in the Arc is rendered without a citation. This is the trust model.

---

#### Connection
A detected relationship between two or more Conversations that discussed the same topic without coordination between their participant groups.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `conversation_ids` | UUID[] | The connected conversations (minimum 2) |
| `topic_id` | UUID | The topic that connects them |
| `rationale` | string | **Required.** Human-readable explanation of why these are connected. e.g., "Both meetings referenced Acme's reporting request in the context of Q2 scope decisions." |
| `detected_at` | timestamp | |
| `seen_by_user` | bool | For Dashboard "new" indicator |

**Key constraint:** A Connection without a `rationale` must not be surfaced. The rationale is the value — a list of linked meetings without explanation is noise.

---

#### Commitment
A future-action statement extracted from a Conversation, attributed to a specific participant.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `conversation_id` | UUID | Source Conversation |
| `attributed_to` | string | The person who made the commitment (usually the current user) |
| `extracted_text` | string | Verbatim-ish extracted statement, e.g., "Send wireframes to the team by Friday" |
| `due_date` | date | nullable — may not be mentioned |
| `status` | enum | `open` / `resolved` |
| `resolved_at` | timestamp | nullable |

**Key constraint:** Commitments are extracted from Day 1. Even a single indexed meeting may yield Commitments. The backend must process Commitment extraction immediately upon indexing any Conversation.

---

#### Brief
A pre-meeting preparation document generated for an upcoming meeting. Forward-facing — about the next session, not a summary of the past.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `meeting_series_id` | string | Google Calendar recurring event ID |
| `generated_for_date` | date | The upcoming meeting date |
| `last_session_summary` | text | LLM-generated summary of the most recent prior Conversation in this series |
| `relevant_commitments` | Commitment[] | Open commitments attributed to user that are relevant to this meeting |
| `relevant_connections` | Connection[] | Connections the system flagged as pertinent |
| `suggested_agenda` | string[] | Ordered list of agenda items derived from open threads |
| `generated_at` | timestamp | |
| `share_token` | UUID | nullable — created when user shares the Brief |
| `share_revoked_at` | timestamp | nullable |

**Key constraint (MVP):** AI-generated Briefs are for recurring meeting series only. At least one prior Conversation in the same recurring series must be indexed. Non-recurring meetings and first-ever sessions in any series do not receive auto-generated Briefs — users may manually surface related context via Search and Meetings. Automatic Brief generation for non-recurring meetings is a post-MVP feature.

**Key constraint:** Briefs must be generated ~10–15 minutes before the scheduled meeting start time. Backend must run a scheduled job for this.

---

#### Index
The user's isolated personal store. Not an API entity — it is the architectural boundary. All objects above (Conversations, Topics, Connections, Commitments, Briefs) belong to one user's Index. No object is shared between users at the data layer. Cross-user data does not exist.

---

### 1.2 Entity Relationships

```
User.Index
├── Conversations [1..N]
│   ├── summary: string                  → renders in Meeting Detail (hero)
│   ├── raw_transcript: text             → renders in Meeting Detail (collapsible)
│   ├── topics: Topic[]                  → renders as tags, links to Topic Arc
│   └── commitments: Commitment[]        → renders in Meeting Detail + Commitments page
│
├── Topics [0..N]
│   └── linked to: Conversations [1..N]
│
│   Topic Arc (computed on query)
│   └── composed from: Topics × Conversations, ordered by time
│
├── Connections [0..N]
│   ├── links: Conversations [2..N]
│   ├── via: Topic [1]
│   └── rationale: string               → required, renders on Connection card
│
└── Briefs [0..N]
    └── composed from: Topic Arc + Commitments + Connections + Calendar event
```

---

## 2. User Journey — Three Phases

Understanding these phases is critical for both frontend (progressive states) and backend (what must be ready by when).

### Phase 1 — Day 1: The Transcript Layer

**Problem:** A new user has no indexed meetings. Arcs don't exist. Briefs can't generate. Connections can't detect. An empty Dashboard drives churn.

**Solution: Retroactive import.** On first login, Farz detects past Google Meet recordings and offers to import them. One click gives the user weeks of meeting history immediately.

**Backend must:**
- On auth completion, enumerate available past Google Meet recordings (configurable lookback window, default 60 days)
- Expose an import endpoint that bulk-ingests and processes Conversations
- Immediately extract `summary`, `topics`, and `commitments` for each indexed Conversation
- Surface import progress state to the frontend

**Frontend must:**
- Detect "0 meetings indexed" state on first login and redirect to Onboarding screen
- Show import progress with a live count
- After import, redirect to Dashboard with "Day 1" state (no Briefs, no Connections, but Commitments and Meetings populated)

**Day 1 value (no prior history required):**
- Meeting summaries readable without re-watching
- Commitment history from past meetings surfaced immediately
- Keyword search across indexed meetings works (primitive, single-meeting results)
- For recurring meetings with 2+ indexed sessions: Brief is already ready

---

### Phase 2 — Week 1–2: Intelligence Activates

After 5–10 meetings indexed across multiple sessions:

- Topics start unifying across Conversations
- Search returns multi-Conversation results (primitive Topic Arcs form)
- First Brief is generated for a recurring meeting — the **"aha moment"**. User receives a push notification 10 minutes before their recurring standup: "Here's what happened last time, and what you committed to." They didn't configure anything. It appeared.
- First Brief is often the viral moment: user shares it with attendees; colleagues ask what generated it

**Dashboard changes:**
- `✦ Brief ready` badge appears on recurring meeting cards
- "Last time: [one-liner]" context appears under meeting titles
- Open Commitments section fills in
- First Connection may appear in the "New Connections" section

---

### Phase 3 — Month 1+: Full Intelligence

- Topic Arcs are rich (10+ data points per topic, spanning months)
- Connections are frequent and contextually meaningful
- Briefs for all recurring meetings are comprehensive (last session + commitments + connections + suggested agenda)
- Insights page shows meaningful patterns: topic trends, commitment completion rate, cross-group topic bridges
- Farz has become the default pre-meeting ritual and the go-to answer for "did we decide this?"

---

## 3. Navigation Architecture

### 3.1 Primary Navigation

Five items. Fixed left sidebar. Order matters — reflects frequency and urgency of use.

```
Dashboard  ·  Search  ·  Meetings  ·  Commitments  ·  Insights
```

| Item | Primary Use | Day 1 Experience | Requires Data |
|---|---|---|---|
| **Dashboard** | Daily starting point — today's meetings, open commitments, new connections | Functional (calendar + import progress + commitments from past meetings) | Calendar access (Day 0) |
| **Search** | Deliberate query → Topic Arc | Works (keyword results from single meetings) | 1 indexed meeting |
| **Meetings** | Browse meeting history + access upcoming | Fully functional after first meeting | 1 indexed meeting |
| **Commitments** | Full cross-meeting commitment list | Populated immediately after import | 1 indexed meeting |
| **Insights** | Pattern analytics — topic trends, commitment rate, meeting load | "Building" state until 10+ meetings indexed | ~10 meetings |

### 3.2 Why Briefs Is NOT in Primary Nav

A Brief belongs to a specific Meeting. It is always accessed in context:
- From the Dashboard → "Open Brief →" on a meeting card
- From Meeting Detail → "View Brief that was generated before this →"

Making Briefs a top-level nav item would suggest it's an independent object. It isn't — it's a view over a Meeting's context. No standalone Briefs log is needed.

### 3.3 Why "Conversations" Is Not Separate

Meetings *are* Conversations. Each row in the Meetings list is one Conversation. The Meeting Detail screen is the conversation record — it shows the summary (hero), transcript (collapsible), extracted commitments, tagged topics, and connections. A separate "Conversations" nav item would duplicate Meetings.

### 3.4 Information Architecture

```
FARZ
├── / (Dashboard)
│   ├── Today's meetings + Brief status
│   ├── Open Commitments (top 3, by due date)
│   ├── New Connections (flagged since last visit)
│   └── Recent activity feed
│
├── /search (Search — Topic Directory)
│   ├── Open Topics (status=open, sorted by last mentioned)
│   ├── Recent Topics (last 7 days)
│   └── All Topics (full directory, sortable)
│
├── /search?q=:query (Topic Arc — result state)
│   ├── Timeline visualization
│   ├── ArcPoints (chronological, cited)
│   └── Status note (open / resolved)
│
├── /meetings (Meetings Library)
│   ├── Upcoming (today, from calendar)
│   └── Recent (indexed past meetings)
│
├── /meetings/:id (Meeting Detail)
│   ├── Summary (hero, always visible)
│   ├── Brief link (only if Brief exists)
│   ├── Commitments extracted
│   ├── Topics discussed → links to /search?q=[topic]
│   ├── Connections detected
│   └── Transcript (collapsible)
│
├── /meetings/:id/brief (Pre-Meeting Brief)
│   ├── Last session summary
│   ├── Relevant commitments
│   ├── Relevant connections
│   ├── Suggested agenda
│   └── Share control
│
├── /brief/:shareId (Shared Brief — PUBLIC, no auth)
│   ├── Sharer name + meeting title
│   ├── Last session summary
│   ├── Open threads
│   └── Farz attribution + signup CTA
│
├── /commitments (Commitments)
│   ├── Open (sorted by due date)
│   └── Resolved (this month)
│
└── /insights (Insights)
    ├── Top topics (bar chart by mention count)
    ├── Topic trends (rising / stable / falling)
    ├── Commitment completion rate
    ├── Meeting load (this week vs. avg)
    └── Cross-group topics (internal ↔ external)
```

---

## 4. Screens & Wireframes

### Screen 0 — Onboarding / First Login

**Trigger:** User has 0 meetings indexed. Shown once; redirect to Dashboard after import completes or user skips.

**Backend dependency:** Endpoint to enumerate available Google Meet recordings + bulk import endpoint.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   ■ FARZ                                                                 │
│                                                                          │
│   Welcome, Layla.                                                        │
│   Farz is your personal intelligence layer for meetings.                 │
│                                                                          │
│   ┌─── IMPORT YOUR HISTORY ───────────────────────────────────────────┐ │
│   │                                                                    │ │
│   │   We found 23 Google Meet recordings from the past 60 days.       │ │
│   │   Import them to get started with your full meeting history.      │ │
│   │                                                                    │ │
│   │   [Import 23 meetings →]    [Start fresh — future meetings only]  │ │
│   │                                                                    │ │
│   │   Your data stays private. No one else can access your meetings.  │ │
│   └────────────────────────────────────────────────────────────────── ┘ │
│                                                                          │
│   What Farz will do:                                                     │
│   ● Summarize every meeting automatically                                │
│   ● Track your commitments across meetings                               │
│   ● Generate pre-meeting briefings for recurring meetings                │
│   ● Surface connections across conversations                             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**States:**
- Import in progress: show progress bar with live count ("Indexing meeting 7 of 23...")
- Import complete: auto-redirect to Dashboard

---

### Screen 1 — Dashboard (Day 1 State)

**Shown when:** User has indexed meetings but no Briefs have been generated yet (no recurring meeting with 2+ sessions).

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  Good morning, Layla.  Monday, March 9                   │
│  ■ FARZ      │                                                          │
│              │  ┌─── TODAY'S MEETINGS ──────────────────────────────┐  │
│  ● Dashboard │  │  ▶ 09:00  Product Standup                         │  │
│  ○ Search    │  │          Recurring · Building context...           │  │
│  ○ Meetings  │  │          [View meeting →]                          │  │
│  ○ Commits   │  │                                                    │  │
│  ○ Insights  │  │  ▶ 11:30  Design Review                           │  │
│              │  │          First indexed session today               │  │
│  ──────────  │  │          [View meeting →]                          │  │
│  [Layla ▾]   │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── OPEN COMMITMENTS ──────────────────────────────┐  │
│              │  │  ● "Send wireframes to the team"    DUE TODAY      │  │
│              │  │    Product Review · Mar 6           [View →]      │  │
│              │  │  ● "Follow up with Acme on pricing"  Due Mar 10   │  │
│              │  │    Sales Call · Mar 4               [View →]      │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── FARZ IS BUILDING YOUR INDEX ───────────────────┐  │
│              │  │  23 meetings indexed · Topics forming              │  │
│              │  │  ████████████░░░░░░░░                              │  │
│              │  │  Pre-meeting Briefs appear after 2 sessions of     │  │
│              │  │  any recurring meeting.                            │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── RECENT ACTIVITY ───────────────────────────────┐  │
│              │  │  Mar 8 · All Hands indexed · 2 topics extracted    │  │
│              │  │  Mar 7 · Engineering Sync indexed · 4 topics       │  │
│              │  │  Mar 6 · Product Review indexed · 2 commits found  │  │
│              │  └────────────────────────────────────────────────── ┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Data required from backend:**
- `GET /calendar/today` — today's upcoming meetings from Google Calendar
- `GET /commitments?status=open&limit=3&sort=due_date` — urgent open commitments
- `GET /index/stats` — total meetings indexed, topics forming count
- `GET /activity?limit=5` — recent indexing events

---

### Screen 1b — Dashboard (Week 2+ State)

**Shown when:** At least one Brief exists and/or at least one Connection has been flagged.

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  Good morning, Layla.  Monday, March 9                   │
│  ■ FARZ      │                                                          │
│              │  ┌─── TODAY'S MEETINGS ──────────────────────────────┐  │
│  ● Dashboard │  │  ▶ 09:00  Product Standup      [Brief ready ✦]   │  │
│  ○ Search    │  │          Recurring · 8 sessions indexed            │  │
│  ○ Meetings  │  │          Last: Q1 review, reporting delay          │  │
│  ○ Commits   │  │                             [Open Brief →]        │  │
│  ○ Insights  │  │                                                    │  │
│              │  │  ▶ 11:30  Design Review                           │  │
│  ──────────  │  │          First session with this group             │  │
│  [Layla ▾]   │  │          Calendar note: 3 agenda items listed      │  │
│              │  │                    [No brief — first session]     │  │
│              │  │                                                    │  │
│              │  │  ○ 14:00  1:1 with Dana        [Generating...]   │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── OPEN COMMITMENTS ──────────────────────────────┐  │
│              │  │  ● "Send wireframes to the team"    DUE TODAY      │  │
│              │  │    Product Review · Mar 6           [View →]      │  │
│              │  │  ● "Follow up with Acme on pricing"  Due Mar 10   │  │
│              │  │    Sales Call · Mar 4               [View →]      │  │
│              │  │                                   [See all 4 →]  │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── NEW CONNECTIONS ───────────────────────────────┐  │
│              │  │  ✦ "Reporting Feature"                             │  │
│              │  │    Sales Call (Mar 4) ↔ Engineering Sync (Mar 7)  │  │
│              │  │    Customer request aligns with backlog item       │  │
│              │  │                                    [Explore →]   │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── RECENT ACTIVITY ───────────────────────────────┐  │
│              │  │  Mar 8 · All Hands · 2 topics · 0 commits          │  │
│              │  │  Mar 7 · Engineering Sync · 4 topics · 2 commits   │  │
│              │  │  Mar 6 · Product Review · 5 topics · 2 commits     │  │
│              │  └────────────────────────────────────────────────── ┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Layout rationale:**
- Meetings first — primary morning anxiety: "what's happening today?"
- `✦ Brief ready` badge is the primary CTA — forms the pre-meeting prep habit
- Commitments second — time-sensitive, personal accountability
- Connections third — passive awareness, not urgent
- Activity feed last — historical, low priority

**Data required from backend:**
- `GET /calendar/today` — with Brief status per meeting (`ready` / `generating` / `unavailable`)
- `GET /commitments?status=open&limit=3&sort=due_date`
- `GET /connections?seen=false&limit=3` — unseen Connections
- `GET /activity?limit=5`

---

### Screen 2 — Search (Landing / Topic Directory)

**Route:** `/search` (no query)

The Search page is never a blank screen. Before the user types anything, it shows the full Topic directory — everything Farz has identified across their indexed meetings, organized by what is most immediately useful. This serves two purposes: discovery ("what can I search for?") and direct navigation (clicking a Topic goes straight to its Arc, no typing needed).

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │                                                          │
│  ■ FARZ      │  ┌──────────────────────────────────────────────────┐  │
│              │  │ 🔍  Search your conversations...                  │  │
│  ○ Dashboard │  └──────────────────────────────────────────────────┘  │
│  ● Search    │                                                          │
│  ○ Meetings  │  ─── OPEN TOPICS ──────────────────────────────────── │
│  ○ Commits   │  Topics with no resolution yet — likely still active   │
│  ○ Insights  │                                                          │
│              │  ┌───────────────────────────────────────────────────┐  │
│  ──────────  │  │  ⬤ Reporting Feature    8 meetings · Last: Mar 7  │  │
│  [Layla ▾]   │  │    No decision reached · Status: Open             │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ⬤ Infra Cost Estimate  5 meetings · Last: Mar 8  │  │
│              │  │    Pending estimate from Jake · Status: Open       │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ⬤ Vendor Contract      6 meetings · Last: Mar 5  │  │
│              │  │    Renewal terms unresolved · Status: Open         │  │
│              │  └───────────────────────────────────────────────────┘  │
│              │                                                          │
│              │  ─── RECENT TOPICS ────────────────────────────────── │
│              │  Discussed in the last 7 days                          │
│              │                                                          │
│              │  ┌───────────────────────────────────────────────────┐  │
│              │  │  ⬤ Q2 Roadmap          14 meetings · Last: Mar 8  │  │
│              │  │    Prioritization in progress                      │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ⬤ Reporting Feature    8 meetings · Last: Mar 7  │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ⬤ All Hands Agenda     2 meetings · Last: Mar 8  │  │
│              │  └───────────────────────────────────────────────────┘  │
│              │                                                          │
│              │  ─── ALL TOPICS ───────────────────────── [A–Z ▾]──  │
│              │                                                          │
│              │  ┌───────────────────────────────────────────────────┐  │
│              │  │  Design System          4 meetings · Last: Mar 3   │  │
│              │  │  Infra Cost Estimate    5 meetings · Last: Mar 8   │  │
│              │  │  Q1 Sprint Review       3 meetings · Last: Mar 6   │  │
│              │  │  Q2 Roadmap            14 meetings · Last: Mar 8   │  │
│              │  │  Reporting Feature      8 meetings · Last: Mar 7   │  │
│              │  │  Vendor Contract        6 meetings · Last: Mar 5   │  │
│              │  │                               [Show all 18 →]     │  │
│              │  └───────────────────────────────────────────────────┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Layout rationale:**
- Open Topics first — these are the most actionable: no decision reached, likely still live
- Recent Topics second — what's top of mind right now (last 7 days)
- All Topics last — the full directory, sorted by most recent mention, with A–Z toggle
- Topics appear in both Open and Recent when applicable (Reporting Feature appears in both above — that's correct)
- A Topic that is `resolved` does not appear in Open Topics, but remains in Recent and All Topics

**Interaction:** Clicking any Topic card navigates to `/search?q=[topic.label]` and renders the Topic Arc immediately — no additional typing required.

**Empty state (0 meetings indexed):**
> "Your Topic directory will appear here once Farz has indexed some meetings. [Go to Meetings →] to see what's been captured."

**Data required from backend:**
- `GET /topics?status=open&sort=last_mentioned&limit=10` — Open Topics section
- `GET /topics?mentioned_after=[7_days_ago]&sort=last_mentioned&limit=5` — Recent Topics section
- `GET /topics?sort=label&limit=20` — All Topics section (paginated)
- Each Topic must include: `label`, `conversation_count`, `last_mentioned_at`, `status`, `status_note`

---

### Screen 2b — Search → Topic Arc (Result State)

**Route:** `/search?q=reporting+feature`

Reached by: (a) typing a query in the search box, or (b) clicking any Topic card on the landing page. Both entry points produce the same Arc result. The search box remains visible at the top so the user can refine or search for something else.

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │                                                          │
│  ■ FARZ      │  ┌──────────────────────────────────────────────────┐  │
│              │  │ 🔍  reporting feature                         [×] │  │
│  ○ Dashboard │  └──────────────────────────────────────────────────┘  │
│  ● Search    │  ← All topics                                           │
│  ○ Meetings  │                                                          │
│  ○ Commits   │  TOPIC ARC: "Reporting Feature"                         │
│  ○ Insights  │  8 conversations  ·  Feb 14 – Mar 8  ·  Status: Open   │
│              │                                                          │
│  ──────────  │  Feb 14 ●────────●────────●────────● Mar 8             │
│  [Layla ▾]   │           intro     scope    backlog   latest           │
│              │                                                          │
│              │  ┌────────────────────────────────────────────────────┐ │
│              │  │ ● Feb 14 · Sales Call with Acme Corp               │ │
│              │  │   Acme requested custom reporting for finance.      │ │
│              │  │   No scope commitment made. Noted as interest.      │ │
│              │  │                      → 00:14:32  [Jump to clip]   │ │
│              │  ├────────────────────────────────────────────────────┤ │
│              │  │ ● Feb 21 · Product Review                          │ │
│              │  │   Feasibility discussed. Jake flagged 3–4 week      │ │
│              │  │   pipeline effort. No timeline committed.           │ │
│              │  │                      → 00:31:07  [Jump to clip]   │ │
│              │  ├────────────────────────────────────────────────────┤ │
│              │  │ ● Mar 7 · Engineering Sync                         │ │
│              │  │   Added to Q2 backlog. API access deferred to       │ │
│              │  │   Phase 2. Infra cost estimate still pending.       │ │
│              │  │                      → 00:08:45  [Jump to clip]   │ │
│              │  └────────────────────────────────────────────────────┘ │
│              │                                                          │
│              │  ⚠ Still open: No delivery date committed.              │
│              │    Last discussed: Mar 7 · Engineering Sync             │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**"← All topics" link** returns to `/search` (the landing page directory). Acts as breadcrumb.

**No-results state** (query matches no Topics or Conversations):
> "No conversations found for '[query]'. Try a broader term, or [browse all topics →]."

**Single-meeting result** (topic exists in only 1 Conversation — Arc cannot form):

```
│  FOUND IN 1 CONVERSATION: "Reporting Feature"                          │
│                                                                        │
│  ● Mar 7 · Engineering Sync                                           │
│    Reporting feature mentioned for the first time. No decision yet.   │
│                            → 00:08:45  [Jump to clip]                │
│                                                                        │
│  Farz will build a full Topic Arc once this subject appears in        │
│  more meetings.                                                        │
```

**Layout rationale:**
- Search box stays visible with the active query and a clear [×] — user can refine without going back
- "← All topics" breadcrumb maintains orientation — user knows they came from the directory
- Timeline bar is the visual anchor — communicates "this topic has a history"
- Each ArcPoint is a discrete cited claim — every synthesis statement has a source
- ArcPoints show synthesis, not transcript excerpts — synthesis is the product
- `status_note` at the bottom is the most actionable signal: resolved or still open?
- "Jump to clip" links to exact Conversation + transcript offset — the trust escape hatch

**Data required from backend:**
- `POST /search` `{ "query": "reporting feature" }` → returns `TopicArc` or `SingleConversationResult`
- Each ArcPoint must include: `conversation_id`, `conversation_title`, `occurred_at`, `summary`, `transcript_offset_seconds`
- If query matches a known Topic by label, backend may return the Arc directly without LLM synthesis (it is already computed)

---

### Screen 3 — Pre-Meeting Brief

**Route:** `/meetings/:id/brief`
**Access points:** Dashboard "Open Brief →" button · Meeting Detail "View Brief" link
**Availability:** Only for recurring meetings with ≥ 1 prior indexed session

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  ← Back                                                  │
│  ■ FARZ      │  Brief: Product Standup                   [Share ↗]    │
│              │  Today 09:00  ·  Recurring  ·  8 sessions indexed       │
│  ○ Dashboard │  ────────────────────────────────────────────────────── │
│  ○ Search    │                                                          │
│  ● Meetings  │  ┌─── LAST SESSION (Mar 6) ──────────────────────────┐  │
│  ○ Commits   │  │  Reviewed Q1 sprint. Decision: reporting feature    │  │
│  ○ Insights  │  │  delayed to Q2 due to infra costs. Two action       │  │
│              │  │  items assigned.                                     │  │
│  ──────────  │  └────────────────────────────────────────────────── ┘  │
│  [Layla ▾]   │                                                          │
│              │  ┌─── YOUR COMMITMENTS FOR THIS MEETING ─────────────┐  │
│              │  │  ● "Send wireframes to the team"                   │  │
│              │  │    Due today · Source: Product Review, Mar 6       │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── RELEVANT CONNECTIONS ──────────────────────────┐  │
│              │  │  ✦ Acme reporting request (Sales Call, Mar 4)      │  │
│              │  │    aligns with backlog item from last session       │  │
│              │  │                                  [View Arc →]     │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── SUGGESTED AGENDA ──────────────────────────────┐  │
│              │  │  1.  Infra cost estimate — open since Mar 6        │  │
│              │  │  2.  Wireframe review (your commitment due today)  │  │
│              │  │  3.  Q2 roadmap priority order                     │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ─────────────────────────────────────────────────────  │
│              │  [Share this Brief with attendees]                      │
│              │  Read-only · Includes your name and Farz attribution    │
│              │  Revocable at any time · [Preview what they'll see →]  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Section order rationale:**
1. Last session summary — the memory replacement; #1 thing the user needs
2. Commitments — time-sensitive, personal accountability, often overdue
3. Connections — context enrichment; not always present
4. Suggested agenda — derived from open threads; a bonus, not a core requirement
5. Share section — prominent but separate; privacy controls explicit before action

**Share behavior:**
- Generating a share token creates a public `GET /brief/:shareId` endpoint
- Shared view is read-only
- Revoking the share invalidates the token — existing links stop working
- "Preview" shows the user exactly what recipients will see before they share

**Data required from backend:**
- `GET /meetings/:id/brief` → returns `Brief` object
- `POST /meetings/:id/brief/share` → returns `{ shareId, shareUrl }`
- `DELETE /meetings/:id/brief/share` → revokes token

---

### Screen 4 — Meetings Library

**Route:** `/meetings`

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  Meetings                           [Filter ▾]          │
│  ■ FARZ      │                                                          │
│              │  UPCOMING TODAY                                          │
│  ○ Dashboard │  ┌───────────────────────────────────────────────────┐  │
│  ○ Search    │  │  ▶ 09:00  Product Standup       [Brief ready ✦]  │  │
│  ● Meetings  │  │  ▶ 11:30  Design Review         [Brief ready ✦]  │  │
│  ○ Commits   │  │  ○ 14:00  1:1 with Dana         [Generating...]  │  │
│  ○ Insights  │  └───────────────────────────────────────────────────┘  │
│              │                                                          │
│  ──────────  │  RECENT                                                  │
│  [Layla ▾]   │  ┌───────────────────────────────────────────────────┐  │
│              │  │  Mar 8 · All Hands          2 topics · 0 commits  │  │
│              │  │  Mar 7 · Engineering Sync   4 topics · 2 commits  │  │
│              │  │  Mar 6 · Product Review     5 topics · 2 commits  │  │
│              │  │  Mar 5 · Sales Call – Acme  3 topics · 0 commits  │  │
│              │  │  Mar 4 · All Hands          2 topics · 1 commit   │  │
│              │  │                                    [Load more]   │  │
│              │  └───────────────────────────────────────────────────┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Data required from backend:**
- `GET /calendar/today` — upcoming meetings with Brief status
- `GET /conversations?sort=started_at&order=desc&limit=20` — recent meetings with topic + commit counts

---

### Screen 5 — Meeting Detail

**Route:** `/meetings/:id`
**Day 1 ready:** Yes. Works from the first indexed meeting. No prior history required.

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  ← Meetings                                              │
│  ■ FARZ      │  Product Review  ·  Mar 6, 14:00  ·  45 min  ·  5 ppl  │
│              │  ─────────────────────────────────────────────────────  │
│  ○ Dashboard │                                                          │
│  ○ Search    │  ┌─── SUMMARY ───────────────────────────────────────┐  │
│  ● Meetings  │  │  Reviewed Q1 sprint results. Main decision:        │  │
│  ○ Commits   │  │  reporting feature delayed to Q2 (infra cost).     │  │
│  ○ Insights  │  │  Two commitments made. Open: infra cost estimate   │  │
│              │  │  from Jake, expected by March 8.                   │  │
│  ──────────  │  └────────────────────────────────────────────────── ┘  │
│  [Layla ▾]   │                                                          │
│              │  ┌─── BRIEF ─────────────────────────────────────────┐  │
│              │  │  [View the Brief generated before this meeting →]  │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │  (hidden if no Brief was generated for this meeting)     │
│              │                                                          │
│              │  ┌─── COMMITMENTS EXTRACTED ─────────────────────────┐  │
│              │  │  ● You: "Send wireframes by March 9"      [Open]  │  │
│              │  │  ● Jake: "Cost estimate by March 8"       [Open]  │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── TOPICS DISCUSSED ──────────────────────────────┐  │
│              │  │  ● Q1 Sprint Review          [View Arc →]         │  │
│              │  │  ● Reporting Feature         [View Arc →]         │  │
│              │  │  ● Q2 Roadmap                [View Arc →]         │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │  "View Arc →" links to /search?q=[topic.label]          │
│              │  If topic has only 1 conversation, show inline note     │
│              │  instead: "Arc forming — more sessions needed"          │
│              │                                                          │
│              │  ┌─── CONNECTIONS ───────────────────────────────────┐  │
│              │  │  ✦ Sales Call (Mar 4) — both discuss Acme's        │  │
│              │  │    reporting request          [View →]            │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │  (hidden if no Connections detected for this meeting)    │
│              │                                                          │
│              │  ┌─── TRANSCRIPT ────────────────────────────────────┐  │
│              │  │  [Show full transcript ▾]                          │  │
│              │  │                                                    │  │
│              │  │  Layla: "Should we push this to Q2?"               │  │
│              │  │  Jake:  "Given the infra cost, yes. I'll get you   │  │
│              │  │          a number by tomorrow."                    │  │
│              │  └────────────────────────────────────────────────── ┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Layout rationale:**
- Summary is the hero — LLM synthesis is the product; transcript is the evidence
- Summary always visible; transcript always collapsible (most users want synthesis, not raw text)
- Brief section: hidden when no Brief exists (first session or non-recurring meeting)
- Connections section: hidden when no Connections detected
- Topics "View Arc →": if Arc doesn't exist yet (topic appears in only 1 meeting), show an inline note instead of a broken link

**Data required from backend:**
- `GET /conversations/:id` → full `Conversation` object including `summary`, `topics`, `commitments`, `transcript`
- `GET /meetings/:id/brief/exists` → boolean, to conditionally render Brief link
- `GET /conversations/:id/connections` → Connections linked to this conversation

---

### Screen 6 — Commitments

**Route:** `/commitments`
**Day 1 ready:** Yes. Populated immediately from import.

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  My Commitments                                          │
│  ■ FARZ      │  4 open  ·  12 resolved this month                      │
│              │  ─────────────────────────────────────────────────────  │
│  ○ Dashboard │                                                          │
│  ○ Search    │  OPEN                                                    │
│  ○ Meetings  │  ┌───────────────────────────────────────────────────┐  │
│  ● Commits   │  │  ● "Send wireframes to the team"      DUE TODAY   │  │
│  ○ Insights  │  │    Product Review  ·  Mar 6           [View →]   │  │
│              │  ├───────────────────────────────────────────────────┤  │
│  ──────────  │  │  ● "Follow up with Acme on pricing"   Due Mar 10  │  │
│  [Layla ▾]   │  │    Sales Call  ·  Mar 4               [View →]   │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ● "Share roadmap draft with Marcus"  Due Mar 12  │  │
│              │  │    Stakeholder Review  ·  Mar 3       [View →]   │  │
│              │  ├───────────────────────────────────────────────────┤  │
│              │  │  ● "Review vendor proposal"           No date set  │  │
│              │  │    Vendor Review  ·  Feb 28           [View →]   │  │
│              │  └───────────────────────────────────────────────────┘  │
│              │                                                          │
│              │  RESOLVED  (this month)                                 │
│              │  ┌───────────────────────────────────────────────────┐  │
│              │  │  ✓ "Send Q1 summary to leadership"  Resolved Mar 7 │  │
│              │  │    All Hands  ·  Feb 22             [View →]     │  │
│              │  └───────────────────────────────────────────────────┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**"View →"** links to `/meetings/:conversation_id` (the source meeting).

**Data required from backend:**
- `GET /commitments?attributed_to=me&status=open&sort=due_date`
- `GET /commitments?attributed_to=me&status=resolved&resolved_after=[30_days_ago]`

---

### Screen 7 — Insights

**Route:** `/insights`
**Available when:** ≥ 10 meetings indexed. Show "building" placeholder below that threshold.

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │  Insights                      Last 30 days [▾]        │
│  ■ FARZ      │                                                          │
│              │  ┌─── TOP TOPICS ────────────────────────────────────┐  │
│  ○ Dashboard │  │  Q2 Roadmap           ██████████████  14 meetings  │  │
│  ○ Search    │  │  Reporting Feature    ████████          8 meetings  │  │
│  ○ Meetings  │  │  Vendor Contract      ██████            6 meetings  │  │
│  ○ Commits   │  │  Infra Cost           █████             5 meetings  │  │
│  ● Insights  │  │  Design System        ████              4 meetings  │  │
│              │  │                      [View Arc →]  on any topic   │  │
│  ──────────  │  └────────────────────────────────────────────────── ┘  │
│  [Layla ▾]   │                                                          │
│              │  ┌─── TOPIC TRENDS ──────────────────────────────────┐  │
│              │  │  ↑ Rising:  Vendor Contract   (+4 vs. prev period) │  │
│              │  │  ↑ Rising:  Infra Cost        (+3 vs. prev period) │  │
│              │  │  → Stable:  Q2 Roadmap                             │  │
│              │  │  ↓ Falling: Design System     (-2 vs. prev period) │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── COMMITMENT RATE ───────────────────────────────┐  │
│              │  │  Open: 4    Resolved: 12    Rate: 75%              │  │
│              │  │  ████████████████░░░░░░     Avg close time: 4 days │  │
│              │  │  ⚠ 1 commitment has no due date set                │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── MEETING LOAD ──────────────────────────────────┐  │
│              │  │  This week: 12 meetings    30-day avg: 9 / week    │  │
│              │  │  Recurring: 8  ·  Ad-hoc: 4                        │  │
│              │  └────────────────────────────────────────────────── ┘  │
│              │                                                          │
│              │  ┌─── CROSS-GROUP TOPICS ────────────────────────────┐  │
│              │  │  Topics that appear in both internal & external    │  │
│              │  │  meetings — likely needing deliberate alignment:   │  │
│              │  │  ● Reporting Feature  — 3 external · 5 internal   │  │
│              │  │  ● Vendor Contract    — 2 external · 4 internal   │  │
│              │  │  [View Arc →] on any row                          │  │
│              │  └────────────────────────────────────────────────── ┘  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**"Building" state (< 10 meetings):**
> "Insights appear after Farz has indexed 10 or more meetings. You have [N] so far. Keep going — your patterns are forming."

**Data required from backend:**
- `GET /insights/topics?period=30d` → topic frequency counts + trend direction
- `GET /insights/commitments?period=30d` → open/resolved counts, avg close time
- `GET /insights/meetings?period=30d` → load counts, recurring vs. ad-hoc
- `GET /insights/cross-group?period=30d` → topics by meeting participant type (internal/external)

---

### Screen 8 — Shared Brief (Public, No Auth)

**Route:** `/brief/:shareId`
**Auth:** None required. Token-gated public endpoint.

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   ■ FARZ                                       [Create your own →]  │
│   ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│   Pre-Meeting Brief                                                  │
│   Shared by Layla M.  ·  Product Standup  ·  Today, 09:00          │
│                                                                      │
│   ┌─── LAST SESSION SUMMARY ────────────────────────────────────┐   │
│   │  Q1 sprint reviewed. Main decision: reporting feature         │   │
│   │  delayed to Q2 due to infra costs.                            │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   ┌─── OPEN THREADS ────────────────────────────────────────────┐   │
│   │  1.  Infra cost estimate — pending since Mar 6               │   │
│   │  2.  Q2 roadmap priority order                               │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   ─────────────────────────────────────────────────────────────     │
│   Generated by Farz · Personal intelligence for meetings             │
│   This Brief was created from Layla's meeting history only.          │
│   Your data is not included.                                         │
│   [Get your own pre-meeting briefings →]                            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Privacy note rationale:** The recipient's first question is "did this AI read my meetings?" The explicit note — "This Brief was created from Layla's meeting history only. Your data is not included." — resolves that concern at the moment of viral contact. The product demo and the signup prompt share the same screen.

**Expired / revoked token:**
> "This Brief is no longer available. The link may have expired or been revoked by the sender."

**Data required from backend:**
- `GET /brief/shared/:shareId` → returns a read-only `SharedBrief` object (subset of `Brief`, no private data)
- Returns `404` or `410 Gone` when token is invalid or revoked

---

## 5. Progressive Enhancement

How key screens change as data accumulates:

| Screen | Day 1 (post-import) | Week 1–2 | Month 1+ |
|---|---|---|---|
| Dashboard | Calendar meetings, commitments from history, progress banner | First `✦ Brief ready`, first Connection card | Full — Briefs, Connections, rich commit list |
| Search | Single-meeting keyword results | Primitive Topic Arcs (2–5 points) | Rich Topic Arcs with timeline + status |
| Meeting Detail | Summary + Transcript + Commitments (no Brief, no Connections) | Brief link for recurring meetings | Full — Brief, Connections, Arc links |
| Commitments | Populated from import | Grows with every meeting | Full history |
| Insights | "Building" state | Light data | Full — trends, cross-group topics |

---

## 6. Conditional Rendering Rules

Frontend must apply these rules to avoid empty or misleading states:

| Condition | Rule |
|---|---|
| Meeting is first session of a series | Hide Brief section in Meeting Detail. Do not show "Brief ready" on Dashboard card. |
| Topic has only 1 Conversation | Replace "View Arc →" with: "Arc forming — search this topic as more meetings are indexed" |
| Connection has no `rationale` | Do not render the Connection. Log it internally for debugging. |
| `insights` API returns < 10 meeting threshold | Render "building" state instead of charts |
| Share token is revoked or expired | Render the expired-link page, not a 500 |
| Import in progress | Dashboard shows import progress banner instead of empty state |

---

## 7. Component Inventory

Reusable components frontend must build:

| Component | Used On | Props |
|---|---|---|
| `Sidebar` | All authenticated screens | `activeRoute`, `user` |
| `MeetingCard` | Dashboard, Meetings list | `meeting`, `briefStatus`, `lastSessionTeaser` |
| `CommitmentCard` | Dashboard, Commitments, Brief | `commitment`, `showSource` |
| `ConnectionCard` | Dashboard, Meeting Detail, Brief | `connection` (must include `rationale`) |
| `TopicArcTimeline` | Search results | `arc` (topic + arcPoints) |
| `ArcPoint` | TopicArcTimeline | `point` (summary, citation, transcriptOffset) |
| `ProgressBanner` | Dashboard (Day 1) | `indexedCount`, `totalImporting` |
| `BriefSharePanel` | Brief screen | `shareToken`, `onShare`, `onRevoke` |
| `TranscriptViewer` | Meeting Detail | `transcript` (speaker-attributed, timestamped) |

---

## 8. Tech Stack

- **Framework:** Next.js 15 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS — dark-only, no "AI purple"
- **Component library:** shadcn/ui — Card, Badge, Button, Input, Progress, Collapsible, Separator
- **Design principle:** Editorial, dark-only, minimal chrome. Feels like a professional intelligence tool, not a startup SaaS.

---

## 9. API Surface (Backend Contract)

Backend must expose the following endpoints. Phase tags indicate when each group is built.

### Auth & Onboarding — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/onboarding/available-recordings` | Count of importable past Meet recordings (Drive API) |
| `POST` | `/onboarding/import` | Trigger bulk retro-import |
| `GET` | `/onboarding/import/status` | Import progress (count indexed, total) |

### Conversations — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/conversations` | Paginated list with topic/commit counts |
| `GET` | `/conversations/:id` | Full conversation (summary, topics, commitments, transcript) |
| `GET` | `/conversations/:id/connections` | Connections linked to this conversation |

### Calendar — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/calendar/today` | Today's meetings with Brief status per meeting |

### Topics — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/topics` | All topics. Filterable by `status`, `mentioned_after`. Sortable by `label`, `last_mentioned`, `conversation_count`. |
| `GET` | `/topics/:id` | Single topic with metadata |

### Search
| Method | Path | Description |
|---|---|---|
| `POST` | `/search` | Query → `TopicArc` or `SingleConversationResult`. If query exactly matches a known Topic label, return precomputed Arc directly. |

### Commitments — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/commitments` | Paginated, filterable by status, attributed_to, due_date |
| `PATCH` | `/commitments/:id` | Update status (open → resolved) |

### Index Stats — Phase 1
| Method | Path | Description |
|---|---|---|
| `GET` | `/index/stats` | Total conversations, topics, commitments indexed |

### Briefs — Phase 2
| Method | Path | Description |
|---|---|---|
| `GET` | `/meetings/:id/brief` | Full Brief for a meeting |
| `GET` | `/meetings/:id/brief/exists` | Boolean — does a Brief exist? |
| `POST` | `/meetings/:id/brief/share` | Generate share token |
| `DELETE` | `/meetings/:id/brief/share` | Revoke share token |
| `GET` | `/brief/shared/:shareId` | Public endpoint — returns read-only SharedBrief |

### Connections — Phase 2
| Method | Path | Description |
|---|---|---|
| `GET` | `/connections` | Filterable by `seen=false` |
| `PATCH` | `/connections/:id/seen` | Mark as seen |

### Insights — Phase 2
| Method | Path | Description |
|---|---|---|
| `GET` | `/insights/topics` | Topic frequency + trend, filterable by period |
| `GET` | `/insights/commitments` | Completion stats, avg close time |
| `GET` | `/insights/meetings` | Load stats, recurring vs. ad-hoc |
| `GET` | `/insights/cross-group` | Topics spanning internal + external meetings |

---

## 10. Verification Checklist

Before any screen is considered complete:

### Frontend
- [ ] All 8 screens render without errors at 1280px, 1440px, 1920px
- [ ] Onboarding screen is shown to users with 0 indexed meetings
- [ ] Dashboard renders correctly in both Day 1 and Week 2+ states
- [ ] Brief is not accessible from primary nav — only from Dashboard card and Meeting Detail
- [ ] Search landing page (`/search`) shows Topic directory — never a blank screen
- [ ] Open Topics section shows only `status=open` topics
- [ ] Clicking any Topic card on landing page navigates to `/search?q=[topic.label]` and renders the Arc
- [ ] Search box retains query on Arc result page with visible [×] clear button
- [ ] "← All topics" breadcrumb on Arc result page returns to `/search`
- [ ] Single-conversation result shows inline note instead of Arc timeline
- [ ] Topic Arc timeline renders with all ArcPoints cited (meeting name + timestamp visible)
- [ ] Meeting Detail: Summary visible by default, Transcript collapsed by default
- [ ] Brief section hidden in Meeting Detail when no Brief exists
- [ ] Connections section hidden in Meeting Detail when no Connections exist
- [ ] "View Arc →" shows "forming" note when topic has only 1 conversation
- [ ] Insights shows "building" state when < 10 meetings indexed
- [ ] Shared Brief (`/brief/:shareId`) renders without authentication
- [ ] Shared Brief shows expired-link state when token is invalid or revoked
- [ ] Share CTA visible on Brief screen with privacy note beneath it

### Backend
- [ ] Commitment extraction runs on every newly indexed Conversation
- [ ] Brief generation job runs ~10–15 minutes before each scheduled recurring meeting
- [ ] Brief is never generated for a first session of a meeting series
- [ ] Connection must have a non-empty `rationale` field — validated at write time
- [ ] Topic Arc is computed dynamically on search query, not stored
- [ ] `/brief/shared/:shareId` returns 410 Gone when token is revoked
- [ ] All user data is strictly isolated per user at the data layer
- [ ] No LLM provider call stores or logs conversation data (no-training policy enforced for internal MVP; formal DPA with all providers required before external user onboarding)
