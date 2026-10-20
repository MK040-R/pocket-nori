import type {
  BriefDetail,
  ChatCitation,
  ChatMessage,
  ChatSessionSummary,
  Commitment,
  ConversationConnection,
  ConversationDetail,
  ConversationSummary,
  EntitySummary,
  HomeDashboard,
  IndexStats,
  RecordingItem,
  SearchResult,
  TodayBriefing,
  TopicArc,
  TopicDetail,
  TopicSummary,
  UpcomingBrief,
} from "@/lib/api";
import type { MeetingCategory } from "@/lib/meeting-categories";

// Fictional dataset. Dates are relative to "now" so the demo always looks current.
const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgo(days: number, hour = 10): string {
  const date = new Date(Date.now() - days * DAY_MS);
  date.setHours(hour, 0, 0, 0);
  return date.toISOString();
}

function hoursFromNow(hours: number): string {
  return new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
}

function dateOnly(daysFromNow: number): string {
  return new Date(Date.now() + daysFromNow * DAY_MS).toISOString().slice(0, 10);
}

export const DEMO_SESSION = { user_id: "demo-user", email: "priya.raman@northwind.dev" };

type DemoSegment = { speaker: string; text: string };

type DemoMeeting = {
  id: string;
  title: string;
  daysAgo: number;
  durationMin: number;
  category: MeetingCategory;
  topicIds: string[];
  segments: DemoSegment[];
};

type DemoTopic = {
  id: string;
  label: string;
  summary: string;
  status: "open" | "resolved";
  trend: TopicArc["trend"];
  keyQuotes: string[];
  arc: Record<string, string>;
};

const TOPICS: DemoTopic[] = [
  {
    id: "t-pricing",
    label: "Q4 pricing revamp",
    summary:
      "Moving from per-seat to usage-based pricing for the Analytics tier. Finance wants a floor price; Sales worries about mid-market churn. Decision: pilot usage pricing with 10 accounts before a full rollout.",
    status: "open",
    trend: "growing",
    keyQuotes: [
      "If we go usage-based we need a floor, otherwise small accounts become unprofitable. — Daniel",
      "Let's pilot with ten accounts and look at churn signals before committing. — Priya",
    ],
    arc: {
      "m-strategy": "Usage-based pricing proposed for the Analytics tier; Finance flags margin risk on small accounts.",
      "m-acme-qbr": "Acme asks whether pricing will change at renewal — Priya avoids committing until the pilot.",
      "m-leadership": "Leadership agrees to a 10-account pilot with a $499/month floor.",
      "m-sales-sync": "Sales picks the 10 pilot accounts; two mid-market accounts flagged as churn risk.",
    },
  },
  {
    id: "t-acme",
    label: "Acme Corp onboarding",
    summary:
      "Acme's 400-seat rollout is blocked on SSO configuration and a data residency question. Engineering committed an EU region by end of month.",
    status: "open",
    trend: "stable",
    keyQuotes: [
      "Our security team won't sign off without EU data residency. — Sarah (Acme)",
      "We can have the EU region live by the 30th. — Marcus",
    ],
    arc: {
      "m-acme-kickoff": "Acme kickoff: 400 seats, SSO via Okta, rollout in three waves.",
      "m-acme-qbr": "Acme raises EU data residency as a hard blocker for wave two.",
      "m-eng-standup": "Engineering scopes the EU region; Marcus commits to the 30th.",
    },
  },
  {
    id: "t-perf",
    label: "Dashboard load time",
    summary:
      "P95 dashboard load regressed to 4.2s after the charts migration. Root cause was N+1 queries on the widgets endpoint; fix shipped and P95 is back to 1.1s.",
    status: "resolved",
    trend: "resolved",
    keyQuotes: [
      "P95 is 4.2 seconds, customers are noticing. — Aisha",
      "Batched the widget queries, P95 is down to 1.1s in prod. — Marcus",
    ],
    arc: {
      "m-eng-standup": "Aisha reports P95 dashboard load at 4.2s after the charts migration.",
      "m-1on1-marcus": "Marcus traces it to N+1 queries on the widgets endpoint.",
      "m-eng-retro": "Fix shipped; P95 back to 1.1s. Topic closed.",
    },
  },
  {
    id: "t-hiring",
    label: "Senior data engineer hire",
    summary:
      "Opening a senior data engineer role to own the ingestion pipeline. Two finalists; offer decision pending reference checks.",
    status: "open",
    trend: "stable",
    keyQuotes: ["We need someone who has run Kafka-scale ingestion before. — Marcus"],
    arc: {
      "m-1on1-marcus": "Marcus asks for a senior data engineer to own ingestion.",
      "m-leadership": "Headcount approved for one senior data engineer.",
    },
  },
  {
    id: "t-soc2",
    label: "SOC 2 Type II audit",
    summary:
      "Audit window opens next quarter. Gaps: access reviews and vendor risk assessments. Acme's security review depends on it.",
    status: "open",
    trend: "growing",
    keyQuotes: ["Acme's procurement will ask for the SOC 2 report in wave two. — Priya"],
    arc: {
      "m-acme-qbr": "Acme procurement will require the SOC 2 report before wave two.",
      "m-leadership": "SOC 2 Type II prioritised; access reviews are the biggest gap.",
      "m-eng-retro": "Engineering assigns owners for access-review automation.",
    },
  },
];

const MEETINGS: DemoMeeting[] = [
  {
    id: "m-sales-sync",
    title: "Sales × Product weekly sync",
    daysAgo: 1,
    durationMin: 30,
    category: "team",
    topicIds: ["t-pricing"],
    segments: [
      { speaker: "Priya", text: "Goal today is to lock the ten pilot accounts for usage-based pricing." },
      { speaker: "Jordan", text: "I've got eight confirmed. Brightline and Coastal are the two I'm nervous about — both mid-market, both price sensitive." },
      { speaker: "Priya", text: "Keep them in. If they churn under the pilot, that's exactly the signal we need before a full rollout." },
      { speaker: "Jordan", text: "Fine. I'll send the pilot terms to all ten by Friday." },
    ],
  },
  {
    id: "m-leadership",
    title: "Leadership staff meeting",
    daysAgo: 3,
    durationMin: 60,
    category: "strategy",
    topicIds: ["t-pricing", "t-hiring", "t-soc2"],
    segments: [
      { speaker: "Elena", text: "Three items: pricing pilot, the data engineering headcount, and SOC 2." },
      { speaker: "Daniel", text: "On pricing, I'm comfortable with a pilot if we set a floor. I'd propose $499 a month." },
      { speaker: "Priya", text: "Agreed. Ten accounts, $499 floor, we review churn signals after one billing cycle." },
      { speaker: "Elena", text: "Approved. Marcus, you get the senior data engineer headcount." },
      { speaker: "Elena", text: "SOC 2 Type II is now a priority — Acme's wave two depends on it. Access reviews are our biggest gap." },
    ],
  },
  {
    id: "m-eng-retro",
    title: "Engineering sprint retro",
    daysAgo: 5,
    durationMin: 45,
    category: "team",
    topicIds: ["t-perf", "t-soc2"],
    segments: [
      { speaker: "Marcus", text: "Good news first: batched the widget queries, P95 dashboard load is down to 1.1 seconds in prod." },
      { speaker: "Aisha", text: "Confirmed from the customer side, support tickets about slowness dropped to zero this week." },
      { speaker: "Marcus", text: "For SOC 2, I'll own access-review automation. Aisha takes vendor risk assessments." },
    ],
  },
  {
    id: "m-acme-qbr",
    title: "Acme Corp — quarterly business review",
    daysAgo: 8,
    durationMin: 50,
    category: "client",
    topicIds: ["t-acme", "t-pricing", "t-soc2"],
    segments: [
      { speaker: "Sarah (Acme)", text: "Wave one went well. For wave two, our security team won't sign off without EU data residency." },
      { speaker: "Priya", text: "Understood. I'll come back with a firm date from engineering this week." },
      { speaker: "Sarah (Acme)", text: "Also — is pricing changing at renewal? We've heard rumours about usage-based." },
      { speaker: "Priya", text: "We're evaluating it, nothing changes for existing contracts before renewal. I'll keep you posted." },
      { speaker: "Sarah (Acme)", text: "And procurement will need your SOC 2 report before we expand." },
    ],
  },
  {
    id: "m-eng-standup",
    title: "Engineering standup",
    daysAgo: 9,
    durationMin: 15,
    category: "team",
    topicIds: ["t-acme", "t-perf"],
    segments: [
      { speaker: "Aisha", text: "Heads up, P95 dashboard load is at 4.2 seconds since the charts migration. Customers are noticing." },
      { speaker: "Priya", text: "Separate item: Acme needs EU data residency for wave two. What's realistic?" },
      { speaker: "Marcus", text: "We can have the EU region live by the 30th if nothing else jumps the queue." },
    ],
  },
  {
    id: "m-1on1-marcus",
    title: "1:1 Priya / Marcus",
    daysAgo: 12,
    durationMin: 30,
    category: "1on1",
    topicIds: ["t-perf", "t-hiring"],
    segments: [
      { speaker: "Marcus", text: "Traced the dashboard regression — it's N+1 queries on the widgets endpoint. Fix is straightforward." },
      { speaker: "Marcus", text: "Bigger issue: nobody owns ingestion. We need a senior data engineer who has run Kafka-scale pipelines." },
      { speaker: "Priya", text: "I'll take the headcount request to leadership next week." },
    ],
  },
  {
    id: "m-strategy",
    title: "Analytics tier pricing strategy",
    daysAgo: 16,
    durationMin: 60,
    category: "strategy",
    topicIds: ["t-pricing"],
    segments: [
      { speaker: "Priya", text: "Proposal: move the Analytics tier from per-seat to usage-based pricing." },
      { speaker: "Daniel", text: "If we go usage-based we need a floor, otherwise small accounts become unprofitable." },
      { speaker: "Priya", text: "Let's pilot with ten accounts and look at churn signals before committing." },
    ],
  },
  {
    id: "m-acme-kickoff",
    title: "Acme Corp — onboarding kickoff",
    daysAgo: 20,
    durationMin: 45,
    category: "client",
    topicIds: ["t-acme"],
    segments: [
      { speaker: "Sarah (Acme)", text: "We're rolling out to 400 seats across three waves. SSO through Okta is a must." },
      { speaker: "Priya", text: "Okta SSO is supported. We'll set up a shared channel and a weekly check-in." },
    ],
  },
];

const COMMITMENTS: Array<Omit<Commitment, "conversation_title" | "meeting_date" | "topic_labels"> & { topicIds: string[] }> = [
  { id: "c-1", text: "Send usage-based pilot terms to all ten pilot accounts", owner: "Jordan", due_date: dateOnly(2), status: "open", action_type: "commitment", conversation_id: "m-sales-sync", topicIds: ["t-pricing"] },
  { id: "c-2", text: "Share a firm EU region date with Acme", owner: "Priya", due_date: dateOnly(-1), status: "open", action_type: "follow_up", conversation_id: "m-acme-qbr", topicIds: ["t-acme"] },
  { id: "c-3", text: "Ship EU data residency region", owner: "Marcus", due_date: dateOnly(9), status: "open", action_type: "commitment", conversation_id: "m-eng-standup", topicIds: ["t-acme"] },
  { id: "c-4", text: "Automate quarterly access reviews for SOC 2", owner: "Marcus", due_date: dateOnly(21), status: "open", action_type: "commitment", conversation_id: "m-eng-retro", topicIds: ["t-soc2"] },
  { id: "c-5", text: "Complete vendor risk assessments", owner: "Aisha", due_date: dateOnly(14), status: "open", action_type: "commitment", conversation_id: "m-eng-retro", topicIds: ["t-soc2"] },
  { id: "c-6", text: "Update Acme on pricing plans before renewal", owner: "Priya", due_date: dateOnly(30), status: "open", action_type: "follow_up", conversation_id: "m-acme-qbr", topicIds: ["t-pricing", "t-acme"] },
  { id: "c-7", text: "Fix N+1 queries on widgets endpoint", owner: "Marcus", due_date: dateOnly(-6), status: "resolved", action_type: "commitment", conversation_id: "m-1on1-marcus", topicIds: ["t-perf"] },
  { id: "c-8", text: "Take data engineer headcount request to leadership", owner: "Priya", due_date: dateOnly(-4), status: "resolved", action_type: "commitment", conversation_id: "m-1on1-marcus", topicIds: ["t-hiring"] },
];

const ENTITIES: EntitySummary[] = [
  { name: "Acme Corp", type: "company", mentions: 14, conversation_count: 3 },
  { name: "Marcus Lee", type: "person", mentions: 12, conversation_count: 5 },
  { name: "Analytics tier", type: "product", mentions: 9, conversation_count: 4 },
  { name: "Daniel Okafor", type: "person", mentions: 6, conversation_count: 2 },
  { name: "Sarah Chen", type: "person", mentions: 6, conversation_count: 2 },
  { name: "SOC 2 Type II", type: "project", mentions: 5, conversation_count: 3 },
  { name: "Aisha Patel", type: "person", mentions: 5, conversation_count: 3 },
  { name: "EU data region", type: "project", mentions: 4, conversation_count: 2 },
  { name: "Jordan Brooks", type: "person", mentions: 3, conversation_count: 1 },
  { name: "Okta", type: "company", mentions: 2, conversation_count: 1 },
];

const meetingById = new Map(MEETINGS.map((m) => [m.id, m]));
const topicById = new Map(TOPICS.map((t) => [t.id, t]));

function meetingDate(meeting: DemoMeeting): string {
  return daysAgo(meeting.daysAgo);
}

function topicLabels(ids: string[]): string[] {
  return ids.map((id) => topicById.get(id)?.label ?? id);
}

function toCommitment(item: (typeof COMMITMENTS)[number]): Commitment {
  const meeting = meetingById.get(item.conversation_id);
  return {
    id: item.id,
    text: item.text,
    owner: item.owner,
    due_date: item.due_date,
    status: item.status,
    action_type: item.action_type,
    conversation_id: item.conversation_id,
    conversation_title: meeting?.title ?? "",
    meeting_date: meeting ? meetingDate(meeting) : null,
    topic_labels: topicLabels(item.topicIds),
  };
}

export function demoCommitments(): Commitment[] {
  return COMMITMENTS.map(toCommitment);
}

export function demoConversations(): ConversationSummary[] {
  return MEETINGS.map((m) => ({
    id: m.id,
    title: m.title,
    source: "google_drive",
    meeting_date: meetingDate(m),
    duration_seconds: m.durationMin * 60,
    status: "indexed",
    topic_labels: topicLabels(m.topicIds),
    category: m.category,
    latest_brief_id: m.id === "m-acme-qbr" ? "b-acme" : null,
    latest_brief_generated_at: m.id === "m-acme-qbr" ? daysAgo(0, 8) : null,
  }));
}

export function demoConnections(meetingId: string): ConversationConnection[] {
  const meeting = meetingById.get(meetingId);
  if (!meeting) {
    return [];
  }
  return MEETINGS.filter((other) => other.id !== meetingId)
    .map((other) => ({ other, shared: other.topicIds.filter((id) => meeting.topicIds.includes(id)) }))
    .filter(({ shared }) => shared.length > 0)
    .slice(0, 4)
    .map(({ other, shared }) => ({
      id: `conn-${meetingId}-${other.id}`,
      linked_type: "conversation",
      label: topicLabels(shared).join(", "),
      summary: topicById.get(shared[0])?.arc[other.id] ?? "Discussed a shared topic.",
      connected_conversation_id: other.id,
      connected_conversation_title: other.title,
      connected_meeting_date: meetingDate(other),
      shared_topics: topicLabels(shared),
      shared_entities: [],
      shared_commitments: [],
    }));
}

export function demoConversationDetail(id: string): ConversationDetail | null {
  const meeting = meetingById.get(id);
  if (!meeting) {
    return null;
  }
  const segmentLengthMs = Math.floor((meeting.durationMin * 60 * 1000) / meeting.segments.length);
  return {
    conversation: {
      id: meeting.id,
      title: meeting.title,
      meeting_date: meetingDate(meeting),
      duration_seconds: meeting.durationMin * 60,
      category: meeting.category,
      latest_brief_id: meeting.id === "m-acme-qbr" ? "b-acme" : null,
      latest_brief_generated_at: meeting.id === "m-acme-qbr" ? daysAgo(0, 8) : null,
    },
    topics: meeting.topicIds.map((topicId) => {
      const topic = topicById.get(topicId)!;
      return {
        id: topic.id,
        label: topic.label,
        summary: topic.arc[meeting.id] ?? topic.summary,
        status: topic.status,
        key_quotes: topic.keyQuotes.slice(0, 1),
      };
    }),
    commitments: COMMITMENTS.filter((c) => c.conversation_id === meeting.id).map((c) => ({
      id: c.id,
      text: c.text,
      owner: c.owner,
      due_date: c.due_date,
      status: c.status,
      action_type: c.action_type,
    })),
    entities: ENTITIES.filter((e) =>
      meeting.segments.some((s) => s.text.includes(e.name.split(" ")[0]) || s.speaker.includes(e.name.split(" ")[0])),
    ).map((e, index) => ({ id: `e-${index}`, name: e.name, type: e.type, mentions: Math.max(1, Math.round(e.mentions / 3)) })),
    segments: meeting.segments.map((s, index) => ({
      id: `${meeting.id}-s${index}`,
      speaker_id: s.speaker,
      start_ms: index * segmentLengthMs,
      end_ms: (index + 1) * segmentLengthMs,
      text: s.text,
    })),
    connections: demoConnections(meeting.id),
  };
}

export function demoTopics(): TopicSummary[] {
  return TOPICS.map((t) => {
    const meetings = MEETINGS.filter((m) => m.topicIds.includes(t.id));
    return {
      id: t.id,
      label: t.label,
      conversation_count: meetings.length,
      latest_date: meetingDate(meetings.reduce((a, b) => (a.daysAgo < b.daysAgo ? a : b))),
    };
  });
}

export function demoTopicDetail(id: string): TopicDetail | null {
  const topic = topicById.get(id);
  if (!topic) {
    return null;
  }
  return {
    id: topic.id,
    label: topic.label,
    summary: topic.summary,
    status: topic.status,
    key_quotes: topic.keyQuotes,
    conversations: MEETINGS.filter((m) => m.topicIds.includes(id)).map((m) => ({
      id: m.id,
      title: m.title,
      meeting_date: meetingDate(m),
    })),
  };
}

export function demoTopicArc(id: string): TopicArc | null {
  const topic = topicById.get(id);
  if (!topic) {
    return null;
  }
  const bestSegment = (m: DemoMeeting): number => {
    const words = new Set(`${topic.label} ${topic.arc[m.id]}`.toLowerCase().match(/[a-z0-9$]{3,}/g) ?? []);
    let best = 0;
    let bestScore = -1;
    m.segments.forEach((seg, index) => {
      const score = (seg.text.toLowerCase().match(/[a-z0-9$]{3,}/g) ?? []).filter((w) => words.has(w)).length;
      if (score > bestScore) {
        best = index;
        bestScore = score;
      }
    });
    return best;
  };
  const points = MEETINGS.filter((m) => topic.arc[m.id])
    .sort((a, b) => b.daysAgo - a.daysAgo)
    .map((m, index, all) => ({
      topic_id: topic.id,
      conversation_id: m.id,
      conversation_title: m.title,
      occurred_at: meetingDate(m),
      summary: topic.arc[m.id],
      topic_status: topic.status === "resolved" && index === all.length - 1 ? ("resolved" as const) : ("open" as const),
      citation_segment_id: `${m.id}-s${bestSegment(m)}`,
      transcript_offset_seconds: Math.floor((bestSegment(m) * m.durationMin * 60) / m.segments.length),
      citation_snippet: m.segments[bestSegment(m)]?.text ?? null,
    }));
  return {
    id: `arc-${topic.id}`,
    topic_id: topic.id,
    label: topic.label,
    summary: topic.summary,
    status: topic.status,
    trend: topic.trend,
    conversation_count: points.length,
    arc_points: points,
  };
}

export function demoEntities(): EntitySummary[] {
  return ENTITIES;
}

export function demoIndexStats(): IndexStats {
  return {
    conversation_count: MEETINGS.length,
    topic_count: TOPICS.length,
    commitment_count: COMMITMENTS.filter((c) => c.status === "open").length,
    entity_count: ENTITIES.length,
    last_updated_at: daysAgo(0, 8),
  };
}

const UPCOMING = [
  { id: "ev-acme", title: "Acme Corp — wave two planning", start: 2, attendees: ["Sarah Chen", "Marcus Lee", "Priya Raman"] },
  { id: "ev-pricing", title: "Pricing pilot check-in", start: 5, attendees: ["Daniel Okafor", "Jordan Brooks", "Priya Raman"] },
];

export function demoUpcomingBriefs(): UpcomingBrief[] {
  return [
    {
      brief_id: "b-acme",
      conversation_id: "m-acme-qbr",
      calendar_event_id: "ev-acme",
      event_title: UPCOMING[0].title,
      event_start: hoursFromNow(UPCOMING[0].start),
      minutes_until_start: UPCOMING[0].start * 60,
      preview:
        "Acme is waiting on a firm EU region date (you promised it last week — overdue). Marcus committed to the 30th. They'll also ask about SOC 2 and renewal pricing.",
      open_commitments_count: 3,
      related_topic_count: 3,
    },
  ];
}

export function demoTodayBriefing(): TodayBriefing {
  const open = demoCommitments().filter((c) => c.status === "open");
  return {
    date: dateOnly(0),
    upcoming_meetings: UPCOMING.map((e) => ({ id: e.id, title: e.title, start_time: hoursFromNow(e.start), attendees: e.attendees })),
    open_commitments: open.slice(0, 4).map((c) => ({
      id: c.id,
      text: c.text,
      owner: c.owner,
      due_date: c.due_date,
      conversation_id: c.conversation_id,
      conversation_title: c.conversation_title,
    })),
    recent_activity: MEETINGS.slice(0, 4).map((m) => ({
      conversation_id: m.id,
      title: m.title,
      meeting_date: meetingDate(m),
      status: "indexed",
    })),
    recent_connections: [
      {
        id: "rc-1",
        label: "Q4 pricing revamp",
        summary: "Acme's renewal pricing question connects to the usage-based pilot approved in leadership.",
        linked_type: "topic",
        created_at: daysAgo(1),
        related_conversations: ["m-acme-qbr", "m-leadership"].map((id) => ({
          conversation_id: id,
          title: meetingById.get(id)!.title,
          meeting_date: meetingDate(meetingById.get(id)!),
        })),
      },
    ],
  };
}

export function demoHomeDashboard(): HomeDashboard {
  const open = demoCommitments().filter((c) => c.status === "open");
  const toItem = (c: Commitment) => ({
    id: c.id,
    text: c.text,
    owner: c.owner,
    due_date: c.due_date,
    conversation_title: c.conversation_title,
  });
  return {
    today: { upcoming_meetings: demoTodayBriefing().upcoming_meetings },
    stats: demoIndexStats(),
    summary: {
      summary:
        "Busy week on two fronts. Leadership approved a 10-account usage-pricing pilot with a $499 floor, and Jordan is sending terms by Friday. Acme's wave two is blocked on EU data residency — you owe Sarah a firm date and it's overdue; Marcus is targeting the 30th. The dashboard performance issue is resolved (P95 back to 1.1s). SOC 2 is now a priority because Acme's procurement depends on it.",
      generated_at: daysAgo(0, 8),
    },
    prep_push: demoUpcomingBriefs()[0],
    actions: {
      commitment: open.filter((c) => c.action_type === "commitment").map(toItem),
      follow_up: open.filter((c) => c.action_type === "follow_up").map(toItem),
    },
  };
}

export function demoBrief(id: string): BriefDetail | null {
  if (id !== "b-acme") {
    return null;
  }
  const qbr = meetingById.get("m-acme-qbr")!;
  return {
    id: "b-acme",
    conversation_id: qbr.id,
    calendar_event_id: "ev-acme",
    generated_at: daysAgo(0, 8),
    content: [
      "Where things stand: wave one is live. Wave two is blocked on EU data residency — Acme's security team won't sign off without it.",
      "",
      "What you promised: at the QBR you told Sarah you'd come back with a firm EU region date that week. That follow-up is overdue. Marcus has since committed to having the EU region live by the 30th.",
      "",
      "Likely questions: (1) the SOC 2 report — procurement needs it before expansion; the Type II audit window opens next quarter and access reviews are the main gap. (2) Renewal pricing — leadership approved a usage-based pilot, but existing contracts don't change before renewal.",
      "",
      "Suggested opener: lead with the EU date (the 30th), then pre-empt the SOC 2 question with the audit timeline.",
    ].join("\n"),
    topic_arcs: ["t-acme", "t-soc2", "t-pricing"].map((tid) => ({
      id: `arc-${tid}`,
      topic_id: tid,
      summary: topicById.get(tid)!.summary,
      trend: topicById.get(tid)!.trend,
    })),
    commitments: COMMITMENTS.filter((c) => ["c-2", "c-3", "c-6"].includes(c.id)).map((c) => ({
      id: c.id,
      text: c.text,
      owner: c.owner,
      due_date: c.due_date,
      status: c.status,
    })),
    connections: [
      { id: "bc-1", label: "Engineering standup", summary: "Marcus committed to the EU region by the 30th.", linked_type: "conversation" },
      { id: "bc-2", label: "Leadership staff meeting", summary: "SOC 2 Type II prioritised because Acme depends on it.", linked_type: "conversation" },
    ],
    citations: qbr.segments.slice(0, 3).map((s, index) => ({
      segment_id: `${qbr.id}-s${index}`,
      conversation_id: qbr.id,
      speaker_id: s.speaker,
      start_ms: index * 60000,
      text: s.text,
    })),
  };
}

export function demoSearch(query: string): SearchResult[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const results: SearchResult[] = [];
  for (const topic of TOPICS) {
    const haystack = `${topic.label} ${topic.summary}`.toLowerCase();
    if (terms.some((t) => haystack.includes(t))) {
      const first = MEETINGS.find((m) => m.topicIds.includes(topic.id))!;
      results.push({
        result_id: topic.id,
        result_type: "topic",
        title: topic.label,
        text: topic.summary,
        conversation_id: first.id,
        conversation_title: first.title,
        meeting_date: meetingDate(first),
        score: 0.92,
      });
    }
  }
  for (const meeting of MEETINGS) {
    meeting.segments.forEach((s, index) => {
      if (terms.some((t) => s.text.toLowerCase().includes(t))) {
        results.push({
          result_id: `${meeting.id}-s${index}`,
          result_type: "segment",
          title: `${s.speaker} in ${meeting.title}`,
          text: s.text,
          conversation_id: meeting.id,
          conversation_title: meeting.title,
          meeting_date: meetingDate(meeting),
          score: 0.8,
        });
      }
    });
  }
  return results.slice(0, 12);
}

function citationsFor(meetingIds: string[]): ChatCitation[] {
  return meetingIds.map((id) => {
    const m = meetingById.get(id)!;
    return {
      result_id: `${id}-s0`,
      result_type: "segment",
      title: m.title,
      conversation_id: id,
      conversation_title: m.title,
      meeting_date: meetingDate(m),
    };
  });
}

export function demoAnswer(question: string): { answer: string; citations: ChatCitation[] } {
  const q = question.toLowerCase();
  if (q.includes("acme") || q.includes("eu") || q.includes("residency")) {
    return {
      answer:
        "Acme's wave two is blocked on EU data residency. Sarah raised it at the QBR and you promised a firm date that week (that follow-up is now overdue). In the engineering standup the next day, Marcus committed to having the EU region live by the 30th. Acme's procurement will also require the SOC 2 report before expanding.",
      citations: citationsFor(["m-acme-qbr", "m-eng-standup"]),
    };
  }
  if (q.includes("pric")) {
    return {
      answer:
        "The pricing discussion started in the Analytics tier strategy meeting, where you proposed usage-based pricing and Daniel asked for a floor. Leadership then approved a 10-account pilot with a $499/month floor. In this week's Sales sync, Jordan confirmed the ten accounts (Brightline and Coastal flagged as churn risks) and will send terms by Friday.",
      citations: citationsFor(["m-strategy", "m-leadership", "m-sales-sync"]),
    };
  }
  return {
    answer:
      "Across your last eight meetings, the active threads are the Q4 pricing pilot, Acme's onboarding (blocked on EU data residency), SOC 2 Type II prep, and the senior data engineer hire. The dashboard performance regression was resolved last week. Your most urgent open item is the overdue follow-up to Acme with an EU region date.",
    citations: citationsFor(["m-leadership", "m-acme-qbr", "m-eng-retro"]),
  };
}

export function demoChatSessions(): ChatSessionSummary[] {
  return [
    {
      id: "chat-1",
      title: "Where are we on Acme?",
      created_at: daysAgo(2, 15),
      updated_at: daysAgo(2, 15),
      last_message_preview: "Acme's wave two is blocked on EU data residency…",
    },
  ];
}

export function demoChatMessages(sessionId: string): ChatMessage[] {
  if (sessionId !== "chat-1") {
    return [];
  }
  const reply = demoAnswer("acme");
  return [
    { id: "msg-1", role: "user", content: "Where are we on Acme?", citations: [], created_at: daysAgo(2, 15) },
    { id: "msg-2", role: "assistant", content: reply.answer, citations: reply.citations, created_at: daysAgo(2, 15) },
  ];
}

export function demoRecordings(): RecordingItem[] {
  return MEETINGS.map((m) => ({
    file_id: `file-${m.id}`,
    name: `${m.title} - Transcript`,
    created_time: meetingDate(m),
    size_bytes: 48000,
    mime_type: "application/vnd.google-apps.document",
    already_imported: true,
  }));
}
