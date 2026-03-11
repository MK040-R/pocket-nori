# DOCS.md — Documentation Index

This file is the entry point for understanding the Farz documentation suite. Read this first before reading any other document. It tells you what each file is, when to read it, and what to do when documents conflict.

---

## Document Registry

### `farz-prd.md` — Product Requirements Document
**Audience:** Everyone (product, engineering, design)
**Purpose:** Defines what Farz does and why. Covers user experience, intelligence capabilities, privacy principles, the conceptual data model, and the phased roadmap.
**When to read:** Before writing any code. Sections 3 (Privacy Principles) and 5 (Conceptual Data Model) are mandatory prerequisites.
**Does NOT cover:** How to build it, which libraries to use, infrastructure choices. For those, see the tech requirements.

---

### `farz-tech-requirements-mvp.md` — Technical Requirements (MVP)
**Audience:** Engineers building Phases 0a through 2
**Purpose:** Records every major engineering decision with its rationale. Stack choices, database strategy, authentication, ingestion pipeline, async job design, infrastructure, per-user isolation enforcement. Explicitly overrides the PRD on implementation choices where the two conflict.
**When to read:** Before any architecture or infrastructure work. The definitive source for "why did we choose X?"
**Does NOT cover:** Phase 3+ (Electron, AWS, compliance). For those, see `docs/later-stages/farz-tech-requirements-full.md`.

---

### `farz-ui-spec.md` — UI Specification
**Audience:** Frontend engineers, backend engineers (for the API surface section)
**Purpose:** Screen-by-screen specification of every view, component, and state. Defines the API contract (endpoints, payloads, phase labels). Defines Day 1 / Day N user journeys and empty states.
**When to read:** Before any frontend work. Backend engineers should read Section 9 (API Surface) before building any endpoint.
**Does NOT cover:** Design tokens, colors, fonts. For those, see `.interface-design/system.md`.

---

### `.interface-design/system.md` — Interface Design System
**Audience:** Frontend engineers
**Purpose:** Design token definitions (colors, typography, spacing, borders, depth). The canonical source for all visual values — background colors, text colors, accent, font sizes, weights.
**When to read:** Before writing any CSS, Tailwind class, or component styling.
**Does NOT cover:** Screen layouts or component behavior. For those, see the UI spec.

---

### `spikes/PHASE_0A_SUMMARY.md` — Phase 0a Spike QA Summary
**Audience:** Engineers starting Phase 0
**Purpose:** QA results for all 5 technical spikes. Records go/no-go decisions, bugs found and fixed, and human-action blockers that must be resolved before Phase 0 can start.
**When to read:** Before writing Phase 0 foundation code.

---

### `docs/later-stages/farz-tech-requirements-full.md` — Full Architecture (Phase 3+)
**Audience:** Engineers planning Phase 3 and beyond
**Purpose:** Covers the full architectural vision: AWS ECS/RDS migration, Electron desktop app, formal compliance (SOC 2, GDPR, ADGM), enterprise multi-tenancy.
**When to read:** Phase 3+ planning only. Do not apply Phase 3+ decisions to MVP work.

---

### `agent_docs/CODEX_BRIEF.md` — Cross-Agent Integration Brief
**Audience:** Claude Code + Codex
**Purpose:** Historical contract for earlier Claude/Codex parallel wave coordination and API shape expectations.
**When to read:** Reference only. Current execution ownership is Codex end-to-end.

---

### `PROGRESS.md` — Shared Progress Log
**Audience:** Codex + humans tracking execution
**Purpose:** Append-only log of completed tasks and wave milestones.
**When to read:** Before starting work to avoid duplicate effort; update after each completed task.

---

### `POST_MVP_HARDENING_PLAN.md` — Pilot Hardening Execution Plan
**Audience:** Codex + humans running post-MVP pilot prep
**Purpose:** Single-source plan for moving from MVP-complete to pilot-ready (privacy/legal guardrails, observability, reliability, security ops, support readiness, rollout gate).
**When to read:** At the start of any post-MVP session before implementing hardening milestones.

---
### `competitive-analysis.md` — Competitive Analysis
**Audience:** Product, engineering (background reading)
**Purpose:** Static research on Granola, Otter.ai, Fireflies.ai, Notion, and Mem0. Informs product positioning and informed several architectural decisions (e.g., no-bot approach from Granola).
**When to read:** Background context. Not a decision document — it does not change decisions.

---

### `CLAUDE.md` — Claude Code Instructions
**Audience:** Claude Code (AI coding assistant)
**Purpose:** Mirrors the decisions in the above docs in a format optimized for Claude Code sessions. Contains spike run commands and current phase status.
**When to read:** Automatically loaded by Claude Code. Humans can read it to understand what Claude Code knows.

---

### `AGENTS.md` — Codex Instructions
**Audience:** Codex (AI coding assistant)
**Purpose:** Same as CLAUDE.md but formatted for Codex.

---

### Linear (external, not in this repo)
**Audience:** Everyone
**Purpose:** Source of truth for sprint tasks, issue status, ticket details, and work-in-progress. Issues are tagged with FAR-XXX identifiers referenced throughout the spike documents.
**When to use:** For task assignment, sprint tracking, and issue status. Not for architectural decisions — those live in the docs above.

---

## Conflict Resolution Hierarchy

When two documents say different things about the same topic, this hierarchy determines which is correct:

| Priority | Document | Scope |
|---|---|---|
| 1 | `farz-tech-requirements-mvp.md` | Implementation decisions — explicitly overrides PRD on technical choices |
| 2 | `farz-prd.md` | Product intent and user experience |
| 3 | `farz-ui-spec.md` | Screen behavior and API contract |
| 4 | `.interface-design/system.md` | Visual tokens and styling |

**Example:** If the PRD and tech requirements disagree on the Phase 1 ingestion method, the tech requirements wins. If the UI spec and design system disagree on a color value, the design system wins.

---

## Change Protocol

When a decision changes, all affected documents must be updated in the same session. Use this table to identify which documents need updating together:

| Decision type | Documents to update |
|---|---|
| Ingestion method / pipeline | Tech requirements + PRD + UI spec (API surface) |
| Privacy / compliance stance | PRD (Principles) + Tech requirements + UI spec (checklist) |
| Phase boundary (what's in Phase 1 vs 2) | Tech requirements + UI spec (phase tags) |
| Data model / entity | PRD (Section 5) + Tech requirements + UI spec (object model) |
| Navigation structure | UI spec + Design system |
| Brief generation rules | PRD (Section 4.3) + UI spec (object model + conditional rules + mockups) |
| Tech stack version | Tech requirements + UI spec (Section 8) |
| Design token | Design system only (UI spec references tokens by name, not value) |
| OAuth scopes | Tech requirements (Section 6) only |
| Milestone completion / phase closure | `PROGRESS.md` + `.planning/ROADMAP.md` + `.planning/STATE.md` + `.planning/PROJECT.md` + assistant instruction file (`AGENTS.md` / `CLAUDE.md`) if status text changed |

**Rule:** If you change one document without updating the others in this table, the documentation suite is out of sync. Future engineers and AI assistants will receive conflicting instructions. Update all affected docs before closing the session.

**Milestone Rule:** After every completed milestone, append an entry to `PROGRESS.md` in the same session with date, scope completed, validation commands, and next focus.

---

## Document Relationship Diagram

```
farz-prd.md                     ← product intent, user experience, privacy principles
    ↓ overridden on impl. by
farz-tech-requirements-mvp.md   ← engineering decisions, stack, infra, pipeline
    ↓ detailed for UI/API by
farz-ui-spec.md                 ← screens, components, API surface, phase tags
    ↓ styled using
.interface-design/system.md     ← tokens, typography, color

All decisions → Linear (tasks)  ← sprint execution, issue tracking
All decisions → CLAUDE.md / AGENTS.md  ← AI assistant context
```
