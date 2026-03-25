# Pocket Nori
## Personal Intelligence Layer for the Working Professional
### Product Requirements Document

---

## 1. Problem Statement

Every organization runs on conversations. Decisions are made in meetings, refined over Slack, confirmed in emails, and committed to in standups. Yet no system exists that captures, connects, and surfaces the intelligence embedded in these conversations for the individual professional. Organizations already deploy Slack, email, Zoom, Google Meet, Asana, Monday, Jira, and a growing number of transcription services. The tooling landscape is not immature. What is missing is a personal memory layer that operates across all of these tools—a system that knows what an individual has discussed, decided, and committed to, regardless of where the conversation took place.

The result is a compounding productivity tax that affects every team, every role, and every day. Three structural problems define the scope of this tax.

### 1.1 The Problems

**Problem 1: Conversations are fragmented across channels, severing the continuity of decisions.**
Work conversations are distributed across video calls, Slack messages, email threads, and documents. A single decision may originate in a standup, get refined in a Slack thread, receive approval via email, and get modified in a follow-up call. No system captures the full arc. The consequence is not merely that information is scattered—it is that decisions lose their traceability. When someone asks "did we decide this, and why?", no one can produce a definitive answer because the decision trail is distributed across four tools, none of which reference each other. Decisions are revisited not because they were wrong, but because their existence and rationale cannot be located.

**Problem 2: Topic context is buried across time, making recurring discussions effectively unrecoverable.**
In recurring meetings such as daily standups, a topic may surface briefly across five or six sessions over several weeks. Each mention amounts to a few sentences buried in a separate transcript. No system reconstructs the chronological arc of that topic—what was proposed, what changed, what was committed to, and what was resolved. The information was captured at every stage. It is simply not retrievable in the temporal sequence that makes it useful. In practice, teams restart conversations from scratch, unaware that the same discussion has already occurred, and in some cases, already concluded.

**Problem 3: Context degrades at every audience boundary, with no mechanism to preserve fidelity across stakeholder groups.**
The same topic is discussed with customers in their language, with leadership in strategic terms, and with engineering in technical requirements. Each conversation happens independently. The connective tissue between them exists only in the working memory of whoever attended all three. This places a disproportionate burden on cross-functional professionals—product managers, marketing leads, operations teams—who function as manual translators of context between groups. Their absence from a single meeting creates a gap in the information chain. The problem is structural: organizations have no system to propagate context across audience boundaries, so they rely on individuals to do it in their heads, at scale, without loss.

### 1.2 The Cost

The cumulative effect of these three problems is a single, measurable organizational cost: decisions are systematically revisited. Not because the decisions were wrong, but because no individual can definitively point to where a decision was made, who made it, what alternatives were considered, and what the reasoning was. Time that should be spent executing is spent re-establishing consensus that already existed. The cost is not crises. It is delays—delays that compound across teams, across weeks, and across projects.

---

## 2. Product Vision

Pocket Nori is a personal intelligence layer for the working professional. It continuously captures context from a user's meetings and workspace, and makes that context searchable, synthesized, and actionable.

Pocket Nori operates on two layers. The first is context gathering: it captures and structures everything a professional discusses across their work—starting with meetings, expanding over time to include Slack, email, and other workspace tools. The second is intelligence: four distinct capabilities that transform raw context into productivity.

### 2.1 Intelligence Capabilities

**Topical search across time.** A user can query any keyword or topic and retrieve a synthesized view of everything discussed about it across all meetings and channels—not a list of transcripts, but a connected narrative of what was proposed, what changed, and where it stands.

**Cross-meeting connection.** Pocket Nori identifies when the same topic is being discussed across different meetings with different stakeholders. If a customer requests a feature in a sales call, and engineering discusses feasibility in a sprint review, Pocket Nori connects these threads—even if the user didn't think to look.

**Pre-meeting preparation.** Before a scheduled meeting, Pocket Nori delivers a briefing: what was discussed in the last session, what commitments were made, what has changed since, and what the user may need to address. This is pushed automatically, not pulled.

**Personal context dashboard.** A daily view of the user's work landscape—meetings ahead, recent decisions, outstanding commitments, and anything Pocket Nori has flagged as requiring attention.

### 2.2 What Pocket Nori Is

Pocket Nori is personal. Each user's view is their own—like their own Slack workspace or Figma account. Even if an entire organization adopts Pocket Nori, no user sees another user's aggregated context. Sharing is explicit and user-controlled.

### 2.3 What Pocket Nori Is Not

Pocket Nori is not a project management tool. It does not replace Asana, Monday, or Jira. It is not a team collaboration platform. It is not a transcription service, though transcription is a necessary input. Pocket Nori is what sits between all of these tools—the layer that remembers what you discussed, where you discussed it, and what you need to do about it.

### 2.4 Phased Input Expansion

Phase 1 begins with Google Workspace—specifically Google Meet—as the sole input source. Subsequent phases expand to additional channels and integrations.

---

## 3. Privacy & Data Principles

Privacy is not a feature of Pocket Nori. It is a design constraint that shapes every product and engineering decision. Because Pocket Nori ingests, structures, and reasons over a user's entire professional conversation history, the privacy model must be rigorous from day zero. Any compromise here undermines the core value proposition—if users do not trust that Pocket Nori is theirs alone, they will not give it access to their conversations.

**Principle 1: Personal by default, user-controlled sharing.**
Pocket Nori only processes conversations the user was a participant in. The aggregated intelligence view belongs to the user and is not visible to any other user, administrator, or Pocket Nori employee. When Pocket Nori generates an output that could be shared—such as a pre-meeting briefing—the user reviews and explicitly approves what is shared, with whom. No data crosses user boundaries without deliberate action. Sharing is always revocable.

**Principle 2: No model training on user data.**
User conversation data—including transcripts, summaries, and intelligence outputs—is never used to train, fine-tune, or improve any AI model, whether Pocket Nori's own or any third-party provider's. For internal MVP operation, Pocket Nori uses providers (Anthropic, OpenAI) whose standard API terms confirm no training on submitted data — this is a no-training policy, not a formal Zero Data Retention (ZDR) agreement. Before any external user onboards, a formal Data Processing Agreement (DPA) must be executed with every inference and embedding provider. The no-training policy is the floor for MVP; formal ZDR/DPA is required before production launch to external users.

**Principle 3: User ownership and deletion.**
The user owns all data generated through their use of Pocket Nori. Users can export or delete their data at any time. Deletion is immediate and irreversible—once deleted, the data cannot be recovered by Pocket Nori or any third party. There is no soft-delete, no grace period, and no archival retention beyond what the user explicitly chooses.

**Principle 4: No administrative visibility into individual intelligence.**
Even in organizational deployments, no manager, IT administrator, or workspace owner can view a user's aggregated intelligence, search history, or personal context dashboard. This is a hard architectural constraint, not a policy toggle. Pocket Nori does not build reporting, analytics, or oversight features that surface individual user data to anyone other than that user. This is a deliberate trade-off: it limits certain enterprise selling motions, but it preserves the trust model that makes the product worth using.

**Principle 5: Encryption and infrastructure standards.**
All data is encrypted using AES-256 at rest and TLS 1.2+ in transit. Infrastructure is hosted on SOC 2-compliant cloud providers. Access to production systems follows least-privilege principles with audit logging.

**Principle 6: Compliance roadmap.**
No compliance certifications are required for internal MVP testing. SOC 2 Type II certification is a Phase 3+ target — after the product reaches external users. Given Pocket Nori's UAE base, ADGM and DIFC data protection frameworks are relevant for regional enterprise customers and will be addressed during regional market expansion. GDPR readiness is required before any European user exposure. Compliance certifications will be pursued in sequence aligned with the market expansion roadmap.

---

## 4. Intelligence Layers — Detailed Specification

This section specifies the four intelligence capabilities introduced in the Product Vision. For each capability, the specification covers what the user experiences, what the system does, and what inputs are required.

### 4.1 Topical Search Across Time

**User experience.** The user enters a keyword or natural-language query—for example, "hackathon" or "what did we discuss about the Q2 launch?" Pocket Nori returns a synthesized narrative: when the topic was first raised, how the discussion evolved across meetings, what decisions were made, what commitments remain open, and where the topic currently stands. The output is not a list of transcript excerpts. It is a coherent summary that reconstructs the arc of the topic across time.

**System behavior.** Pocket Nori identifies all mentions of the queried topic across the user's indexed conversations, orders them chronologically, and passes the relevant fragments to the LLM with instructions to synthesize a narrative. The system must handle partial matches, synonyms, and context—a discussion about "community event planning" should surface when the user searches for "hackathon" if the two were discussed interchangeably. Each claim in the synthesized output should be traceable to a specific meeting and timestamp.

**Required inputs.** Indexed transcripts from all meetings the user participated in. In Phase 1, this is limited to Google Meet. In later phases, this extends to Slack messages, email threads, and other channels.

### 4.2 Cross-Meeting Connection

**User experience.** Pocket Nori surfaces connections the user did not explicitly search for. For example: the user had a customer call on Monday where the customer requested a reporting feature. On Wednesday, the user attended a product sprint review where engineering discussed the same feature's feasibility. Pocket Nori identifies the overlap and presents it—either in the personal dashboard or as a contextual note before the next relevant meeting. The user sees: "This topic was also discussed in [meeting name] on [date]. Here is what was said."

**System behavior.** After each new meeting is indexed, Pocket Nori runs a background process that compares topics, entities, and commitments from the new meeting against the user's existing conversation index. When a match is found with sufficient confidence, it is flagged and stored as a connection. Connections are surfaced in the dashboard and in pre-meeting briefings. The system must distinguish between genuine topical overlap and incidental keyword matches—discussing "budget" in an HR meeting and "budget" in a marketing meeting may or may not be related, and the system must use surrounding context to make that judgment.

**Required inputs.** Same as topical search. Cross-meeting connection is a background process that operates on the same indexed data. Its effectiveness scales with the breadth of channels indexed—the more conversation sources Pocket Nori has access to, the more connections it can identify.

### 4.3 Pre-Meeting Preparation

**User experience.** Approximately 10–15 minutes before a scheduled meeting, Pocket Nori pushes a briefing to the user. The briefing contains: a summary of what was discussed in the most recent session of this recurring meeting (if applicable), any commitments the user made that are due or relevant, any cross-meeting connections that may be pertinent, and a suggested agenda based on open threads from previous sessions. **In MVP, AI-generated Briefs are produced only for recurring meeting series with at least one prior indexed session.** For first-time or non-recurring meetings, Pocket Nori does not auto-generate a Brief — users can manually browse related context (past topics, commitments, relevant entities) via Search and the Meetings screen. Automatically generated Briefs for non-recurring meetings, drawing on participant history and calendar topic context, is a post-MVP feature.

**System behavior.** Pocket Nori monitors the user's calendar. For each upcoming meeting, it identifies whether the meeting is part of a recurring series, retrieves context from previous sessions, checks for open commitments or action items attributed to the user, queries the cross-meeting connection index for related discussions, and generates a briefing via the LLM. The briefing is delivered through the Pocket Nori interface and, optionally, via email or notification. The user can choose to share the briefing with other meeting attendees—this is the primary viral mechanism for PLG adoption.

**Required inputs.** Calendar access (Google Calendar in Phase 1), indexed transcripts from previous sessions of the same meeting series, and the cross-meeting connection index. The quality of the briefing improves with the volume of indexed context.

### 4.4 Personal Context Dashboard

**User experience.** The dashboard is the default view when a user opens Pocket Nori. It presents: today's meetings with brief context for each (what happened last time, what to expect), outstanding commitments the user has made across recent meetings, any cross-meeting connections flagged since the user last checked, and a recent activity feed showing meetings that have been indexed and key decisions extracted. The dashboard is not a task manager. It does not assign priorities or track completion. It provides awareness—a synthesized view of the user's conversational landscape.

**System behavior.** The dashboard aggregates outputs from the other three intelligence capabilities into a single view. It is generated on each load (or refreshed periodically) by querying the user's conversation index for recent activity, upcoming calendar events, and flagged items. Commitment extraction is an LLM-powered process that identifies statements like "I will send the proposal by Friday" and attributes them to the user with a due date.

**Required inputs.** All of the above: calendar access, indexed transcripts, cross-meeting connection index, and commitment extraction outputs.

---

## 5. Conceptual Data Model

Pocket Nori's intelligence capabilities operate on a defined set of core objects. This section describes the business-level information model — what Pocket Nori knows, how it is structured, and how the pieces relate. This is not a database schema; it is a conceptual map of the entities that the system reasons over.

### 5.1 Core Entities

**Conversation**
The atomic unit of capture. Any indexed interaction: a meeting, Slack thread, email chain, or document. A Conversation has: source platform, list of participants, start timestamp, duration, and raw transcript. In Phase 1, all Conversations are Google Meet sessions. Conversations are the foundation from which all other entities are derived.

**TranscriptSegment**
A single speaker utterance within a Conversation — the atomic unit of a transcript. A TranscriptSegment has: source Conversation ID, speaker ID, start timestamp (seconds from meeting start), end timestamp, utterance text, and a confidence score from the transcription provider. Every derived entity (Topic, Commitment, Connection) links back to one or more TranscriptSegments, enabling verifiable citations ("Murali said this at 14:23 in the March 5 standup"). TranscriptSegments are not a user-facing concept — they are the traceability layer that makes every intelligence output auditable. This entity must be built from Phase 0; retrofitting utterance-level storage later requires a schema migration and breaks citation quality.

**Topic**
A subject that recurs or persists across Conversations, identified and labeled by Pocket Nori's intelligence layer. Topics are not user-created — they emerge from the content of indexed Conversations. A Topic has: a label (e.g., "Q2 launch timeline"), the date it was first mentioned, the date it was last mentioned, a status (open or resolved), and a list of linked Conversations. The same real-world subject discussed under different names (e.g., "feature X" and "the reporting feature") may be unified into a single Topic if the system identifies them as semantically equivalent.

The system identifies topics through a cost-optimized 5-stage pipeline: heuristic transcript segmentation, deterministic entity extraction, two-tier candidate identification (deterministic scoring followed by targeted AI validation), rule-based filtering, and hybrid resolution against the existing topic graph. See `docs/specs/Topic_intelligence.md` for the full specification.

**Topic Arc**
A view over a Topic's linked Conversations, ordered chronologically. The Topic Arc is the output of Pocket Nori's topical search capability — not a list of excerpts, but a synthesized narrative: what was proposed, what changed, what was decided, and what remains open. Each claim in a Topic Arc is traceable to a specific Conversation and timestamp.

**Connection**
A detected relationship between two or more Conversations or Topics. A Connection is created when Pocket Nori identifies overlap in subject matter, referenced entities, or commitments across separate meetings — particularly when those meetings involved different stakeholder groups. Connections are surfaced proactively in the dashboard and in pre-meeting briefings. They are the primary mechanism by which Pocket Nori closes the gap between siloed discussions.

**Commitment**
A statement, extracted from a Conversation, in which the user indicates a future action. Commitments have: the extracted text, the user to whom it is attributed, a due date (if mentioned explicitly), the source Conversation, and a status (open or resolved). Example: "I will send the proposal by Friday" extracted from a client call on Tuesday. Commitments are surfaced in pre-meeting briefings and the personal context dashboard.

**Entity**
A deterministic fact extracted from transcript text — a named person, project, company, product, date, deadline, monetary value, artifact, or project code. Entities are extracted automatically using NLP pattern matching before any AI processing, and serve as a primary signal for topic resolution and cross-meeting connection detection — for example, linking a customer name mentioned in a sales call to a product feature discussed in a sprint review. Entities are not exposed directly as a user-facing concept; they are an internal enrichment layer.

**Brief**
A generated pre-meeting artifact composed from relevant Topic Arcs, open Commitments, flagged Connections, and calendar context for an upcoming meeting. A Brief belongs to the user who generated it. It is private by default. The user may choose to share it with other meeting attendees — this is an explicit action, and the only mechanism by which Pocket Nori content crosses user boundaries.

**Index**
The user's personal conversation store — the complete collection of Conversations, Topics, Connections, and Commitments indexed for a given user. The Index is architecturally isolated per user. No part of one user's Index is accessible by or derived from another user's data. The Index grows over time as new Conversations are captured and processed.

### 5.2 Entity Relationships

```
Index (per user)
├── Conversations [1..N]
│   ├── contains → Commitments [0..N]
│   └── references → Entities [0..N]
├── Topics [0..N]
│   └── linked to → Conversations [1..N]
├── Topic Arcs [0..N] (view over Topics × Conversations, ordered by time)
└── Connections [0..N]
    └── links → Conversations or Topics [2..N]

Brief
└── composed from → Topic Arcs + Commitments + Connections + Calendar event
```

The topic intelligence pipeline introduces intermediate representations (`DiscussionBlock`, `BlockCandidacy`, `CandidateTopic`) that are transient processing artifacts, not persisted entities. The canonical stored entity is `TopicNode`, which accumulates aliases, entities, keywords, and graph relationships over time.

### 5.3 Design Principles of the Model

**Conversation-first.** The model is organized around conversations as the primary input unit — not documents, tasks, or notes. This distinguishes Pocket Nori architecturally from note-taking tools (document-first) and project management tools (task-first).

**Derived, not created.** Topics, Connections, and Commitments are generated by the intelligence layer, not entered by the user. The user never manually tags a meeting or creates a topic — the system infers these from content. This is essential to Pocket Nori's value proposition: if users had to curate the model manually, the productivity benefit would be lost.

**Traceable to source.** Every derived entity — every Topic, Connection, Commitment, and Topic Arc — is traceable to a specific Conversation and timestamp. This traceability is what allows users to verify Pocket Nori's outputs and protects against the consequences of hallucination.

**Per-user isolation.** The Index is the fundamental privacy boundary. All entities exist within and belong to a user's Index. There is no shared entity store, no cross-user topic merging, and no global knowledge graph. When two users both attend the same meeting, each user has an independent Conversation record in their own Index.

---

## 6. User Journey

This section describes how a user discovers, adopts, and derives sustained value from Pocket Nori. The journey is designed for product-led growth: an individual signs up, experiences value independently, and organically introduces Pocket Nori to colleagues through shared outputs.

### 6.1 Discovery and Signup

A professional discovers Pocket Nori through one of two paths. The first is direct: they search for a tool to help them manage meeting overload, context switching, or conversation recall. The second is viral: they receive a pre-meeting briefing from a colleague who uses Pocket Nori. The briefing itself demonstrates the product's value—a concise, useful summary of what was discussed previously and what to expect. The recipient sees the Pocket Nori attribution and signs up. Signup requires a Google Workspace account (Phase 1). The user grants Pocket Nori access to Google Meet and Google Calendar. No organizational approval is required—Pocket Nori is a personal tool, and the permissions requested are scoped to the individual user's data.

### 6.2 First Value

After connecting Google Workspace, Pocket Nori begins indexing the user's meetings. The first moment of value occurs when the user receives a pre-meeting briefing before a recurring meeting—a summary of what was discussed last time, what they committed to, and what might come up. This requires at least two sessions of the same recurring meeting to be indexed. For users with heavy meeting loads, this value arrives within the first week. The second moment of value is the first successful topical search—the user queries a keyword and receives a synthesized view they could not have assembled manually without significant effort.

### 6.3 Sustained Value

Value compounds over time. As Pocket Nori indexes more meetings, the topical search becomes richer, cross-meeting connections become more frequent and more relevant, and pre-meeting briefings become more comprehensive. The user begins to rely on Pocket Nori as their default starting point before any meeting—checking what was discussed, what's due, and what's connected. The dashboard becomes a morning routine: open Pocket Nori, see the day's landscape, enter meetings prepared.

### 6.4 Viral Expansion

The primary viral mechanism is shared pre-meeting briefings. When a user shares a briefing with meeting attendees, each recipient experiences Pocket Nori's output without having an account. The briefing includes a Pocket Nori attribution and a signup prompt. In organizations where multiple individuals adopt Pocket Nori independently, the quality of cross-meeting connections improves—though each user's view remains private. Pocket Nori does not require organizational adoption to be useful. A single user gets full value from their own conversation history alone.

---

## 7. User Personas

Pocket Nori is designed for every professional who participates in regular meetings and communicates across multiple channels. The product is not limited to a specific role, industry, or team type. However, certain profiles will experience the sharpest pain and derive the earliest value.

### 7.1 Primary Audience

Professionals in companies with 50 or more employees who work asynchronously and meet regularly to synchronize. At this organizational size, the number of meetings, channels, and stakeholder groups creates a context management burden that individual memory cannot sustain. Smaller organizations may still benefit, but the problem is most acute at 50+ employees where cross-functional coordination becomes structurally necessary.

### 7.2 Initial Focus: Business Teams Over Technical Teams

Phase 1 prioritizes business teams—marketing, sales, operations, customer success, and general management. Technical teams (engineering, DevOps, infrastructure) tend to have more structured workflows, more objective deliverables, and more mature tooling for tracking work. Business teams, by contrast, operate in environments where discussions are more subjective, decisions are more distributed, and context is more likely to be carried verbally rather than documented in structured systems. This makes the context fragmentation problem more acute for business teams and the value of Pocket Nori more immediately apparent.

### 7.3 Persona Profiles

---

#### Persona 1: Layla — The Cross-Functional Operator

**Role:** Product Manager at a 200-person B2B SaaS company. Reports to the VP of Product. Works across engineering, design, marketing, and customer success on a daily basis.

**Day in the life.** Layla's calendar is a patchwork of team rituals — daily engineering standups, weekly design reviews, biweekly customer calls, and ad hoc stakeholder syncs. She is the person who attends the most meetings in any given week and the one expected to have the most complete picture of every initiative. She writes the PRDs, synthesizes user feedback from sales and CS, and translates it into engineering priorities. By Thursday of most weeks, she has absorbed enough information from enough separate meetings that she can no longer reliably reconstruct which decision was made where.

**Primary pains.**
- A feature request raised by a customer in a call two weeks ago was also discussed in the sprint planning meeting last week — but Layla can't easily connect those two conversations to build a complete picture before the next roadmap review.
- She spends 15–20 minutes before each customer call manually searching Slack and her own meeting notes to reconstruct what was discussed previously, with inconsistent results.
- When a team member asks "did we decide to include X in the next release?", Layla often knows the answer but can't point to where or when it was settled — which means the decision gets re-litigated.

**What they need from Pocket Nori.**
- *Topical search:* Query "feature X" before a roadmap meeting and get a full arc — when it was first raised, what engineering said about feasibility, what the customer said, and what was decided.
- *Cross-meeting connection:* Pocket Nori surfaces that the customer call and the sprint review both touched the same topic, so Layla sees the link without having to search for it.
- *Pre-meeting briefing:* Before each weekly sync, Layla receives what was discussed last session, what she committed to, and what's relevant from other meetings since then.
- *Dashboard:* A morning view of open commitments and flagged connections — a quick scan before the day begins.

**Adoption path.** Layla discovers Pocket Nori directly — she's actively looking for a tool to manage meeting context overload. She signs up with her Google Workspace account and connects Google Meet and Calendar. First value arrives within the first week when she receives a pre-meeting briefing before a recurring customer call.

**Success signal.** Layla stops starting customer calls by asking "where did we leave off?" She can answer "did we decide this?" questions in seconds, with a reference. She no longer re-reads old notes before meetings — she reads her Pocket Nori brief.

---

#### Persona 2: Marcus — The Client-Facing Professional

**Role:** Senior Account Manager at a mid-sized consulting firm. Manages 8–12 active client accounts simultaneously. Interfaces daily with clients externally and with delivery teams, leadership, and finance internally.

**Day in the life.** Marcus's week is split between external client calls — status updates, issue escalations, renewal conversations, upsell discussions — and internal meetings where he translates those conversations into deliverables for the delivery team. He is the single point of continuity between what the client says they need and what the team actually builds. His memory is the connective tissue between two worlds that never meet directly. When he's out sick or on leave, the information chain breaks.

**Primary pains.**
- After a client call, Marcus needs to brief the delivery lead on what was discussed — but the delivery lead was in three other meetings and can't process context verbally. Marcus ends up writing long recap emails that he's not sure anyone reads.
- He manages 10+ clients and cannot reliably remember what each one said in their last call without reviewing notes. Before renewal conversations, this becomes critical — forgetting a client's stated concern is a relationship risk.
- Internal leadership asks him to report on "client sentiment" across accounts — a synthesis task that currently requires Marcus to manually review notes across dozens of calls.

**What they need from Pocket Nori.**
- *Topical search:* Query a client name and get a synthesized view — every concern, request, and commitment across all interactions with that client.
- *Cross-meeting connection:* Pocket Nori links what a client said in Monday's call to what the delivery team discussed on Wednesday, so Marcus can see if the internal response addresses the client's actual concern.
- *Pre-meeting briefing:* Before each client call, Marcus receives a brief: what was discussed last time, what he committed to, what's changed since, and any relevant internal discussions. He enters calls prepared, not improvising.
- *Shared briefing:* Marcus shares a pre-meeting briefing with the client before a review session — demonstrating diligence and creating a natural Pocket Nori touchpoint.

**Adoption path.** Marcus discovers Pocket Nori after a colleague shares a pre-meeting briefing with him before a joint client call. He sees the output — a structured, contextual brief — and signs up. The viral mechanism is direct: the briefing is the demo.

**Success signal.** Marcus no longer writes recap emails after client calls — he shares a Pocket Nori brief. His pre-call preparation drops from 20 minutes to 3 minutes. When leadership asks about client sentiment, he can query across accounts in seconds.

---

#### Persona 3: Priya — The Overscheduled Executive

**Role:** VP of Operations at a PE-backed logistics company (~400 employees). Reports directly to the CEO. Responsible for supply chain, vendor management, customer operations, and internal process efficiency.

**Day in the life.** Priya is in back-to-back meetings from 8am to 6pm, four days a week. She attends cross-functional reviews, vendor negotiations, weekly leadership syncs, one-on-ones with her five direct reports, and ad hoc crisis calls when operations break down. She does not have time to review notes before most meetings — she walks into them relying on memory and whatever's in the calendar invite. Her most common experience is sitting in a meeting and realizing she cannot recall what was decided in the last session on this topic.

**Primary pains.**
- She misses commitments — not deliberately, but because they were made verbally in a meeting two weeks ago and never captured in a system she checks. This is professionally embarrassing and erodes her team's trust in her follow-through.
- She cannot tell her CEO, with confidence, what was discussed and decided in a given workstream last week — because the information is scattered across meeting notes she hasn't read, Slack threads she hasn't followed, and emails she's archived.
- She is the bottleneck for decisions because her team cannot move forward without her input — and she cannot give informed input without re-reading context she doesn't have time to re-read.

**What they need from Pocket Nori.**
- *Pre-meeting briefing:* This is Priya's primary use case. She needs to walk into every meeting knowing what was decided last time and what she committed to. She doesn't have time to prepare manually — she needs it pushed to her.
- *Commitment tracking:* Pocket Nori surfaces Priya's open commitments across all meetings. She reviews this list at the start and end of each week.
- *Topical search:* When her CEO asks "where are we on the vendor renegotiation?", Priya queries Pocket Nori and gets a summary she can relay in 60 seconds.
- *Dashboard:* A morning view that gives her the shape of the day and any flagged items — a 90-second scan before the day starts.

**Adoption path.** Priya is introduced to Pocket Nori by her EA or by a direct report who's already using it. Alternatively, she sees a briefing shared by a peer in a leadership meeting and asks about it. She is not a self-serve discoverer — she needs a trusted introduction. Once she sees the briefing format, adoption is immediate.

**Success signal.** Priya's missed commitments drop to zero. She enters every meeting with a briefing she's actually read. Her team notices she's better prepared and starts asking her fewer "do you remember when we decided...?" questions.

---

#### Persona 4: Tariq — The Independent Consultant

**Role:** Independent strategy consultant. Works with 3–5 clients simultaneously on 3–6 month engagements. Engagements typically involve senior stakeholder interviews, strategy workshops, and weekly status calls. He works alone — no team, no EA.

**Day in the life.** Tariq manages the full context load of multiple clients with no organizational infrastructure to support him. He has no team to delegate to, no shared knowledge base, and no one who attends meetings with him. Every piece of context captured in a client engagement lives in his head, his notes, or a folder of transcripts he rarely re-reads. He switches between clients multiple times per day — often going from a strategy call with Client A to a workshop debrief with Client B within the hour. Context bleed is a constant risk.

**Primary pains.**
- He occasionally mixes up details between clients — referencing something a different client said, or forgetting the specific language a stakeholder used about a sensitive issue. The professional consequences of these errors are significant.
- Before monthly executive check-ins, he spends 30–45 minutes reviewing notes from the previous month — time that is not billed and cannot scale if he takes on more clients.
- He cannot demonstrate to clients the depth of his listening and recall in a systematic way — the occasional "I remembered what you said about X three weeks ago" moment is powerful but inconsistent.

**What they need from Pocket Nori.**
- *Pre-meeting briefing:* Before each client meeting, Tariq receives a brief: what was discussed in the last session, what commitments he made, and what connections exist between this client's discussions and prior conversations. He enters every meeting prepared without the 30-minute manual review.
- *Topical search:* Query a client name or a project topic and get a complete arc of that thread — essential for month-end reviews and final deliverable drafting.
- *Per-client Index:* Because each client's data is in the same Index (Tariq has one account), Pocket Nori must be reliable about attributing context correctly. Cross-client connections should only surface when explicitly queried, not proactively — Tariq does not want client B's context bleeding into client A's brief.
- *Shared briefing:* Tariq occasionally shares a structured brief with a senior client stakeholder before a monthly review — demonstrating rigor and prompting the client to confirm what's in scope.

**Adoption path.** Tariq discovers Pocket Nori directly, through search or professional networks. He is an early adopter profile — high pain, high willingness to try new tools, and enough technical comfort to evaluate a PLG product independently. He will adopt if the free experience delivers value within the first two weeks.

**Success signal.** Tariq's pre-meeting preparation time drops from 30–45 minutes to under 5 minutes. He never mixes up client context. He uses a Pocket Nori brief in a client review meeting and the client explicitly comments on how organized the session is.

---

## 8. Phased Roadmap

Pocket Nori is built in phases, each expanding the breadth of context gathered and the depth of intelligence delivered. Each phase must demonstrate standalone value—no phase is justified solely as a prerequisite for the next.

### 8.1 Phase 1: Google Workspace Foundation

**Input sources:** Google Meet (transcription), Google Calendar (scheduling and meeting metadata).

**Intelligence capabilities:**
- Topical search across indexed Google Meet transcripts
- Pre-meeting briefings for recurring meetings based on past session context
- Personal context dashboard showing today's meetings, recent decisions, and outstanding commitments
- Basic commitment extraction from meeting transcripts

**What this phase proves:** That professionals derive meaningful value from an intelligence layer built on meeting transcripts alone. That pre-meeting briefings are compelling enough to drive viral adoption. That the privacy model is viable for PLG distribution.

### 8.2 Phase 2: Multi-Channel Expansion

**Input sources:** Slack messages and threads, Gmail, Google Docs (referenced in meetings or threads). Potentially Zoom and Microsoft Teams for cross-platform meeting coverage.

**Intelligence capabilities:** Cross-meeting connection now includes Slack and email context. Topical search spans meetings, Slack, and email. Pre-meeting briefings incorporate async context—if a relevant Slack thread occurred between meetings, it appears in the briefing. The async-sync boundary (Problem Statement, Problem 1) begins to close.

**What this phase proves:** That cross-channel intelligence is materially more valuable than meeting-only intelligence. That users are willing to grant Pocket Nori access to additional channels once trust is established in Phase 1.

### 8.3 Phase 3: Full Intelligence

**Input sources:** All Phase 2 sources plus integration with project management tools (Asana, Monday, Jira, ClickUp) as read-only context sources—not to manage tasks, but to enrich intelligence with structured project data.

**Intelligence capabilities:** Proactive intelligence reaches full capability—Pocket Nori can connect a customer request from a call to a Jira ticket in the backlog to a Slack discussion about prioritization, and surface this to the user before the relevant meeting. Commitment tracking becomes more robust with project management data as a validation source. The dashboard evolves into a comprehensive daily work intelligence view.

**What this phase proves:** That Pocket Nori can serve as the connective layer across an entire professional's toolset without becoming a project management tool itself.

---

## 9. Competitive Landscape

The meeting intelligence and personal productivity AI market is growing rapidly. This section summarizes the competitive context in quantitative terms. Full competitive profiles, feature comparison, and strategic analysis are maintained in `competitive-analysis.md`.

### 9.1 Market Size & Growth

The global AI meeting assistant and transcription market was valued at approximately **$1.5B in 2024** and is projected to grow at a CAGR of **25–30%** through 2030, reaching an estimated **$6–8B** by end of decade (MarketsandMarkets, Grand View Research). Growth is driven by:

- Proliferation of hybrid and remote work, increasing reliance on recorded/transcribed meetings
- Enterprise AI adoption budgets expanding post-2023 LLM wave
- Growing demand for individual productivity tools alongside team-oriented platforms

The broader **workplace intelligence and knowledge management** TAM — which includes tools that connect meetings, documents, emails, and workflows — is substantially larger, estimated at **$15–20B by 2027** (IDC). Pocket Nori is positioned to compete in both the meeting intelligence segment (Phase 1) and the broader workplace intelligence segment (Phases 2–3).

### 9.2 Competitor Pricing Reference

| Competitor | Free Tier | Entry Paid | Mid Tier | Notes |
|---|---|---|---|---|
| **Limitless** | 10 hrs AI/month | $20/month | $399 one-time (pendant bundle) | Hardware wearable add-on |
| **Mem.ai** | 25 notes/month | $12/month | Custom (Teams) | Note-centric, not meeting-centric |
| **Otter.ai** | 300 min/month | $8.33–$16.99/seat/month | $20–30/seat/month | Minute caps on all plans |
| **Fireflies.ai** | Basic transcription | $10/month | $19/month | Enterprise custom |
| **Fathom** | Unlimited recordings | $15/month | $29/seat/month | Best free tier in category |
| **tl;dv** | Unlimited meetings, 10 AI notes | $18/month | $59/seat/month | Cross-meeting reports at Business tier |
| **Granola** | Limited | $18/month | — | Mac/Windows desktop only |
| **MS Copilot** | Included in M365 | Teams Premium add-on (~$10/user/month) | — | Ecosystem-locked to Microsoft |
| **Google Gemini** | Included in Workspace | — | — | Google Meet only |

*Pricing as of Q1 2026. Subject to change.*

### 9.3 Funding Reference

Notable funding rounds in the space, indicating competitive momentum and investor conviction:

| Company | Funding (total known) | Stage | Notable investors |
|---|---|---|---|
| **Otter.ai** | ~$63M | Series B | Dragoneer, GGV Capital |
| **Fireflies.ai** | ~$19M | Series A | Khosla Ventures |
| **Limitless** | ~$13M | Seed/Series A | a16z, General Catalyst |
| **tl;dv** | ~$9M | Seed | Various |
| **Mem.ai** | ~$29M | Series A | Andreessen Horowitz |

The category is well-funded but no single player has achieved dominant market share. The personal intelligence segment — where Pocket Nori competes — remains the least crowded and the least capitalized, representing both opportunity and the need for Pocket Nori to move quickly to establish positioning.

---

## 10. Open Questions

The following questions remain unresolved and require further research, user validation, or strategic decision-making before they can be incorporated into the product specification.

1. **Monetization model.** Pocket Nori is a PLG product, but the pricing structure is undefined. Key questions include: what triggers conversion from free to paid? Is the gate based on volume (number of meetings indexed), capability (advanced intelligence features), or time (trial period)? How is pricing structured—per user per month, usage-based, or tiered?

2. **Meeting consent and bot presence.** Many organizations are increasingly resistant to AI bots joining meetings. Pocket Nori must define its approach: does it join meetings as a visible bot (like Fireflies or Otter), operate through native Google Meet transcription APIs without a visible presence, or offer both options? The choice affects user trust, organizational adoption friction, and data quality.

3. **Accuracy and hallucination risk.** Pocket Nori's intelligence capabilities are LLM-powered. The risk of generating inaccurate summaries, false connections, or hallucinated commitments is real. A user who acts on a Pocket Nori-generated briefing that contains an error may face professional consequences. The threshold for accuracy must be defined, and the system must make it easy for users to verify claims against source transcripts.

4. **Cold start problem.** Pocket Nori's value scales with the volume of indexed context. A new user has no history. How does Pocket Nori deliver value in the first 48 hours before enough meetings have been indexed to power meaningful intelligence? Options include retroactive indexing of past Google Meet recordings (if available), a guided onboarding that sets expectations, or a lightweight utility (simple transcript search) that provides immediate value while the intelligence layer accumulates data.

5. **Multi-language support.** Given the UAE base and global PLG ambitions, meetings may occur in English, Arabic, Hindi, or other languages—sometimes within the same meeting. The transcription and intelligence layers must handle multilingual input. The feasibility and accuracy of this in Phase 1 needs assessment.

6. **Intellectual property and legal exposure.** Pocket Nori processes and stores conversation data that may contain confidential business information, trade secrets, or legally privileged discussions. The legal framework governing Pocket Nori's liability—particularly in the event of a data breach or an erroneous intelligence output that leads to a business decision—requires legal review.

7. **Competitive response.** Read AI is well-funded, fast-moving, and already building toward a similar vision. Pocket Nori's personal-first architecture is a differentiation today, but Read AI could add a personal mode. The durability of this differentiation needs to be assessed, and a strategy for sustained defensibility beyond the privacy model should be developed.

---

## 11. Technical Architecture Overview

This section outlines the build-versus-buy decisions that define Pocket Nori's technical approach. Pocket Nori's engineering effort is concentrated on the orchestration, retrieval, and intelligence layers—not on foundational AI infrastructure.

### 11.1 Speech-to-Text: Buy

Pocket Nori does not build transcription models. Phase 1 uses the Google Drive API to enumerate and retrieve past Google Meet recordings (stored automatically in Drive for Google Workspace accounts). Recordings are fetched transiently, transcribed via Deepgram Nova-3, then discarded — never stored in Pocket Nori's infrastructure. Google Meet's native captions were evaluated and rejected: they lack speaker diarization, have lower accuracy on technical and business vocabulary, and provide no API for programmatic retrieval. For Phase 3 (Electron desktop app) and cross-platform coverage (Zoom, Microsoft Teams, in-person), Deepgram real-time streaming WebSocket is the transcription engine. The choice of provider will be evaluated against accuracy, language support, latency, cost, and privacy posture — particularly whether self-hosting is viable to keep audio data off third-party infrastructure entirely.

### 11.2 LLM Inference: Buy

Pocket Nori does not build or train large language models. Intelligence capabilities—summarization, topical search synthesis, cross-meeting connection, and pre-meeting briefing generation—are powered by existing LLM APIs (Anthropic Claude, OpenAI GPT, Google Gemini, or equivalent). All LLM providers must operate under zero-data-retention agreements, ensuring that conversation data processed for inference is not stored, logged, or used for model improvement. The intelligence layer's value is in the orchestration logic—what context is retrieved, how it is structured for the model, and how the output is presented to the user—not in the model itself.

### 11.3 Storage and Indexing: Build

The core engineering effort is the conversation data layer—how transcripts and workspace data are ingested, structured, indexed, and made retrievable. This includes temporal indexing (tracking a topic's evolution across time), cross-meeting linking (connecting related discussions across separate meetings and channels), and per-user isolation (ensuring each user's data is architecturally separated). This layer is Pocket Nori's primary technical asset.

### 11.4 Intelligence Orchestration: Build

The retrieval and reasoning layer that sits between the data store and the LLM—determining what context to pull, how to construct prompts, how to synthesize multi-meeting information, and how to generate actionable outputs (briefings, search results, dashboard content). This is where product differentiation lives.

### 11.5 User Interface: Build

The web and mobile application through which users interact with Pocket Nori—the personal dashboard, search, meeting briefings, and sharing controls. Designed for individual use, not team administration.
