import {
  DEMO_SESSION,
  demoAnswer,
  demoBrief,
  demoChatMessages,
  demoChatSessions,
  demoCommitments,
  demoConnections,
  demoConversationDetail,
  demoConversations,
  demoEntities,
  demoHomeDashboard,
  demoIndexStats,
  demoRecordings,
  demoSearch,
  demoTodayBriefing,
  demoTopicArc,
  demoTopicDetail,
  demoTopics,
  demoUpcomingBriefs,
} from "@/lib/demo-data";
import type { ChatMessage, ChatSessionSummary } from "@/lib/api";

type DemoChatSession = { summary: ChatSessionSummary; messages: ChatMessage[] };

const liveChatSessions: DemoChatSession[] = [];

function allChatSessions(): ChatSessionSummary[] {
  return [...liveChatSessions.map((session) => session.summary), ...demoChatSessions()];
}

function chatMessagesFor(sessionId: string): ChatMessage[] {
  return liveChatSessions.find((session) => session.summary.id === sessionId)?.messages ?? demoChatMessages(sessionId);
}

export class DemoNotFoundError extends Error {
  public readonly status = 404;
}

type Handler = (match: RegExpMatchArray, body: Record<string, unknown>, query: URLSearchParams) => unknown;

function orNotFound<T>(value: T | null): T {
  if (value === null) {
    throw new DemoNotFoundError("Not found in demo data");
  }
  return value;
}

const ROUTES: Array<[string, RegExp, Handler]> = [
  ["GET", /^\/auth\/session$/, () => DEMO_SESSION],
  ["POST", /^\/auth\/(refresh|logout)$/, () => ({ ok: true })],
  ["GET", /^\/home\/dashboard$/, () => demoHomeDashboard()],
  ["GET", /^\/home\/summary$/, () => demoHomeDashboard().summary],
  ["GET", /^\/calendar\/today$/, () => demoTodayBriefing()],
  ["GET", /^\/index\/stats$/, () => demoIndexStats()],
  ["GET", /^\/conversations$/, (_m, _b, q) => {
    const category = q.get("category");
    return demoConversations().filter((c) => !category || c.category === category);
  }],
  ["GET", /^\/conversations\/([^/]+)\/connections$/, (m) => ({ connections: demoConnections(decodeURIComponent(m[1])) })],
  ["GET", /^\/conversations\/([^/]+)$/, (m) => orNotFound(demoConversationDetail(decodeURIComponent(m[1])))],
  ["PATCH", /^\/conversations\/([^/]+)$/, (m, b) => {
    const row = orNotFound(demoConversations().find((c) => c.id === decodeURIComponent(m[1])) ?? null);
    return { ...row, category: b.category ?? row.category };
  }],
  ["GET", /^\/topics$/, () => demoTopics()],
  ["GET", /^\/topics\/([^/]+)\/arc$/, (m) => orNotFound(demoTopicArc(decodeURIComponent(m[1])))],
  ["GET", /^\/topics\/([^/]+)$/, (m) => orNotFound(demoTopicDetail(decodeURIComponent(m[1])))],
  ["GET", /^\/commitments$/, (_m, _b, q) => {
    const status = q.get("status");
    const actionType = q.get("action_type");
    const assignee = q.get("assignee")?.toLowerCase();
    return demoCommitments().filter(
      (c) =>
        (!status || c.status === status) &&
        (!actionType || c.action_type === actionType) &&
        (!assignee || c.owner.toLowerCase().includes(assignee)),
    );
  }],
  ["POST", /^\/commitments\/([^/]+)\/draft$/, (m, b) => {
    const c = orNotFound(demoCommitments().find((item) => item.id === decodeURIComponent(m[1])) ?? null);
    return {
      subject: `Follow-up: ${c.text}`,
      body: `Hi,\n\nFollowing up from "${c.conversation_title}" — ${c.text.charAt(0).toLowerCase()}${c.text.slice(1)}. I'll share an update by ${c.due_date ?? "end of week"}.\n\nThanks,\nPriya`,
      recipient_suggestion: c.owner,
      commitment_text: c.text,
      format: b.format === "message" ? "message" : "email",
    };
  }],
  ["PATCH", /^\/commitments\/([^/]+)$/, (m) => {
    const c = orNotFound(demoCommitments().find((item) => item.id === decodeURIComponent(m[1])) ?? null);
    return { ...c, status: "resolved" };
  }],
  ["POST", /^\/commitments$/, (_m, b) => ({
    id: `c-new-${Date.now()}`,
    text: String(b.text ?? ""),
    owner: String(b.owner ?? "Priya"),
    due_date: (b.due_date as string | null) ?? null,
    status: "open",
    action_type: b.action_type === "follow_up" ? "follow_up" : "commitment",
    conversation_id: "",
    conversation_title: "",
    meeting_date: null,
    topic_labels: [],
  })],
  ["GET", /^\/entities$/, () => demoEntities()],
  ["GET", /^\/briefs\/upcoming$/, () => demoUpcomingBriefs()],
  ["GET", /^\/briefs\/latest$/, () => ({
    brief_id: "b-acme",
    generated_at: demoUpcomingBriefs()[0].event_start,
    preview: demoUpcomingBriefs()[0].preview,
  })],
  ["GET", /^\/briefs\/([^/]+)$/, (m) => orNotFound(demoBrief(decodeURIComponent(m[1])))],
  ["POST", /^\/search$/, (_m, b) => demoSearch(String(b.q ?? ""))],
  ["POST", /^\/search\/ask$/, (_m, b) => {
    const { answer, citations } = demoAnswer(String(b.q ?? ""));
    return {
      answer,
      citations: citations.map((c) => ({ ...c, snippet: c.title })),
    };
  }],
  ["GET", /^\/chat\/sessions$/, () => allChatSessions()],
  ["GET", /^\/chat\/sessions\/([^/]+)\/messages$/, (m) => chatMessagesFor(decodeURIComponent(m[1]))],
  ["DELETE", /^\/chat\/sessions\/([^/]+)$/, (m) => {
    const index = liveChatSessions.findIndex((item) => item.summary.id === decodeURIComponent(m[1]));
    if (index >= 0) {
      liveChatSessions.splice(index, 1);
    }
    return undefined;
  }],
  ["GET", /^\/onboarding\/available-recordings$/, () => demoRecordings()],
  ["GET", /^\/onboarding\/import\/status\/([^/]+)$/, (m) => ({ job_id: decodeURIComponent(m[1]), status: "success" })],
  ["GET", /^\/onboarding\/import\/status$/, () => ({ total: 0, pending: 0, processing: 0, succeeded: 0, failed: 0, jobs: [] })],
  ["POST", /^\/onboarding\/import$/, () => ({ jobs: [] })],
];

export async function demoRequest(path: string, init: RequestInit = {}): Promise<unknown> {
  const method = (init.method ?? "GET").toUpperCase();
  const [pathname, queryString = ""] = path.split("?");
  const body =
    typeof init.body === "string" && init.body ? (JSON.parse(init.body) as Record<string, unknown>) : {};

  await new Promise((resolve) => setTimeout(resolve, 150));

  for (const [routeMethod, pattern, handler] of ROUTES) {
    if (routeMethod !== method) {
      continue;
    }
    const match = pathname.match(pattern);
    if (match) {
      return handler(match, body, new URLSearchParams(queryString));
    }
  }
  throw new DemoNotFoundError(`Demo mode has no data for ${method} ${pathname}`);
}

export function demoChatStream(message: string, sessionId?: string): Response {
  const { answer, citations } = demoAnswer(message);
  const now = new Date().toISOString();
  let session = liveChatSessions.find((item) => item.summary.id === sessionId);
  if (!session) {
    session = {
      summary: { id: `chat-demo-${Date.now()}`, title: message, created_at: now, updated_at: now, last_message_preview: "" },
      messages: [...(sessionId ? demoChatMessages(sessionId) : [])],
    };
    liveChatSessions.unshift(session);
  }
  session.messages.push(
    { id: `u-${Date.now()}`, role: "user", content: message, citations: [], created_at: now },
    { id: `a-${Date.now()}`, role: "assistant", content: answer, citations, created_at: now },
  );
  session.summary.updated_at = now;
  session.summary.last_message_preview = answer.slice(0, 80);
  const activeSessionId = session.summary.id;
  const encoder = new TextEncoder();
  const words = answer.split(/(\s+)/);
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: string, data: unknown) =>
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      send("session", { session_id: activeSessionId });
      for (let i = 0; i < words.length; i += 6) {
        send("delta", { content: words.slice(i, i + 6).join("") });
        await new Promise((resolve) => setTimeout(resolve, 40));
      }
      send("citations", citations);
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}
