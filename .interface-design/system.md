# Farz — Interface Design System

## Direction: "Quiet Intelligence"

> A composed, airy workspace for working professionals. Warm off-white background, clean white cards, a single calm blue accent. The feel of a well-organized desk — not a terminal. Nothing fights for attention. The content is the product.

---

## Product Context

**Who is this human:** Working professionals (PMs, team leads, founders, cross-functional operators) context-switching between meetings. They open Farz to recall decisions, prepare for the next meeting, track commitments. Smart, busy, information-dense. They don't need handholding.

**What they must do:** Recall ("what did we decide about X?"), prepare ("what do I need to know before my 2pm?"), track ("what have I committed to?"), discover ("what threads did I miss?").

**How it should feel:** Light, composed, professional. Like the best B2B SaaS products — Stripe, Linear, Notion, Granola. Not a dev tool. Not a colorful startup. A calm intelligence layer that earns trust through clarity.

---

## Design Direction

### Color

Warm off-white base, white surfaces, single calm blue accent.

| Token                    | Value                          | Usage                                                        |
| ------------------------ | ------------------------------ | ------------------------------------------------------------ |
| `--bg-base`              | `#F7F6F3`                      | App background (warm off-white — not clinical white)         |
| `--bg-surface`           | `#FFFFFF`                      | Cards, panels (float on base)                                |
| `--bg-surface-raised`    | `#F0EFF0`                      | Modals, dropdowns                                            |
| `--bg-control`           | `#F3F2EF`                      | Inputs, text areas                                           |
| `--ink-primary`          | `#1C1C27`                      | Primary text (near-black with warm undertone)                |
| `--ink-secondary`        | `#6B6E7A`                      | Supporting text, labels                                      |
| `--ink-tertiary`         | `#9B9EA8`                      | Metadata, timestamps                                         |
| `--ink-muted`            | `#C4C5CB`                      | Disabled, placeholder                                        |
| `--accent`               | `#4A6CF7`                      | Interactive elements, Arc thread, commitment bars, focus — the only color |
| `--accent-subtle`        | `#EEF1FE`                      | Accent backgrounds (badges, highlights)                      |
| `--accent-hover`         | `#3555E8`                      | Hover on accent elements                                     |
| `--border-standard`      | `rgba(0,0,0,0.08)`             | Default separation                                           |
| `--border-soft`          | `rgba(0,0,0,0.04)`             | Very subtle grouping                                         |
| `--border-emphasis`      | `rgba(0,0,0,0.14)`             | Active states, selected rows                                 |
| `--shadow-card`          | `0 1px 4px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.04)` | Card depth |
| `--shadow-raised`        | `0 4px 16px rgba(0,0,0,0.08)` | Modals, hover cards                                          |
| `--semantic-open`        | `#16A37A`                      | Open commitment/topic status                                 |
| `--semantic-resolved`    | `#8E9BA8`                      | Resolved state (neutral, not celebratory)                    |
| `--semantic-destructive` | `#E5484D`                      | Destructive actions                                          |


### Typography

Inter throughout. Round, readable, the lingua franca of modern professional SaaS.

| Role                    | Font  | Weight | Size    | Notes                                           |
| ----------------------- | ----- | ------ | ------- | ----------------------------------------------- |
| Page headings           | Inter | 700    | 22–28px | Letter-spacing `−0.02em`                        |
| Card titles             | Inter | 600    | 15px    | Normal tracking                                 |
| Body                    | Inter | 400    | 14px    | Line height 1.65                                |
| Labels / section headers| Inter | 500    | 11px    | Uppercase, `0.06em` tracking                    |
| Data / timestamps       | Inter | 400    | 12px    | Tabular numbers, `--ink-tertiary`               |
| Transcript              | `ui-monospace` | 400 | 12.5px | `--ink-secondary`, comfortable reading |


### Depth Strategy

**Subtle shadows on white cards floating on warm-base background.**

Light mode earns depth through natural shadow, not color shifting. Cards feel lifted from the page. This is how Stripe, Linear, and Notion do it.

- `--bg-base` is the canvas — warm off-white
- `--bg-surface` (white) cards sit on the canvas with `--shadow-card`
- Sidebar is white — same as a card, separated by `--border-standard`
- Inputs sit slightly inset: `--bg-control` + no shadow
- No borders competing with shadows — pick one per element


### Spacing

Base unit: **4px** — but sections are more generous than the old system.

| Scale | Value | Usage                                       |
| ----- | ----- | ------------------------------------------- |
| `xs`  | 4px   | Icon gaps, tight inline spacing             |
| `sm`  | 8px   | Within components (button padding inline)   |
| `md`  | 16px  | Component padding (cards, inputs)           |
| `lg`  | 20px  | Between related elements                    |
| `xl`  | 32px  | Between sections                            |
| `2xl` | 48px  | Major layout separation                     |


### Border Radius

Friendly and consistent. Not sharp. Not overly bubbly.

| Scale  | Value  | Usage                   |
| ------ | ------ | ----------------------- |
| `sm`   | 6px    | Badges, chips           |
| `md`   | 10px   | Cards, inputs, buttons  |
| `lg`   | 14px   | Modals, popovers        |
| `pill` | 999px  | Status pills            |

---

## Signature Element — The Arc Thread

The **Topic Arc** is Farz's core concept: a topic's journey across meetings over time. A thin `--accent` line threads through meeting nodes in chronological order. Makes the product's intelligence visible.

- Thread weight: 1.5px
- Color: `--accent` at 60% opacity between nodes, 100% at active node
- Node: 10px circle, `--accent` fill, `--bg-surface` inner dot (4px)
- Applied in: Search results (Topic Arc view)

---

## Navigation

Clean white sidebar. Calm and contained.

- Background: `--bg-surface` (white) with `--shadow-card` on right edge
- Width: 220px
- Active state: `--accent` text color, `--accent-subtle` background, no bars or indicators
- Nav item font: Inter 500 14px, `--ink-secondary` default, `--ink-primary` hover
- Logo: Inter 700, `--ink-primary` — no color tricks

Nav items: Dashboard, Search, Meetings, Commitments, Insights

---

## Key Component Patterns

### Meeting Card
- Surface: `--bg-surface`, shadow: `--shadow-card`, radius: `md`
- Title: `--ink-primary`, Inter 600, 15px
- Meta line (date, duration, participants): `--ink-tertiary`, 12px
- "Brief ready" badge: `--accent` background, white text, `pill` radius
- Topic tags: `--accent-subtle` background, `--accent` text, `sm` radius
- Last session teaser: `--ink-secondary`, 13px italic

### Commitment Item
- Left accent bar: 3px `--accent`, rounded
- Extracted text: `--ink-primary`, 14px
- Attribution + date: `--ink-tertiary`, 12px
- Status badge: `pill` shape, `--semantic-open` or `--semantic-resolved`

### Search / Topic Arc Result
- Arc thread connects meeting nodes (see Signature Element)
- ArcPoint cards: `--bg-surface` with `--shadow-card`, 20px padding
- Source meeting citation: `--ink-tertiary`, 12px
- Jump-to-clip link: `--accent` color on hover
- Status note: soft badge at bottom

### Pre-Meeting Brief
- Hero card: `--bg-surface`, `--shadow-card`, 3px `--accent` top border
- Sections: Last session summary, Commitments, Connections, Suggested agenda
- Each section separated by generous whitespace (32px) + `--border-soft` line

---

## What This Is Not

- No dark backgrounds
- No harsh black text (use `--ink-primary` `#1C1C27`, not `#000000`)
- No multiple accent colors
- No decorative gradients
- No dense layouts — every section has breathing room
- No monospace for non-data content (transcripts and timestamps only)
- No borders competing with shadows — choose one elevation method per element
