import { isMeetingCategory, type MeetingCategory } from "@/lib/meeting-categories";

const DEFAULT_API_URL =
  process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://farz-personal-intelligence.onrender.com";

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;

export type Session = {
  user_id: string;
  email: string;
};

export type ActionType = "commitment" | "follow_up";

export type AuthEvent =
  | { type: "refreshed"; session: Session }
  | { type: "expired" | "signed_out" };

export type RecordingItem = {
  file_id: string;
  name: string;
  created_time: string;
  size_bytes: number | null;
  mime_type: string;
  already_imported: boolean;
};

export type ImportJob = {
  file_id: string;
  job_id: string;
};

export type ImportJobList = {
  jobs: ImportJob[];
};

export type ImportJobStatus = {
  job_id: string;
  file_id?: string;
  status: "pending" | "progress" | "processing" | "success" | "failure";
  detail?: string | null;
  result?: Record<string, unknown> | null;
};

export type AggregateImportStatus = {
  total: number;
  pending: number;
  processing: number;
  succeeded: number;
  failed: number;
  jobs: ImportJobStatus[];
};

export type ConversationSummary = {
  id: string;
  title: string;
  source: "google_drive";
  meeting_date: string;
  duration_seconds: number | null;
  status: "indexed" | "processing";
  topic_labels: string[];
  category: MeetingCategory | null;
  latest_brief_id?: string | null;
  latest_brief_generated_at?: string | null;
};

export type ConversationConnection = {
  id: string;
  linked_type: "conversation" | "topic";
  label: string;
  summary: string;
  connected_conversation_id: string;
  connected_conversation_title: string;
  connected_meeting_date: string | null;
  shared_topics: string[];
  shared_entities: string[];
  shared_commitments: string[];
};

export type ConversationDetail = {
  conversation: {
    id: string;
    title: string;
    meeting_date: string;
    duration_seconds: number | null;
    category: MeetingCategory | null;
    latest_brief_id?: string | null;
    latest_brief_generated_at?: string | null;
  };
  topics: Array<{
    id: string;
    label: string;
    summary: string;
    status: "open" | "resolved";
    key_quotes: string[];
  }>;
  commitments: Array<{
    id: string;
    text: string;
    owner: string;
    due_date: string | null;
    status: "open" | "resolved";
    action_type: ActionType;
  }>;
  entities: Array<{
    id: string;
    name: string;
    type: "person" | "project" | "company" | "product";
    mentions: number;
  }>;
  segments: Array<{
    id: string;
    speaker_id: string;
    start_ms: number;
    end_ms: number;
    text: string;
  }>;
  connections: ConversationConnection[];
};

export type SearchResult = {
  result_id: string;
  result_type: "topic" | "entity" | "meeting" | "segment";
  title: string;
  text: string;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string;
  score: number;
};

export type CitationRef = {
  result_id: string;
  result_type: string;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string;
  snippet: string;
};

export type AskResponse = {
  answer: string;
  citations: CitationRef[];
};

export type IndexStats = {
  conversation_count: number;
  topic_count: number;
  commitment_count: number;
  entity_count: number;
  last_updated_at: string;
};

export type TopicSummary = {
  id: string;
  label: string;
  conversation_count: number;
  latest_date: string;
};

export type TopicDetail = {
  id: string;
  label: string;
  summary: string;
  status?: string;
  conversations: Array<{
    id: string;
    title: string;
    meeting_date: string;
  }>;
  key_quotes: string[];
};

export type TopicArcPoint = {
  topic_id: string;
  conversation_id: string;
  conversation_title: string;
  occurred_at: string;
  summary: string;
  topic_status: "open" | "resolved";
  citation_segment_id: string | null;
  transcript_offset_seconds: number | null;
  citation_snippet: string | null;
};

export type TopicArc = {
  id: string;
  topic_id: string;
  label: string;
  summary: string;
  status: "open" | "resolved";
  trend: "growing" | "stable" | "resolved";
  conversation_count: number;
  arc_points: TopicArcPoint[];
};

export type Commitment = {
  id: string;
  text: string;
  owner: string;
  due_date: string | null;
  status: "open" | "resolved";
  action_type: ActionType;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string | null;
  topic_labels: string[];
};

export type CreateCommitmentInput = {
  text: string;
  action_type: ActionType;
  owner: string;
  due_date?: string | null;
};

export type EntitySummary = {
  name: string;
  type: "person" | "project" | "company" | "product";
  mentions: number;
  conversation_count: number;
};

export type TodayBriefing = {
  date: string;
  upcoming_meetings: Array<{
    id: string;
    title: string;
    start_time: string;
    attendees: string[];
  }>;
  open_commitments: Array<{
    id: string;
    text: string;
    owner: string;
    due_date: string | null;
    conversation_id: string;
    conversation_title: string;
  }>;
  recent_activity: Array<{
    conversation_id: string;
    title: string;
    meeting_date: string;
    status: string;
  }>;
  recent_connections: Array<{
    id: string;
    label: string;
    summary: string;
    linked_type: "conversation" | "topic";
    created_at: string;
    related_conversations: Array<{
      conversation_id: string;
      title: string;
      meeting_date: string | null;
    }>;
  }>;
};

export type HomeSummary = {
  summary: string;
  generated_at: string;
};

export type BriefCitation = {
  segment_id: string;
  conversation_id: string;
  speaker_id: string;
  start_ms: number;
  text: string;
};

export type BriefDetail = {
  id: string;
  conversation_id: string;
  calendar_event_id: string | null;
  content: string;
  generated_at: string;
  topic_arcs: Array<{
    id: string;
    topic_id: string;
    summary: string;
    trend: "growing" | "stable" | "resolved";
  }>;
  commitments: Array<{
    id: string;
    text: string;
    owner: string;
    due_date: string | null;
    status: "open" | "resolved";
  }>;
  connections: Array<{
    id: string;
    label: string;
    summary: string;
    linked_type: "conversation" | "topic";
  }>;
  citations: BriefCitation[];
};

export type BriefLatest = {
  brief_id: string;
  generated_at: string;
  preview: string;
};

export type ChatCitation = {
  result_id: string;
  result_type: string;
  title: string;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string;
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: ChatCitation[];
  created_at: string;
};

export type DraftFormat = "email" | "message";

export type DraftResponse = {
  subject: string;
  body: string;
  recipient_suggestion: string;
  commitment_text: string;
  format: DraftFormat;
};

export type UpcomingBrief = {
  brief_id: string;
  conversation_id: string | null;
  calendar_event_id: string;
  event_title: string;
  event_start: string;
  minutes_until_start: number;
  preview: string;
  open_commitments_count: number;
  related_topic_count: number;
};

class ApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function isApiErrorStatus(error: unknown, statuses: number[]): boolean {
  return error instanceof ApiError && statuses.includes(error.status);
}

type RequestOptions = RequestInit & {
  expectNoContent?: boolean;
  skipAuthRefresh?: boolean;
};

type AuthListener = (event: AuthEvent) => void;

const authListeners = new Set<AuthListener>();
let refreshPromise: Promise<Session | null> | null = null;

function emitAuthEvent(event: AuthEvent): void {
  for (const listener of authListeners) {
    listener(event);
  }
}

export function subscribeToAuth(listener: AuthListener): () => void {
  authListeners.add(listener);
  return () => {
    authListeners.delete(listener);
  };
}

function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const hasBody = init?.body !== undefined && init?.body !== null;
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  if (hasBody && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function fetchResponse(path: string, init: RequestOptions = {}): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: buildHeaders(init),
  });
}

async function refreshSession(): Promise<Session | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const response = await fetchResponse("/auth/refresh", {
        method: "POST",
        skipAuthRefresh: true,
      });
      if (!response.ok) {
        return null;
      }
      const session = (await response.json()) as Session;
      emitAuthEvent({ type: "refreshed", session });
      return session;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function shouldAttemptRefresh(path: string, init: RequestOptions, response: Response): boolean {
  if (response.status !== 401 || init.skipAuthRefresh) {
    return false;
  }
  return path !== "/auth/refresh" && path !== "/auth/logout";
}

async function parseResponse<T>(response: Response, init: RequestOptions): Promise<T | void> {
  if (!response.ok) {
    let message =
      response.status === 401 ? "Session expired. Sign in again." : `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        message = response.status === 401 ? "Session expired. Sign in again." : payload.detail;
      }
    } catch {
      // ignore JSON parse issues for error payloads
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    if (init.expectNoContent) {
      return;
    }
    throw new ApiError(response.status, "Unexpected empty response from server");
  }

  if (init.expectNoContent) {
    return;
  }

  return (await response.json()) as T;
}

async function request(path: string, init: RequestOptions & { expectNoContent: true }): Promise<void>;
async function request<T>(path: string, init?: RequestOptions): Promise<T>;
async function request<T>(path: string, init: RequestOptions = {}): Promise<T | void> {
  let response = await fetchResponse(path, init);
  if (shouldAttemptRefresh(path, init, response)) {
    const refreshedSession = await refreshSession();
    if (refreshedSession) {
      response = await fetchResponse(path, { ...init, skipAuthRefresh: true });
    }
  }

  if (response.status === 401 && path !== "/auth/session") {
    emitAuthEvent({ type: "expired" });
  }

  return parseResponse<T>(response, init);
}

type ConversationSummaryApi = Omit<ConversationSummary, "category" | "topic_labels"> & {
  category?: string | null;
  topic_labels?: string[] | null;
};

type ConversationDetailApi = Omit<ConversationDetail, "conversation"> & {
  conversation: Omit<ConversationDetail["conversation"], "category"> & {
    category?: string | null;
  };
};

function normalizeConversationSummary(item: ConversationSummaryApi): ConversationSummary {
  return {
    ...item,
    topic_labels: item.topic_labels ?? [],
    category: isMeetingCategory(item.category) ? item.category : null,
  };
}

function normalizeConversationDetail(item: ConversationDetailApi): ConversationDetail {
  return {
    ...item,
    conversation: {
      ...item.conversation,
      category: isMeetingCategory(item.conversation.category) ? item.conversation.category : null,
    },
  };
}

export async function getSession(): Promise<Session | null> {
  try {
    const session = await request<Session>("/auth/session", { method: "GET" });
    if (session) {
      emitAuthEvent({ type: "refreshed", session });
    }
    return session;
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  await request<{ ok: boolean }>("/auth/logout", { method: "POST", body: JSON.stringify({}) });
  emitAuthEvent({ type: "signed_out" });
}

// Real onboarding endpoints
export async function getAvailableRecordings(): Promise<RecordingItem[]> {
  return request<RecordingItem[]>("/onboarding/available-recordings", { method: "GET" });
}

export async function startImport(fileIds: string[]): Promise<ImportJobList> {
  return request<ImportJobList>("/onboarding/import", {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

export async function getImportStatus(jobId: string): Promise<ImportJobStatus> {
  return request<ImportJobStatus>(`/onboarding/import/status/${encodeURIComponent(jobId)}`, {
    method: "GET",
  });
}

export async function getAllImportStatus(jobIds: string[]): Promise<AggregateImportStatus> {
  if (jobIds.length === 0) {
    return { total: 0, pending: 0, processing: 0, succeeded: 0, failed: 0, jobs: [] };
  }
  const params = new URLSearchParams({ job_ids: jobIds.join(",") });
  return request<AggregateImportStatus>(`/onboarding/import/status?${params.toString()}`, {
    method: "GET",
  });
}

// Live Phase 1 endpoints
export async function getConversations(options: {
  limit?: number;
  offset?: number;
  category?: MeetingCategory;
} = {}): Promise<ConversationSummary[]> {
  const params = new URLSearchParams();
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(options.offset));
  }
  if (options.category) {
    params.set("category", options.category);
  }
  const query = params.toString();
  const rows = await request<ConversationSummaryApi[]>(`/conversations${query ? `?${query}` : ""}`, {
    method: "GET",
  });
  return rows.map(normalizeConversationSummary);
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const detail = await request<ConversationDetailApi>(`/conversations/${encodeURIComponent(id)}`, {
    method: "GET",
  });
  return normalizeConversationDetail(detail);
}

export async function updateConversationCategory(
  id: string,
  category: MeetingCategory,
): Promise<ConversationSummary> {
  const updated = await request<ConversationSummaryApi>(`/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ category }),
  });
  return normalizeConversationSummary(updated);
}

export async function getConversationConnections(id: string): Promise<ConversationConnection[]> {
  const response = await request<{ connections: ConversationConnection[] }>(
    `/conversations/${encodeURIComponent(id)}/connections`,
    { method: "GET" },
  );
  return response.connections;
}

export async function search(
  q: string,
  limit = 10,
  options: { dateFrom?: string; dateTo?: string } = {},
): Promise<SearchResult[]> {
  const normalized = q.toLowerCase().trim();
  if (!normalized) {
    return [];
  }
  return request<SearchResult[]>("/search", {
    method: "POST",
    body: JSON.stringify({
      q: normalized,
      limit,
      ...(options.dateFrom ? { date_from: options.dateFrom } : {}),
      ...(options.dateTo ? { date_to: options.dateTo } : {}),
    }),
  });
}

export async function ask(
  q: string,
  options: { dateFrom?: string; dateTo?: string } = {},
): Promise<AskResponse> {
  const normalized = q.trim();
  return request<AskResponse>("/search/ask", {
    method: "POST",
    body: JSON.stringify({
      q: normalized,
      ...(options.dateFrom ? { date_from: options.dateFrom } : {}),
      ...(options.dateTo ? { date_to: options.dateTo } : {}),
    }),
  });
}

export async function backfillEmbeddings(): Promise<{
  digests_generated: number;
  topic_clusters_embedded: number;
  entities_embedded: number;
  digest_embeddings_stored: number;
  conversations_processed: number;
  conversations_skipped: number;
}> {
  return request("/admin/backfill-embeddings", { method: "POST" });
}

export async function getIndexStats(): Promise<IndexStats> {
  return request<IndexStats>("/index/stats", { method: "GET" });
}

type TopicApiSummaryItem = {
  id: string;
  label: string;
  conversation_count: number;
  latest_date: string | null;
};

type TopicApiDetailItem = {
  id: string;
  label: string;
  summary: string;
  status?: string;
  key_quotes: string[];
  conversations: Array<{
    id: string;
    title: string;
    meeting_date: string;
  }>;
};

export async function getTopics(options: { minConversations?: number } = {}): Promise<TopicSummary[]> {
  const params = new URLSearchParams();
  if (typeof options.minConversations === "number") {
    params.set("min_conversations", String(options.minConversations));
  }
  const query = params.toString();
  const rows = await request<TopicApiSummaryItem[]>(`/topics${query ? `?${query}` : ""}`, {
    method: "GET",
  });
  return rows
    .map((item) => ({
      id: item.id,
      label: item.label,
      conversation_count: item.conversation_count,
      latest_date: item.latest_date ?? "",
    }))
    .sort((a, b) => b.latest_date.localeCompare(a.latest_date));
}

export async function getTopic(id: string): Promise<TopicDetail> {
  const topic = await request<TopicApiDetailItem>(`/topics/${encodeURIComponent(id)}`, {
    method: "GET",
  });

  return {
    id: topic.id,
    label: topic.label,
    summary: topic.summary,
    status: topic.status,
    conversations: [...topic.conversations].sort((a, b) => b.meeting_date.localeCompare(a.meeting_date)),
    key_quotes: topic.key_quotes,
  };
}

export async function getTopicArc(id: string): Promise<TopicArc> {
  return request<TopicArc>(`/topics/${encodeURIComponent(id)}/arc`, { method: "GET" });
}

export async function getCommitments(
  status?: "open" | "resolved",
  options: {
    actionType?: ActionType;
    assignee?: string;
    attributedTo?: string;
    topic?: string;
    meeting?: string;
    meetingDateFrom?: string;
    meetingDateTo?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<Commitment[]> {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  if (options.actionType) {
    params.set("action_type", options.actionType);
  }
  if (options.assignee?.trim()) {
    params.set("assignee", options.assignee.trim());
  }
  if (options.attributedTo?.trim()) {
    params.set("attributed_to", options.attributedTo.trim());
  }
  if (options.topic?.trim()) {
    params.set("topic", options.topic.trim());
  }
  if (options.meeting?.trim()) {
    params.set("meeting", options.meeting.trim());
  }
  if (options.meetingDateFrom?.trim()) {
    params.set("meeting_date_from", options.meetingDateFrom.trim());
  }
  if (options.meetingDateTo?.trim()) {
    params.set("meeting_date_to", options.meetingDateTo.trim());
  }
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(options.offset));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<Commitment[]>(`/commitments${suffix}`, { method: "GET" });
}

export async function createCommitment(input: CreateCommitmentInput): Promise<Commitment> {
  return request<Commitment>("/commitments", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function resolveCommitment(id: string): Promise<Commitment> {
  return request<Commitment>(`/commitments/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "resolved" }),
  });
}

export async function getTodayBriefing(): Promise<TodayBriefing> {
  return request<TodayBriefing>("/calendar/today", { method: "GET" });
}

export async function getHomeSummary(): Promise<HomeSummary> {
  return request<HomeSummary>("/home/summary", { method: "GET" });
}

export async function getEntities(): Promise<EntitySummary[]> {
  return request<EntitySummary[]>("/entities", { method: "GET" });
}

export async function getBrief(id: string): Promise<BriefDetail> {
  return request<BriefDetail>(`/briefs/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function getLatestBrief(params: {
  conversationId?: string;
  calendarEventId?: string;
}): Promise<BriefLatest> {
  const query = new URLSearchParams();
  if (params.conversationId) {
    query.set("conversation_id", params.conversationId);
  }
  if (params.calendarEventId) {
    query.set("calendar_event_id", params.calendarEventId);
  }
  return request<BriefLatest>(`/briefs/latest?${query.toString()}`, { method: "GET" });
}

export async function getUpcomingBriefs(): Promise<UpcomingBrief[]> {
  return request<UpcomingBrief[]>("/briefs/upcoming", { method: "GET" });
}

export async function getChatSessions(): Promise<ChatSessionSummary[]> {
  return request<ChatSessionSummary[]>("/chat/sessions", { method: "GET" });
}

export async function getChatMessages(
  sessionId: string,
  limit = 50,
  offset = 0,
): Promise<ChatMessage[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request<ChatMessage[]>(`/chat/sessions/${encodeURIComponent(sessionId)}/messages?${params.toString()}`, {
    method: "GET",
  });
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await request(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    expectNoContent: true,
  });
}

export async function generateDraft(
  commitmentId: string,
  format: DraftFormat = "email",
): Promise<DraftResponse> {
  return request<DraftResponse>(`/commitments/${encodeURIComponent(commitmentId)}/draft`, {
    method: "POST",
    body: JSON.stringify({ format }),
  });
}
