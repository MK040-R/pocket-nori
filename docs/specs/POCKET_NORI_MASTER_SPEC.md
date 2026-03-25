# Pocket Nori Master Spec

**Status:** Canonical zero-context handoff document  
**Date:** 2026-03-24  
**Audience:** Senior engineer joining cold, staff engineer reviewing architecture, future AI coding agents  
**Scope:** Business context + product spec + implementation architecture + operating rules  
**Active product direction:** Desktop-first full product, Mac-only v1, Windows later

---

## 1. Title + Usage

This is the first document to hand to a developer with no prior Pocket Nori context.

It is the canonical onboarding and execution handoff for the project. It consolidates:

- business context and product intent
- active product direction
- current repo reality
- system architecture
- ingestion and worker flows
- topic intelligence pipeline
- deployment and operating model
- engineering rules and acceptance criteria

The rest of the documentation suite still exists and remains useful for provenance, maintenance, and historical detail. This file is intentionally self-sufficient: a developer should be able to read only this file and understand what Pocket Nori is, what is built today, what the target product is, and how to build toward it.

### How to read this document

| Label | Meaning |
|---|---|
| `Implemented today` | Present in the current repository or current deployment model |
| `Target behavior` | The intended active product direction this spec wants implemented |
| `Deferred` | Intentionally not in the first Mac release |

### Document posture

- This file is a `handoff layer`, not a lightweight summary.
- It resolves major cross-document ambiguity into one active story.
- When underlying source docs disagree, this file chooses one active decision and explains why.

---

## 2. Executive Summary

Pocket Nori is a personal intelligence layer for working professionals who spend their days in meetings and lose time reconstructing what was discussed, decided, promised, and connected across conversations. It does not try to become a bot, task manager, or team surveillance tool. It is a private, user-owned memory system that captures meetings, structures them into durable knowledge, and surfaces that knowledge before the next relevant conversation.

The current repository already contains a substantial FastAPI backend, a deployed web app, Google auth, calendar sync, briefs, commitments, search, dashboard surfaces, and a finalized topic intelligence specification. The missing product leap is not "build Pocket Nori from scratch." The missing leap is "shift ingestion and day-to-day product framing from web-first transcript import to desktop-first meeting capture."

### Product in one sentence

Pocket Nori captures your meetings through a desktop app, turns them into structured memory, and gives you cited answers, cross-meeting context, and pre-meeting preparation without requiring a bot in the call.

### Core user

| Attribute | Definition |
|---|---|
| Primary user | PMs, founders, team leads, operators, client-facing managers |
| Daily pain | Context switching, repeated meetings, hidden commitments, losing track of what changed |
| Desired outcome | Enter each meeting with the right context and recall decisions instantly without re-reading notes |
| Trust requirement | The product must feel private, personal, and verifiable |

### Active product direction

| Area | Decision |
|---|---|
| Product center | Desktop-first full product |
| v1 platform | macOS only |
| Future platform | Windows later |
| Capture model | Desktop app, not bot |
| Audio scope | Source-agnostic Mac audio capture for meetings happening on the Mac |
| Calendar provider | Google Calendar only in v1 |
| Notification rule | Native prompt 1 minute before scheduled meeting start |
| Read surfaces | Desktop app is primary product shell; existing web UI and shared React surfaces are reused where practical |
| Canonical topic model | `TopicNode` plus the 5-stage topic intelligence pipeline |

### Current repo reality

| Area | Current reality |
|---|---|
| Backend | FastAPI app with auth, onboarding, conversations, topics, commitments, search, briefs, home, chat, admin routes |
| Workers | Combined Celery worker handles ingest, extraction, embeddings, calendar sync, brief scheduling |
| Deployment | Backend on Render, frontend on Vercel, data on Supabase, broker on Upstash Redis |
| Ingestion today | Google Meet transcript/Drive import path is implemented; live desktop capture is not |
| Product maturity | Web product phases are complete; topic intelligence spec is finalized; desktop-first product is not yet implemented |

### What success looks like

1. A user installs the Mac app, signs in with Google, and grants calendar, microphone, and system-audio permissions.
2. One minute before a calendar meeting, Pocket Nori sends a native notification to start capture.
3. The app captures system audio plus mic, streams to the backend, and persists transcript segments with citations.
4. Within about a minute of meeting end, the conversation is searchable and feeds commitments, connections, topics, and briefs.
5. The user can ask "What did we decide about X?" and get a cited answer grounded in prior meetings.

---

## 3. Business Context

### Problem statement

Knowledge workers spend large portions of their day in meetings, but the resulting knowledge is fragmented:

- decisions live in scattered transcripts, chat messages, memory, and follow-ups
- commitments are made verbally and then forgotten
- related discussions happen in separate meetings with different groups
- before the next meeting, the user has to reconstruct context manually

The problem is not lack of transcription. The problem is lack of a personal intelligence layer that remembers, organizes, and retrieves the meaning of meetings over time.

### Cost of the problem

| Cost type | Effect |
|---|---|
| Cognitive load | Users repeatedly reconstruct context from scratch |
| Execution risk | Promises and open threads are missed |
| Meeting inefficiency | The first part of many meetings is spent re-establishing context |
| Decision quality | Users make decisions without remembering prior discussions |
| Personal bottleneck | Senior ICs and managers become context chokepoints |

### Target user

Pocket Nori is for individual professionals, not for centralized workspace admins.

| Segment | Why Pocket Nori matters |
|---|---|
| PMs and product leads | Need durable memory across roadmap, customer, and engineering meetings |
| Founders | Need cross-functional recall across hiring, product, customers, and investors |
| Team leads | Need continuity across recurring operational meetings |
| Operators and client-facing roles | Need to connect related threads across stakeholder groups |

### What Pocket Nori is

- a personal meeting memory layer
- a cited search and retrieval system across conversations
- a pre-meeting preparation system
- a cross-meeting intelligence system that links related discussions
- a private workspace owned by the individual user

### What Pocket Nori is not

- not a meeting bot
- not a generic note-taking app
- not a task management tool
- not a manager oversight tool
- not a shared team knowledge base by default

### Why a personal intelligence layer is different

| Product type | Primary object | User burden | Why Pocket Nori is different |
|---|---|---|
| Note-taking tool | User-authored note | User must write and organize | Pocket Nori derives structure automatically from meetings |
| Task tool | Task / project item | User must formalize actions | Pocket Nori extracts commitments from actual conversation |
| Transcription tool | Recording / transcript | User must interpret transcript | Pocket Nori synthesizes meaning across time |
| Bot meeting assistant | Bot-attended meeting record | Social and admin friction | Pocket Nori captures privately through the user's app |

### Product principles

1. **Private by default.** The user's intelligence layer belongs to the user alone.
2. **No bot.** Meeting capture happens through the user's app, not through a visible participant.
3. **Traceable outputs.** Every meaningful generated claim must be tied back to a source conversation or transcript segment.
4. **Derived, not curated.** Topics, commitments, and connections are system-extracted, not manually created.
5. **Cross-meeting value over single-meeting novelty.** The moat is memory and connection, not transcript formatting.

### Business success criteria

| Metric | Definition |
|---|---|
| Time-to-first-value | User gets useful context within the first few meetings |
| Habit formation | Pocket Nori becomes part of the pre-meeting ritual |
| Retrieval quality | Users trust answers to "what did we decide?" |
| Cross-meeting value | Connections and briefs surface genuinely relevant context |
| Trust | Users believe the product is private and auditable |

---

## 4. Product Direction

### Active vision

Pocket Nori is a desktop-first product. The desktop app is the primary runtime for capture, scheduling, notifications, settings, and day-to-day usage. The current web application remains part of the product and its React surfaces should be reused where practical, but the web app is not the primary capture entry point.

### Directional decisions

| Decision | Active choice | Rationale |
|---|---|---|
| Capture mechanism | App-based capture | Avoids visible bot presence, admin approval friction, and awkward social signaling |
| Platform scope | Mac-only v1 | Smallest viable desktop surface with the highest chance of a coherent first release |
| Future portability | Windows later | Keep architecture portable but do not require day-one Windows delivery |
| UI strategy | Electron shell plus reused web/shared React UI | Faster delivery than a full desktop-only rewrite, while still allowing true desktop integration |
| Audio scope | Source-agnostic Mac capture | Product value should not depend on a single meeting vendor |
| Calendar vendor | Google Calendar only | Matches current auth/calendar integration and reduces first-release surface area |
| Notification timing | 1 minute before start | Timely enough to feel helpful without nagging |
| Topic storage | `TopicNode` | The old cluster terminology no longer reflects the final extraction model |

### v1 scope

| In scope for first Mac release | Notes |
|---|---|
| Mac desktop app | Menu bar app plus main window |
| Google sign-in | Existing auth stack adapted for desktop session flow |
| Google Calendar sync | Meeting timing, titles, attendees, recurring-series metadata |
| 1-minute native notification | Start prompt for scheduled meetings |
| Manual ad-hoc capture fallback | User can start a capture without calendar context |
| Live audio capture | System audio plus microphone |
| Backend streaming ingest | Real-time transcription and post-meeting finalization |
| Existing read surfaces | Dashboard, search, meetings, commitments, briefs, insights using reused/shared React surfaces |
| Topic intelligence pipeline | 5-stage pipeline with `TopicNode` canonical storage |

### Non-goals for v1

| Deferred / out of scope | Why |
|---|---|
| Meeting bot fallback | Contradicts the product posture and expands the first release too much |
| Non-Google calendar providers | Keep auth and scheduling simple for the first release |
| Mobile apps | Not required to prove the desktop-first workflow |
| Full native desktop UI rewrite | Not needed to validate the product |
| Silent automatic capture without user action | Higher privacy and UX risk than a prompted start |
| Cross-device ambient recording | The product only captures meetings happening on the Mac in v1 |

### Conflict resolution adopted by this spec

| Topic | Historical conflict | Active decision |
|---|---|---|
| Product center | Existing repo is web-first; later-stage docs are desktop-first | Desktop-first is the active product direction |
| Meeting ingestion | Web import exists; desktop capture does not | Desktop capture becomes the primary path; web import remains legacy/backfill support |
| Topic model | Older docs and code reference `topic_clusters` | `TopicNode` is canonical; old cluster language is legacy/backcompat only |
| Read surface | Web app is currently the main user-facing product | Existing web React surfaces are reused inside the desktop product where practical |

---

## 5. Current State vs Target State

| Area | Implemented today | Target state | What is missing |
|---|---|---|---|
| Frontend | Next.js 15 web app with dashboard, onboarding, meetings, topics, search, commitments, briefs, chat, insights-like surfaces | Electron-hosted desktop product using shared React UI for core read surfaces | Desktop shell, packaging, navigation ownership, desktop settings and runtime integration |
| Backend API | FastAPI routes for auth, onboarding, conversations, search, briefs, topics, commitments, entities, calendar, home, chat, admin | Backend remains authoritative API plus adds desktop auth/session and live capture interfaces | Desktop auth contract, capture-session APIs, streaming ingest endpoint |
| Ingestion | Google transcript/Drive import path exists | Desktop live audio capture is the primary ingest path; legacy import remains for backfill/migration | Live capture finalization path, capture-session persistence, streaming transcript handling |
| Workers | Celery worker supports ingest import, extraction, embeddings, calendar sync, recurring briefs | Same worker model extended for live capture finalization and topic backfill | New live-capture finalize task and explicit reprocessing pathway aligned to TopicNode |
| Desktop app | Archived Electron spike only | Shippable Mac menu bar app plus desktop shell | App implementation, code signing, notifications, permissions, session storage |
| Topic pipeline | Definitive March 24 2026 pipeline spec exists; repo still contains legacy cluster references and transitional code | All topic extraction and read models align to the 5-stage TopicNode pipeline | Pipeline implementation completion, storage alignment, backfill, legacy terminology cleanup |
| Calendar | Google Calendar sync, event linking, and recurring brief scheduling exist | Desktop app uses Google Calendar for notification timing, meeting metadata, and recurring-brief context | Desktop-facing upcoming-meetings contract and capture-session association flow |
| Deployment | Backend on Render, frontend on Vercel, data on Supabase, broker on Upstash | Same cloud backend plus distributed signed desktop app | Desktop distribution, update mechanism, desktop observability |
| Testing | Strong Python unit/integration tests, frontend lint/build, limited live desktop validation | End-to-end desktop capture QA plus backend tests plus shared UI validation | Desktop test strategy, audio-path QA, notification/start-stop behavior tests |

---

## 6. Core Product Surfaces

| Surface | Purpose | Primary user actions | Data dependencies | Core states | Empty / error behavior |
|---|---|---|---|---|---|
| Onboarding | Get the user signed in, connected to Google, and ready for capture | Sign in, grant permissions, connect calendar, review intro, import historical meetings if enabled | Google OAuth, calendar access, desktop permission checks, optional legacy import status | first run, auth pending, calendar connected, permissions incomplete, ready | If permissions are missing, the surface must show explicit system-level remediation steps |
| Desktop menu bar app | Persistent runtime anchor for the product | Open app, view next meeting, start capture, stop capture, open settings, open dashboard | Desktop session, upcoming meetings, capture-session state | idle, scheduled, prompt pending, recording, finishing, error | If backend unavailable, allow local state inspection and explicit retry; do not silently discard captures |
| Capture prompt / notification flow | Start scheduled meeting capture at the right time | Click "Start Pocket Nori", snooze is not supported in v1, ignore notification, open meeting | Upcoming meetings feed, OS notifications, capture permissions | 1-minute notification, prompt expired, already recording | If notification ignored, user can still start from menu bar after the meeting start time |
| Dashboard | Daily home surface for upcoming meetings, recent activity, open commitments, and connections | Open next meeting context, drill into brief, review recent activity, review connections | Calendar feed, commitments, recent activity, recent connections, home summary | loaded, sparse, rich, session expired | On empty data, explain what appears after the first captured meetings; do not show dead widgets |
| Search | Ask what was discussed or browse topics over time | Search by natural language, open topic, open meeting, ask follow-up question | Topics, embeddings, transcript citations, conversations | empty query, results, no results, ask/search failure | No-result state must explain whether the issue is no indexed data vs. no match |
| Meetings library | Browse all conversations and access details | Filter, open meeting, inspect topics/briefs/actions | Conversations list, topic labels, brief metadata | populated, empty, loading, session expired | Empty state should guide the user back to capture/onboarding |
| Meeting detail | Read one conversation in depth | Review summary, transcript, commitments, topics, connections, latest brief | Conversation, transcript segments, actions, topics, brief links, connections | summary, transcript, actions, connections, loading | Missing data should degrade gracefully; the transcript and raw facts remain visible |
| Commitments | Track open and resolved commitments across meetings | Filter by assignee/status, resolve item, open source meeting | Commitments, linked meeting metadata, topic labels | open list, resolved list, empty, loading | Empty state should explain that commitments appear automatically after captured meetings |
| Briefs | Prepare for upcoming recurring meetings | Open brief, review context, share brief, inspect citations | Calendar metadata, topic arcs, commitments, connections, citation segments | eligible brief, no prior history, generated, generation pending, generation failed | If ineligible, explain why; first-time or non-recurring meetings do not auto-generate a brief in v1 |
| Insights | Show patterns and trends across meetings | Review topic trends, commitment behavior, meeting distribution | Topic summaries, connection counts, commitment metrics, dashboard aggregates | low-data, meaningful-data, loading | In low-data mode, explain that insights become meaningful after enough meetings are indexed |
| Sharing | Let the user deliberately share derived context | Share brief, revoke share, copy share link | Brief share token, revocation state | private, shared, revoked | Sharing must be opt-in and reversible; nothing is shared by default |

### Surface-specific behavioral notes

#### Onboarding

- The desktop app is the main onboarding runtime.
- The product should verify:
  - Google sign-in completed
  - Google Calendar access granted
  - microphone permission granted
  - screen/system-audio permission granted
- Historical import is allowed as a backfill utility, but is not the core onboarding message.

#### Desktop menu bar app

- This is the persistent control center.
- It should show:
  - next calendar meeting
  - current capture state
  - quick start for ad-hoc capture
  - link to full product window
  - settings and account actions

#### Dashboard

- The dashboard is still the default home surface, but in the desktop-first product it opens inside the desktop shell rather than being only a browser destination.

#### Search

- Search is the main "ask Pocket Nori" surface.
- Search must always preserve citations and source drill-down.

---

## 7. Canonical Object Model

### Canonical storage note

`TopicNode` is the canonical stored representation for topics.

The historical `topic_clusters` language reflects a prior intermediate design and should be treated as legacy/backcompat terminology only. Any new work should model topics as `TopicNode` entities with accumulated aliases, entities, keywords, and graph relationships.

### Index

The Index is the user's private knowledge boundary. Every user-owned entity belongs to exactly one Index.

| Field | Type | Notes |
|---|---|---|
| `user_id` | UUID | Privacy boundary and ownership key |
| `conversation_ids` | UUID[] | All conversations owned by the user |
| `topic_node_ids` | UUID[] | All canonical topics owned by the user |
| `connection_ids` | UUID[] | All stored cross-meeting connections |
| `brief_ids` | UUID[] | All generated briefs |

### Conversation

The atomic captured interaction.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Canonical conversation ID |
| `user_id` | UUID | Ownership |
| `source_platform` | string | `desktop_capture`, `google_meet_transcript_import`, or future source values |
| `title` | string | Meeting title or generated fallback |
| `meeting_date` | ISO datetime | Start time |
| `duration_seconds` | int | Actual or inferred duration |
| `participants` | string[] | User-visible participants from calendar and/or transcript |
| `calendar_event_id` | string or null | Linked Google Calendar event |
| `recurring_series_id` | string or null | Calendar recurring event key when available |
| `summary` | string | Generated meeting summary |
| `status` | string | `processing`, `ready`, `failed` |

### TranscriptSegment

The atomic citation unit.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Segment ID |
| `conversation_id` | UUID | Parent conversation |
| `user_id` | UUID | Ownership |
| `speaker_id` | string | Speaker label from diarization or normalized identity |
| `start_ms` | int | Offset from meeting start |
| `end_ms` | int | Offset from meeting start |
| `text` | string | Transcript text |
| `confidence` | float or null | Provider confidence when available |
| `embedding` | vector or null | Semantic search support |

### TopicNode

The canonical stored topic entity.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Topic node ID |
| `label` | string | Canonical verb+noun label |
| `aliases` | string[] | Accumulated alternate names |
| `type` | string | `discussion`, `decision`, `status_update`, `brainstorm`, `action_planning` |
| `status` | string | `active`, `resolved`, `stale` |
| `priority_level` | string | Highest priority ever observed |
| `source_context` | string or null | `client_request`, `leadership_directive`, `internal`, `compliance`, or null |
| `speaker_seniority` | string or null | Highest relevant speaker seniority |
| `entities` | Entity[] | Accumulated entities |
| `all_keywords` | string[] | Union of related keywords |
| `decisions` | string[] | Decisions associated with the topic |
| `open_questions` | string[] | Outstanding questions |
| `commitments` | Commitment[] | Active topic-linked commitments |
| `first_mentioned_at` | ISO datetime | First appearance |
| `last_mentioned_at` | ISO datetime | Most recent appearance |
| `mention_count` | int | Number of conversations where it appeared |
| `conversation_ids` | UUID[] | Linked conversations |
| `related_topic_ids` | UUID[] | Graph links |
| `derived_from_id` | UUID or null | Parent topic if forked |
| `derived_topics` | UUID[] | Child topics |

### Topic Arc

Computed chronological view over a TopicNode's touchpoints.

| Field | Type | Notes |
|---|---|---|
| `topic_id` | UUID | Source topic node |
| `arc_points` | ArcPoint[] | Chronological points |
| `conversation_count` | int | How many conversations contributed |
| `status` | string | `open` or `resolved` |
| `status_note` | string | Human-readable arc state summary |

### Connection

Stored relationship between conversations or topics.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Connection ID |
| `user_id` | UUID | Ownership |
| `conversation_ids` | UUID[] | Linked conversations |
| `topic_id` | UUID | The topic causing the connection |
| `rationale` | string | Required explanation for surfacing |
| `detected_at` | ISO datetime | Detection timestamp |
| `seen_by_user` | bool | New/unread signal |

### Commitment

Future-action statement attributed to a person.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Commitment ID |
| `conversation_id` | UUID | Source conversation |
| `user_id` | UUID | Ownership |
| `attributed_to` | string | Person responsible |
| `extracted_text` | string | Extracted action statement |
| `due_date` | ISO date or null | Due date if present |
| `status` | string | `open` or `resolved` |
| `resolved_at` | ISO datetime or null | Resolution timestamp |
| `segment_ids` | UUID[] | Supporting transcript citations |

### Brief

Forward-looking pre-meeting preparation artifact.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Brief ID |
| `conversation_id` | UUID or null | Most relevant previous conversation if available |
| `calendar_event_id` | string | Event the brief was generated for |
| `meeting_series_id` | string or null | Recurring series identifier |
| `generated_for_date` | ISO date | Target meeting date |
| `content` | string | Generated brief text |
| `last_session_summary` | string | Prior-session recap |
| `relevant_commitments` | Commitment[] | Open relevant commitments |
| `relevant_connections` | Connection[] | Relevant connections |
| `suggested_agenda` | string[] | Suggested agenda items |
| `generated_at` | ISO datetime | Generation timestamp |
| `share_token` | UUID or null | Sharing token |
| `share_revoked_at` | ISO datetime or null | Revocation timestamp |

### Object relationship summary

```text
Index (per user)
|- Conversations [1..N]
|  |- TranscriptSegments [1..N]
|  |- Commitments [0..N]
|  |- references Entities [0..N]
|- TopicNodes [0..N]
|  |- linked to Conversations [1..N]
|  |- rendered as Topic Arcs on query
|- Connections [0..N]
|  |- link Conversations or Topics [2..N]
|- Briefs [0..N]
   |- composed from TopicNodes/Arcs + Commitments + Connections + Calendar context
```

---

## 8. End-to-End System Architecture

### Responsibility boundaries

| Component | Responsibility |
|---|---|
| Electron desktop app | Auth initiation, calendar polling, notification scheduling, permission checks, capture orchestration, desktop shell UI, local session storage |
| FastAPI API | Auth, session validation, upcoming meeting feed, read APIs, capture session lifecycle, transcript persistence, worker dispatch |
| Celery workers | Extraction, embeddings, calendar sync, brief generation, recurring scheduling, topic backfill |
| Supabase Postgres + pgvector | Durable user-scoped storage, RLS enforcement, vector search |
| Upstash Redis | Celery broker and task coordination |
| Deepgram | Real-time transcription and diarization |
| Anthropic + OpenAI | Structured intelligence extraction, brief generation, embeddings |
| Render | Backend and worker hosting |
| Vercel | Existing web-hosted React surfaces and possible shared asset/runtime support |

### Trust and privacy boundaries

| Boundary | Rule |
|---|---|
| Desktop to backend | Authenticated using user-scoped session/token only |
| Backend to DB | User JWT for all user data access; never service-role reads for user data |
| Worker execution | Every task carries `user_id` and validates ownership |
| Audio handling | Audio is transient and must never be retained after successful transcription |
| Logs | Transcript content never appears in logs, traces, or error payloads |

### System flow

```text
Google Calendar
   |
   v
Desktop app -> schedules 1-minute notification
   |
   v
User clicks "Start Pocket Nori"
   |
   v
Desktop app captures:
- system audio
- microphone audio
   |
   v
Authenticated live capture session
   |
   v
FastAPI ingest channel
   |
   v
Deepgram real-time transcription
   |
   v
Transcript chunks -> TranscriptSegments -> Conversation finalized
   |
   v
Celery worker chain
   |- topic intelligence extraction
   |- commitment extraction
   |- entity extraction
   |- embeddings
   |- calendar artifact sync
   |- recurring brief prep
   |
   v
Read surfaces
|- dashboard
|- search
|- meetings
|- commitments
|- briefs
|- insights
```

### Why this architecture

| Choice | Rationale |
|---|---|
| Desktop-first | Meeting capture needs desktop permissions, notifications, and audio access |
| No bot | Preserves trust and avoids admin approval friction |
| Backend-centralized transcription and extraction | Keeps the intelligence model server-side and user-scoped |
| Reuse web/shared React UI | Avoids rebuilding proven read surfaces unnecessarily |
| Separate async workers | Meeting post-processing should not block the API or UI |

---

## 9. Ingestion and Capture Spec

### Scheduled meeting flow

1. Desktop app polls or refreshes the upcoming-meetings feed using Google Calendar metadata.
2. If a meeting is scheduled to begin in 1 minute, the app issues a native macOS notification.
3. Notification text is action-oriented: `Meeting starts in 1 minute. Start Pocket Nori?`
4. Clicking the notification creates a capture session and immediately starts capture.
5. The app captures system audio and microphone audio.
6. Audio is streamed to the backend over an authenticated live channel.
7. Backend forwards audio to Deepgram and accumulates transcript segments.
8. When the capture stops, the backend finalizes the conversation, persists transcript segments, and dispatches downstream workers.

### Ad-hoc meeting flow

Ad-hoc meetings are not tied to a scheduled calendar event.

1. User opens the menu bar app and chooses `Start ad-hoc capture`.
2. App creates a capture session without a required `calendar_event_id`.
3. User optionally provides a title or accepts a generated fallback title.
4. The rest of the capture, transcript, and worker flow is identical to scheduled meetings.

### Capture start behavior

| Rule | Decision |
|---|---|
| Scheduled prompt timing | Exactly 1 minute before scheduled start |
| Automatic capture without click | Not allowed in v1 |
| Prompt after scheduled start | If the prompt is missed, the menu bar app still allows immediate start |
| Meeting link launch | Optional convenience, not a required v1 behavior |

### Capture stop behavior

| Rule | Decision |
|---|---|
| Primary stop | At scheduled end time plus 5-minute grace window |
| Manual stop | User can stop at any time |
| Overrun handling | If the meeting runs long, the app offers `Extend 15 minutes` from the active capture surface |
| Ad-hoc stop | Manual stop only |

### Conversation-to-calendar matching

| Scenario | Matching rule |
|---|---|
| Scheduled meeting started from notification | Use the `calendar_event_id` from the notification payload |
| Meeting started manually within +/- 10 minutes of a scheduled event | Associate with the closest eligible event if the user has not chosen ad-hoc mode |
| User intentionally starts ad-hoc | Do not force-link to a calendar event |
| Recurring meeting | Persist both `calendar_event_id` and recurring-series identifier when available |

### Audio lifecycle

| Rule | Requirement |
|---|---|
| Storage | Audio must not be stored as a durable artifact |
| Transport | Audio may exist only in memory and in transit for transcription |
| Success path | Discard audio immediately after transcript persistence succeeds |
| Failure path | If buffering or retry storage is required, enforce a maximum 1-hour retention before hard-delete |
| Logging | Never log audio-derived content or transcript text |

### Privacy constraints on capture

- Capture only starts after an explicit user action.
- No bot joins the meeting.
- Audio data is transient.
- Transcript content is private and user-scoped.
- All downstream processing uses the user's data boundary.

### Why calendar is metadata, not capture

Google Calendar exists to provide:

- meeting timing
- title
- attendees
- recurring-series identity
- brief context

Google Calendar is not the audio source. The desktop app is the audio capture source.

---

## 10. Topic Intelligence Pipeline

### Pipeline summary

The canonical topic intelligence pipeline is a 5-stage system optimized for cost efficiency, determinism where possible, and high extraction precision.

| Stage | Name | Method | Primary output |
|---|---|---|---|
| 1 | Segmentation | Heuristic, no LLM | `DiscussionBlock[]` |
| 2 | Entity extraction | spaCy + patterns, no LLM | `Entity[]` per block |
| 3 | Candidate identification | Tier 1 deterministic + Tier 2 Haiku validation | `CandidateTopic[]` |
| 4 | Filtering | Rule-based qualification | filtered candidate topics |
| 5 | Resolution | Hybrid scoring + Sonnet for ambiguous cases | `ResolutionDecision`, updated `TopicNode` |

### Stage detail

| Stage | Purpose | Inputs | Outputs | Deterministic vs LLM | Rationale | Cost intent |
|---|---|---|---|---|---|---|
| Segmentation | Break meeting into discussion blocks before topic extraction | Transcript utterances, timestamps, speaker labels, calendar metadata | `DiscussionBlock[]` | Deterministic | Reduce downstream LLM load and make topic boundaries explicit | $0.00 |
| Entity extraction | Pull out facts, not interpretations | Discussion block text, known participants | `Entity[]` | Deterministic | Entities should be stable and cheap to compute | $0.00 |
| Candidate identification | Decide which blocks are worth deeper topic interpretation | Blocks, entities, meeting context | `BlockCandidacy[]`, `CandidateTopic[]` | Mixed | Most blocks are not worth LLM cost; Tier 1 filters cheaply first | ~$0.02-$0.08 |
| Filtering | Remove low-value, personal, or non-substantive blocks | Candidate topics, contextual signals | narrowed candidate set | Mixed but mainly rule-based | Avoid polluting the topic graph with noise | ~$0.01-$0.03 |
| Resolution | Decide whether a topic is new, same, related, or derived | Candidate topics, existing topic graph, embeddings, keywords, entities | `ResolutionDecision[]`, updated `TopicNode` state | Hybrid with LLM only for ambiguity | Preserve topic continuity while preventing over-merge | ~$0.02-$0.06 |

### Pipeline design principles

1. Use deterministic logic wherever a stable rule is possible.
2. Spend LLM budget only where judgment is actually needed.
3. Preserve enough metadata to support future backfill and re-resolution.
4. Optimize for durable topic memory, not per-meeting labeling tricks.

### Canonical pipeline schemas

#### `DiscussionBlock`

```python
class DiscussionBlock(BaseModel):
    block_id: int
    start_index: int
    end_index: int
    start_timestamp: float | None
    end_timestamp: float | None
    shift_type: str
    participants: list[str]
    duration_seconds: float
    utterance_count: int
    text: str
```

#### `Entity`

```python
class Entity(BaseModel):
    type: str
    value: str
    raw: str
    confidence: float
```

#### `MeetingContext`

```python
class MeetingContext(BaseModel):
    title: str
    categories: list[str]
    extraction_hints: list[str]
    has_executive: bool
    participant_count: int
    participants: list[str]
    participant_roles: dict[str, str]
    recurring_series: str | None
```

#### `BlockCandidacy`

```python
class BlockCandidacy(BaseModel):
    block_id: int
    candidacy_score: float
    is_candidate: bool
    signals: dict
```

#### `Commitment`

```python
class Commitment(BaseModel):
    owner: str
    action: str
    deadline: str | None
```

#### `CandidateTopic`

```python
class CandidateTopic(BaseModel):
    is_valid_topic: bool
    skip_reason: str | None
    name: str | None
    type: str | None
    key_points: list[str]
    decision_made: str | None
    commitments: list[Commitment] | None
    open_questions: list[str]
    related_keywords: list[str]
    entities: list[Entity]
    adjective_signals: list[str]
    priority_level: str
    source_context: str | None
    speaker_seniority: str | None
    discussion_block_id: int
    meeting_title_mapping: str | None
    confidence_score: float
    segment_ids: list[str]
```

#### `MergeCandidate`

```python
class MergeCandidate(BaseModel):
    existing_topic_id: str
    existing_topic_label: str
    combined_score: float
    score_breakdown: dict
    aliases: list[str]
    last_mentioned_at: str
    participant_names: list[str]
    entities: list[Entity]
```

#### `ResolutionDecision`

```python
class ResolutionDecision(BaseModel):
    new_topic_name: str
    candidate_id: str | None
    relationship: str
    confidence: float
    reasoning: str
    method: str
```

#### `TopicNode`

```python
class TopicNode(BaseModel):
    id: str
    label: str
    aliases: list[str]
    type: str
    status: str
    priority_level: str
    source_context: str | None
    speaker_seniority: str | None
    entities: list[Entity]
    all_keywords: list[str]
    decisions: list[str]
    open_questions: list[str]
    commitments: list[Commitment]
    first_mentioned_at: str
    last_mentioned_at: str
    mention_count: int
    conversation_ids: list[str]
    related_topic_ids: list[str]
    derived_from_id: str | None
    derived_topics: list[str]
    embedding: list[float]
    created_at: str
    updated_at: str
    user_id: str
```

### Topic extraction acceptance intent

| Goal | Requirement |
|---|---|
| Cost | $0.05-$0.20 per meeting target |
| Determinism | Stage 1, 2, and Tier 1 candidacy remain deterministic |
| LLM stability | Temperature 0 on all pipeline LLM calls |
| Quality | Greater than 90% precision target for useful topic extraction |
| Graph durability | Topic continuity must survive repeated meetings and backfill |

---

## 11. Interfaces and Contracts

This section freezes the required product contracts, even where code does not yet exist.

### 11.1 Desktop auth/session contract

#### `DesktopAppSession`

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "access_token": "jwt",
  "refresh_token": "opaque-or-jwt",
  "expires_at": "2026-03-24T12:00:00Z",
  "google_calendar_connected": true
}
```

#### Contract rules

- Desktop app must authenticate as the actual user.
- Token storage must use macOS Keychain or equivalent secure OS storage.
- Backend authorization for desktop requests uses bearer token, not browser cookie.
- Desktop session renewal must happen before token expiry without forcing a full relogin.

### 11.2 Upcoming meetings contract

#### `UpcomingMeeting`

```json
{
  "calendar_event_id": "google-event-id",
  "recurring_series_id": "series-id-or-null",
  "title": "Weekly Product Review",
  "start_time": "2026-03-24T09:59:00Z",
  "end_time": "2026-03-24T10:30:00Z",
  "participants": ["Alice <alice@example.com>", "Bob <bob@example.com>"],
  "is_recurring": true,
  "minutes_until_start": 1,
  "eligible_for_brief": true,
  "latest_brief_id": "uuid-or-null"
}
```

#### Contract rules

- Feed returns all meetings in the next 24 hours for desktop scheduling.
- Desktop app is responsible for issuing the local notification at 1 minute.
- Backend does not own OS notification scheduling.

### 11.3 Capture session contract

#### `CaptureSession`

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "calendar_event_id": "google-event-id-or-null",
  "recurring_series_id": "series-id-or-null",
  "title": "Weekly Product Review",
  "source": "scheduled_notification",
  "status": "pending",
  "started_at": "2026-03-24T09:59:05Z",
  "expected_end_at": "2026-03-24T10:35:00Z",
  "capture_mode": "system_plus_mic"
}
```

#### Allowed `source` values

- `scheduled_notification`
- `manual_start`
- `ad_hoc`

#### Allowed `status` values

- `pending`
- `recording`
- `finalizing`
- `completed`
- `failed`
- `cancelled`

### 11.4 Streaming transcript event contract

#### Client -> backend event

```json
{
  "type": "audio_chunk",
  "capture_session_id": "uuid",
  "sequence": 12,
  "sent_at": "2026-03-24T10:00:01Z",
  "sample_rate_hz": 16000,
  "channels": 1,
  "encoding": "pcm_s16le",
  "track": "system|mic|mixed",
  "payload_base64": "..."
}
```

#### Backend -> client event

```json
{
  "type": "transcript_partial",
  "capture_session_id": "uuid",
  "sequence": 12,
  "speaker_id": "Speaker 1",
  "start_ms": 64000,
  "end_ms": 69000,
  "text": "partial text",
  "is_final": false
}
```

### 11.5 Finalized ingest result contract

#### `ConversationIngestResult`

```json
{
  "capture_session_id": "uuid",
  "conversation_id": "uuid",
  "calendar_event_id": "google-event-id-or-null",
  "segment_count": 184,
  "duration_seconds": 1832,
  "status": "ready_for_extraction"
}
```

### 11.6 Topic read model

#### `TopicNodeReadModel`

```json
{
  "id": "uuid",
  "label": "Finalizing Q3 pricing model",
  "aliases": ["Q3 pricing", "tiered pricing model"],
  "status": "active",
  "priority_level": "high",
  "conversation_count": 4,
  "last_mentioned_at": "2026-03-24T10:30:00Z",
  "entities": [{"type": "company", "value": "Acme Corp", "raw": "Acme", "confidence": 0.96}],
  "all_keywords": ["pricing", "Q3", "tiered"],
  "related_topic_ids": ["uuid"]
}
```

### 11.7 Brief read model

#### `BriefReadModel`

```json
{
  "id": "uuid",
  "calendar_event_id": "google-event-id",
  "event_title": "Weekly Product Review",
  "event_start": "2026-03-24T09:59:00Z",
  "preview": "Last week the team aligned on pricing scope...",
  "content": "full brief text",
  "open_commitments_count": 2,
  "related_topic_count": 3,
  "citation_segment_ids": ["uuid-1", "uuid-2"]
}
```

---

## 12. Workers and Async Processing

| Task | Status | Purpose | Trigger | Inputs | Outputs | Idempotency rule | Retry rule | Privacy rule |
|---|---|---|---|---|---|---|---|---|
| `ingest_recording` | Implemented, legacy/backfill | Import historical transcript documents from Google Drive | User starts import batch | drive file metadata, user JWT, refresh token | Conversation + transcript segments | Unique `drive_file_id` per conversation prevents duplicates | Celery retries on transient failure | Uses user JWT only; transcript content not logged |
| `finalize_live_capture` | Target | Finalize a desktop capture session into a durable conversation | User/manual/system stop of capture session | capture session ID, buffered transcript events, user JWT, meeting metadata | Conversation + transcript segments + downstream dispatch | One completed conversation per capture session ID | Retry until finalization succeeds or session marked failed | Audio transient; no audio persistence after success |
| `extract_from_conversation` | Implemented, evolving | Run the intelligence pipeline over one conversation | New conversation ready for extraction | conversation ID, user JWT | TopicNode updates, commitments, entities, summary, citations | Re-running should upsert deterministic outputs for the same conversation | Retry structured-output or provider failures | All DB work under user JWT; no transcript text in logs |
| `embed_conversation` | Implemented | Generate embeddings for search support | Extraction or transcript persistence complete | conversation or segment payloads | embeddings in pgvector-backed storage | Embedding write is keyed to conversation/segment IDs | Retry provider/network failures | Embeddings remain user-scoped |
| `sync_calendar_artifacts` | Implemented | Link conversations to calendar events and dispatch recurring brief scheduling | Post-login, post-ingest, or explicit sync | user ID, user JWT, refresh token | linked conversations, scheduler dispatch | Same conversation-event pair should not duplicate | Retry token/network failures | Uses user JWT for reads/writes |
| `generate_brief` | Implemented | Build a pre-meeting brief from prior context | scheduler or explicit generate action | user ID, user JWT, conversation/calendar context | brief record + link rows | One latest brief per meeting window; later generation can supersede | Retry on provider failure with bounded attempts | Citations and content remain user-scoped |
| `schedule_recurring_briefs` | Implemented | Identify eligible recurring meetings and queue brief generation | post-login sync and periodic scheduler | user ID, user JWT, refresh token | queued brief jobs | Avoid duplicate scheduling for the same event window | Retry scheduling failures | Only user-owned meetings considered |
| `recluster_topics_for_user` / topic backfill | Implemented transitional / target evolving | Rebuild topic graph for historical meetings | manual admin/user trigger or migration | user ID, user JWT | refreshed topic graph and arcs | Reprocessing same user should converge on canonical TopicNode state | Retry bounded by worker limits | Entire run remains user-scoped |
| `process_transcript` | Legacy stub | Historical placeholder task | no longer a target flow | transcript ID, user ID, raw text | queued placeholder response | N/A | N/A | Should eventually be removed or repurposed |

### Worker chain for desktop capture

```text
Capture session complete
-> finalize_live_capture
-> extract_from_conversation
-> embed_conversation
-> sync_calendar_artifacts
-> schedule_recurring_briefs / generate_brief as needed
```

### Why Celery remains the right abstraction

- extraction is slower than request/response latency should allow
- retries and visibility matter
- brief generation and calendar sync are naturally background work
- the product already uses Celery successfully in the backend architecture

---

## 13. Privacy, Security, and Non-Negotiables

| Rule | Requirement |
|---|---|
| Per-user isolation | Enforce at DB, storage path, cache key namespace, vector search filter, LLM call scope, and job payload scope |
| No service-role reads | `service_role` is never used to read user-owned data in application paths |
| No model training on user data | Providers must not use submitted user data for model training; production requires formal agreements before external rollout |
| Hard-delete only | No soft-delete columns, no grace period semantics for user-owned content |
| No audio retention | Audio is transient and deleted immediately after successful transcription; no durable audio library |
| Startup validation | Required provider and infra config must exist before the server starts |
| Centralized LLM calls | All LLM usage must route through `src/llm_client.py` or its future equivalent central module |
| No transcript logging | Transcript text, prompt bodies, and sensitive derived content must not appear in app logs |
| Private by default | No manager/admin visibility into user intelligence |

### Per-user isolation model

| Layer | Enforcement |
|---|---|
| Postgres | FORCE RLS and `user_id = auth.uid()` style policies |
| Storage | `/users/{user_id}/...` namespace |
| Redis | `user:{user_id}:...` namespacing |
| Vector search | Filter by `user_id` before ANN similarity |
| LLM calls | Never batch transcript content across users |
| Workers | Every payload includes `user_id`; ownership validated before read/write |

### Required startup configuration

At minimum:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`
- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `UPSTASH_REDIS_URL`
- `DEEPGRAM_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `SECRET_KEY`

---

## 14. Deployment and Operations

### Current deployment topology

| Component | Host |
|---|---|
| FastAPI API | Render |
| Combined Celery worker | Render |
| Existing web frontend | Vercel |
| Database + auth + storage | Supabase |
| Redis broker | Upstash Redis |

### Required services

| Service | Required for | Notes |
|---|---|---|
| Render web service | API | Existing service remains |
| Render worker service | Celery | Existing combined worker remains |
| Vercel | Shared web/read surfaces | Reused UI remains useful even in desktop-first product |
| Supabase | DB, auth, storage | Existing core platform |
| Upstash Redis | Broker/backend queue | Existing broker; monitor quota and reliability |
| Apple Developer Program | Mac distribution | Required for signing/notarization |

### What the desktop app adds

| Area | Addition |
|---|---|
| Distribution | Signed macOS application package |
| Runtime | Local Electron process with permissions, notifications, and capture |
| Session handling | Secure desktop session/token storage |
| Observability | Desktop crash/error telemetry and release version tracking |
| Updates | Desktop app update mechanism |

### Important operational rule

The desktop app does **not** replace the backend/web infrastructure. It adds a capture/runtime surface on top of the existing cloud system.

### Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `SUPABASE_URL` | API, workers | Supabase project endpoint |
| `SUPABASE_ANON_KEY` | API, workers | client auth |
| `SUPABASE_SERVICE_KEY` | infra-only / migrations | not for user data reads |
| `DATABASE_URL` | API, workers | direct Postgres/pgvector access |
| `ANTHROPIC_API_KEY` | API, workers | structured extraction and brief generation |
| `OPENAI_API_KEY` | API, workers | embeddings |
| `UPSTASH_REDIS_URL` | API, workers | Celery broker/result backend |
| `DEEPGRAM_API_KEY` | API, workers | transcription |
| `GOOGLE_CLIENT_ID` | API, desktop auth flow | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | API | Google OAuth token exchange |
| `SECRET_KEY` | API | session security |
| `API_BASE_URL` | API, frontend, desktop | canonical API URL |
| `FRONTEND_URL` | API, frontend | current web/read surface URL |

### Monitoring and hardening expectations

| Requirement | Intent |
|---|---|
| Centralized error reporting | Required before pilot scale |
| Queue backlog alerts | Required for meeting-processing reliability |
| Desktop crash telemetry | Required once the app is distributed beyond internal use |
| Backup/restore discipline | Required before external pilot |
| OAuth config review | Required before real distribution |

---

## 15. Engineering Working Rules

### Coding conventions

| Area | Rule |
|---|---|
| Backend language | Python 3.13 |
| Frontend/desktop language | TypeScript |
| Formatting | `ruff` for Python |
| Typing | `mypy` strict for Python |
| Naming | `snake_case` files/functions, `PascalCase` classes |
| Import order | future, stdlib, third-party, local |

### File structure

| Area | Path |
|---|---|
| API routes | `src/api/routes/` |
| Shared backend config | `src/config.py`, `src/database.py`, `src/llm_client.py` |
| Workers | `src/workers/` |
| Models | `src/models/` |
| Migrations | `migrations/` |
| Frontend | `frontend/` |
| Specs | `docs/specs/` |

### Implementation rules

1. All LLM calls go through one module.
2. Never log transcript content.
3. Never read user data with the service-role key in application paths.
4. Do not add soft-delete behavior.
5. Use user-scoped JWT-based DB access for workers and routes.
6. Preserve explicit citations from transcript segments through all downstream features.

### Testing commands

```bash
source .venv/bin/activate

# Backend unit tests
python -m pytest tests/ -v -m unit

# Backend integration tests
python -m pytest tests/ -v -m integration --timeout=30

# Full backend suite
pytest -q

# Lint and typecheck
ruff check src tests
mypy src tests

# Frontend validation
cd frontend && npm run lint && npm run build
```

### Migration rules

- Never rewrite existing migrations.
- Add new migrations sequentially.
- Any schema change affecting user-owned data must preserve RLS and hard-delete rules.

### Documentation sync rules

When the architecture or product direction changes, update the related docs in the same session. At minimum:

- `PROGRESS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/PROJECT.md`
- `AGENTS.md` / `CLAUDE.md` if stage/status text changes
- any affected source docs in `DOCS.md` change protocol

### Working style expectation

- Favor clear, reversible, high-signal architecture.
- Be explicit about what is implemented vs. target.
- Prefer behavior-level documentation over file-by-file churn summaries.
- Preserve privacy constraints in code, not only in policy text.

---

## 16. Acceptance Criteria

### Product acceptance

| Area | Acceptance criteria |
|---|---|
| Onboarding | User can sign in, grant permissions, and reach a ready-to-capture state |
| Scheduled capture | User receives a 1-minute notification and can start capture from it |
| Ad-hoc capture | User can start a capture without a calendar event |
| Search | User can retrieve cited answers across captured meetings |
| Briefs | Eligible recurring meetings receive generated briefs with citations |
| Dashboard | Home surface shows upcoming context, commitments, and recent cross-meeting intelligence |

### Technical acceptance

| Area | Acceptance criteria |
|---|---|
| Transcript persistence | Transcript segments store speaker attribution and timing |
| Worker chain | Capture finalization reliably triggers extraction and embeddings |
| Topic pipeline | 5-stage TopicNode pipeline is the canonical extraction model |
| Reprocessing | Historical meetings can be reprocessed/backfilled without data corruption |
| Auth | Desktop uses secure user-scoped sessions |

### Privacy acceptance

| Area | Acceptance criteria |
|---|---|
| RLS | Cross-user reads are blocked at the DB layer |
| Audio handling | No durable audio retention after success |
| Logging | Transcript content never appears in logs |
| Access model | No service-role user-data reads in app code |

### Desktop capture acceptance

| Area | Acceptance criteria |
|---|---|
| Permissions | App can guide the user to grant required microphone and system-audio permissions |
| Capture | App can capture system audio and mic for meetings happening on the Mac |
| Notification | Native prompt fires at 1 minute before scheduled start |
| Stop behavior | Capture can stop manually and auto-stop with extend support |

### Topic intelligence quality acceptance

| Area | Acceptance criteria |
|---|---|
| Precision | Useful topics exceed the target precision threshold |
| Cost | Pipeline remains inside target cost envelope |
| Stability | Deterministic stages remain stable; LLM stages run at temperature 0 |
| Traceability | Topic decisions and derived entities can be traced back to segments |

### Document acceptance

This document is complete only if:

- a new developer can understand the business problem without reading another doc
- a new developer can identify the active product direction without reading another doc
- a new developer can explain current vs. target state
- a new developer can describe the ingestion, worker, and topic pipeline end to end
- no critical implementation rule requires leaving this file

---

## 17. Source Provenance

| Section in this file | Primary source inputs |
|---|---|
| Business context | `pocket-nori-prd.md` |
| Current implementation constraints | `pocket-nori-tech-requirements-mvp.md` |
| Desktop-first product and future-state architecture | `docs/later-stages/pocket-nori-tech-requirements-full.md` |
| Product surfaces and object model | `pocket-nori-ui-spec.md` |
| Design language | `.interface-design/system.md` |
| Topic intelligence pipeline | `docs/specs/Topic_intelligence.md` |
| Canonical pipeline schemas | `docs/specs/Pydantic_schema.md` |
| Deployment | `render.yaml` |
| Repo conventions and testing | `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/INTEGRATIONS.md` |
| Current execution state | `PROGRESS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` |

### Maintenance note

This file is the canonical zero-context handoff document, but it is maintained by reconciling the underlying source docs above. When product or architecture decisions change, update both this file and the relevant source documents in the same session.
