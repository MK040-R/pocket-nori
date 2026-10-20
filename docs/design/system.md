# Pocket Nori — Interface Design System

## Direction: "Insightful Dashboard"

> A bright, confident dashboard for working professionals. Light mint canvas, crisp white cards, deep navy ink, and a single vivid green accent. Feels like a modern analytics product — clear metrics, obvious status, and fast scanning. The content is still the product, but the frame now feels more purposeful and energetic.

---

## Product Context

**Who is this human:** Working professionals (PMs, team leads, founders, cross-functional operators) context-switching between meetings. They open Pocket Nori to recall decisions, prepare for the next meeting, track commitments. Smart, busy, information-dense. They don't need handholding.

**What they must do:** Recall ("what did we decide about X?"), prepare ("what do I need to know before my 2pm?"), track ("what have I committed to?"), discover ("what threads did I miss?").

**How it should feel:** Light, composed, professional. Like the best B2B SaaS products — Stripe, Linear, Notion, Granola. Not a dev tool. Not a colorful startup. A calm intelligence layer that earns trust through clarity.

---

## Design Direction

### Color

Light mint base, white surfaces, deep navy ink, single vivid green accent. Secondary chart/status accents are derived from semantic tokens, not new primitives.

| Token                    | Value                          | Usage                                                        |
| ------------------------ | ------------------------------ | ------------------------------------------------------------ |
| `--bg-base`              | `#F3F8FF`                      | App background (light blue‑mint canvas; can be overlaid with a subtle gradient) |
| `--bg-surface`           | `#FFFFFF`                      | Cards, panels, sidebar                                       |
| `--bg-surface-raised`    | `#F7FAFF`                      | Header, filters, raised panels                               |
| `--bg-control`           | `#EEF3FF`                      | Inputs, chips, pill filters                                  |
| `--ink-primary`          | `#041021`                      | Primary text (deep navy)                                     |
| `--ink-secondary`        | `#4B5565`                      | Supporting text, labels                                      |
| `--ink-tertiary`         | `#6B7280`                      | Metadata, timestamps                                         |
| `--ink-muted`            | `#9CA3AF`                      | Disabled, placeholder                                        |
| `--accent`               | `#00C27A`                      | Primary interactive elements, nav active state, key metrics  |
| `--accent-subtle`        | `rgba(0, 194, 122, 0.12)`      | Accent backgrounds (badges, highlights, tiles)               |
| `--accent-hover`         | `#02B16F`                      | Hover on accent elements                                     |
| `--border-standard`      | `rgba(15, 23, 42, 0.08)`       | Default separation                                           |
| `--border-soft`          | `rgba(15, 23, 42, 0.04)`       | Very subtle grouping                                         |
| `--border-emphasis`      | `rgba(0, 194, 122, 0.55)`      | Active states, selected items                                |
| `--shadow-card`          | `0 18px 45px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(15, 23, 42, 0.04)` | Card depth |
| `--shadow-raised`        | `0 24px 60px rgba(15, 23, 42, 0.16)` | Modals, hover cards, hero tiles                              |
| `--semantic-open`        | `#F59E0B`                      | Open / pending state (warm amber)                            |
| `--semantic-resolved`    | `#10B981`                      | Resolved / completed state (calm green)                      |
| `--semantic-destructive` | `#EF4444`                      | Destructive or error states                                  |


### Typography

Inter throughout. Round, readable, the lingua franca of modern professional SaaS. The existing `--font-plus-jakarta` variable name stays in code for compatibility, but now resolves to Inter in implementation.

| Role                    | Font  | Weight | Size    | Notes                                           |
| ----------------------- | ----- | ------ | ------- | ----------------------------------------------- |
| Page headings           | Inter | 700    | 22–28px | Letter-spacing `−0.02em`                        |
| Card titles             | Inter | 600    | 15px    | Normal tracking                                 |
| Body                    | Inter | 400    | 14px    | Line height 1.65                                |
| Labels / section headers| Inter | 500    | 11px    | Uppercase, `0.06em` tracking                    |
| Data / timestamps       | Inter | 400    | 12px    | Tabular numbers, `--ink-tertiary`               |
| Transcript              | `ui-monospace` | 400 | 12.5px | `--ink-secondary`, comfortable reading |


### Depth Strategy

**Pronounced but soft shadows under large cards on a bright canvas.**

The dashboard should feel like a layer of cards hovering above a calm gradient — similar to modern analytics tools.

- `--bg-base` is the canvas — light mint/blue; the body may layer a subtle gradient on top.
- `--bg-surface` cards sit on the canvas with `--shadow-card` and `--border-soft`.
- Sidebar intentionally contrasts the main canvas using a deep navy treatment derived from `--ink-primary`, so the navigation rail reads as a separate anchor.
- Inputs use `--bg-control` with no shadow; rely on borders and focus rings instead.
- Prefer shadows for elevation; only use borders for separation and emphasis.


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

Friendly and consistent. Larger radii on primary cards to echo the reference dashboards, while keeping chips compact.

| Scale  | Value  | Usage                   |
| ------ | ------ | ----------------------- |
| `sm`   | 6px    | Badges, chips           |
| `md`   | 12px   | Cards, inputs, buttons  |
| `lg`   | 18px   | Modals, hero tiles      |
| `pill` | 999px  | Status pills, filters   |

---

## Signature Element — The Arc Thread

The **Topic Arc** is Pocket Nori's core concept: a topic's journey across meetings over time. A thin `--accent` line threads through meeting nodes in chronological order. Makes the product's intelligence visible.

- Thread weight: 1.5px
- Color: `--accent` at 60% opacity between nodes, 100% at active node
- Node: 10px circle, `--accent` fill, `--bg-surface` inner dot (4px)
- Applied in: Search results (Topic Arc view)

---

## Navigation

Dark, saturated sidebar on the left. Main workspace stays light; navigation is the single strong contrast zone.

- Background: deep navy gradient derived from `--ink-primary`
- Width: 220–248px
- Active state: bright green pill using `--accent`, dark text for maximum contrast
- Inactive nav items: white at reduced opacity; hover moves toward full white
- Logo: bold white wordmark inside a subtle glassy panel

Nav items: Dashboard, Search, Meetings, Commitments, Insights

---

## Key Component Patterns

### Meeting Card
- Surface: `--bg-surface`, shadow: `--shadow-card`, radius: `lg`
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

- No noisy or high-contrast gradients that fight with content
- No harsh black text (always use `--ink-primary` / `--ink-secondary`, not `#000000`)
- No random extra accent colors outside the semantic palette
- No cramped tiles — cards should still have breathing room
- No monospace for non-data content (transcripts and timestamps only)
- No borders competing with shadows — choose one elevation method per element

---

## Changelog

- **2026‑03‑12 — Insightful Dashboard refresh**  
  - Switched from the earlier \"Quiet Intelligence\" warm off‑white palette to a light mint/blue dashboard palette.  
  - Updated base/background, accent, semantic, and shadow tokens while preserving all token names.  
  - Increased primary card radii and shadow depth to better match the reference dashboards.  
  - Adopted a dark navigation rail while keeping the main workspace light.
