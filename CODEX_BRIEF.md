# Pocket Nori — Master Brief: Claude Code + Codex Parallel Work Division
# Updated: 2026-03-16

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

## Full Product Feedback — 24 Items (Status as of 2026-03-16)

| # | Feature | Type | Effort | Owner | Wave | Status |
|---|---------|------|--------|-------|------|--------|
| 1 | Product rename → Pocket Nori | Redundancy | Very High | Claude Code | — | ✅ Done |
| 2 | Remove UI text clutter | UI/Design | Low | Codex | Wave B | ✅ Done |
| 3 | Rename Dashboard → Home | Enhancement | Low | Codex | Wave B | ✅ Done |
| 4 | Define "Actions" — Commitments + Follow-ups (backend) | Enhancement | Medium | Claude Code | Wave A | ✅ Done |
| 5 | Profile View — "You" dropdown | New Idea | Medium | Codex | Wave D | ✅ Done |
| 6 | Entities → move to "You" dropdown | Enhancement | Low | Codex | Wave D | ✅ Done |
| 7 | Entities tab UX (filters, sort, edit) | UX/Interaction | Medium | Codex | Wave D | ✅ Done |
| 8 | Onboarding journey (full multi-step flow) | New Idea | Very High | Deferred | — | ⏸ Deferred |
| 9 | Onboarding — optional sync | Enhancement | Medium | Deferred | — | ⏸ Deferred |
| 10 | Import past meetings entry point under Meetings | Enhancement | Low | Codex | Wave G | ✅ Done |
| 11 | Home personal touch (Quick Summary, Today's Meetings, Actions) | Enhancement | High | Deferred | — | ⏸ Deferred |
| 12 | Home — Calendar widget UI | UI/Design | Low | Codex | Wave B | ✅ Done |
| 13 | Home — Actions widget (rename + add follow-ups) | Enhancement | Medium | Codex | Wave C | ✅ Done |
| 14 | Meetings list UI redesign (Fireflies/Otter-style) | UI/Design | High | Deferred | — | ⏸ Deferred |
| 15 | /today page simplification | UX/Interaction | Low | Codex | Wave B | ✅ Done |
| 16 | Meeting detail — header cleanup | Enhancement | Low | Codex | Wave B | ✅ Done |
| 17 | Meeting detail — tab navigation (Topics/Actions/Transcript) | UX/Interaction | Medium | Codex | Wave E | ✅ Done |
| 18 | Meeting detail — remove entities | Enhancement | Low | Codex | Wave B | ✅ Done |
| 19 | Meeting detail — Actions (rename + stricter extraction) | Enhancement | Medium | Claude Code + Codex | Wave A + E | ✅ Done (Wave A backend done; Wave E frontend done; action_type now in GET /conversations/{id} via PR #23) |
| 20 | Meeting detail — transcript conversation view | Enhancement | Medium | Codex | Wave E | ✅ Done |
| 21 | Global search bar (persistent, across all pages) | Enhancement | Medium | Codex | Wave F | ✅ Done |
| 22 | Actions page (Commitments → Actions, add follow-ups) | Enhancement | Medium | Codex | Wave C | ✅ Done |
| 23 | Integrations (Zoom, Teams, Slack etc.) | New Idea | Very High | Deferred | — | ⏸ Deferred |
| 24 | Bot as meeting participant | New Idea | Very High | Deferred | — | ⏸ Deferred |
| 25 | Native Mac / iPhone app | New Idea | Very High | Deferred | — | ⏸ Deferred |

**Deferred items** (High / Very High effort): #8, #9, #11, #14, #23, #24, #25 — not in scope for this round.

---

## Execution Status Summary

```
Wave A — Claude Code ✅ DONE  (action_type backend, PR #22 merged)
Wave B — Codex      ✅ DONE  (UI cosmetic fixes)
Wave C — Codex      ✅ DONE  (Actions UI rebuild)
Wave D — Codex      ✅ DONE  (Profile dropdown + entity management)
Wave E — Codex      ✅ DONE  (Meeting detail overhaul)
Wave F — Codex      ✅ DONE  (Persistent global search bar)
Wave G — Codex      ✅ DONE  (Import past meetings entry point on Meetings page)
```

**✅ All 18 in-scope items complete. 7 items remain deferred for a future round.**

**Backend fix for Wave E** (PR #23 merged): `GET /conversations/{id}` now returns `action_type` on each commitment — meeting detail Actions tab can split into Commitments vs Follow-ups.

---

## Wave G — Codex: Import Past Meetings Entry Point ✅ DONE

### File changed:
- `frontend/src/app/meetings/page.tsx`

### What was built:
- Persistent "Import past meetings" entry point at the top of the Meetings page
- Always visible (not conditional on meeting count) — users can import more meetings at any time
- Clicking navigates to `/onboarding`
- Understated style — secondary action, does not compete with the meetings list
- Label: **"Import past meetings"** (not "sync" — avoids confusion)

---

## API Contract Reference

All endpoints are live at: `https://farz-personal-intelligence.onrender.com`

### Commitments (Wave A — live)
```
GET  /commitments
     ?action_type=commitment|follow_up
     ?filter_status=open|resolved
     ?assignee=name
     ?topic=label
     ?meeting=id
     → CommitmentOut[]

     CommitmentOut shape:
     {
       id, text, owner, due_date, status,
       action_type: "commitment" | "follow_up",
       conversation_id, conversation_title,
       meeting_date, topic_labels
     }

POST /commitments
     { text, action_type, owner, due_date }
     → 201 CommitmentOut

PATCH /commitments/{id}
     { status: "resolved" | "open" }
     → 200 CommitmentOut
```

### Conversation detail (PR #23 — deploy pending)
```
GET /conversations/{id}
    → ConversationDetail
    commitments[] now includes action_type: "commitment" | "follow_up"
```

### Other endpoints (unchanged)
```
GET  /conversations          → ConversationSummary[]
GET  /topics                 → TopicSummary[]
GET  /topics/{id}            → TopicDetail
POST /search                 → SearchResult[]
POST /search/ask             → { answer, citations[] }
GET  /calendar/today         → { upcoming_meetings, open_commitments, recent_activity, recent_connections }
GET  /index/stats            → { conversation_count, topic_count, commitment_count, entity_count }
GET  /entities               → Entity[]
GET  /briefs/latest          → BriefSummary
GET  /briefs/{id}            → BriefDetail
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
