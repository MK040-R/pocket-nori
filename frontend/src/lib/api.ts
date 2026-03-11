export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Session = {
  user_id: string;
  email: string;
};

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
  segment_id: string;
  text: string;
  conversation_id: string;
  conversation_title: string;
  meeting_date: string;
  score: number;
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
  conversation_id: string;
  conversation_title: string;
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

class ApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = RequestInit & {
  expectNoContent?: boolean;
};

async function request(path: string, init: RequestOptions & { expectNoContent: true }): Promise<void>;
async function request<T>(path: string, init?: RequestOptions): Promise<T>;
async function request<T>(path: string, init: RequestOptions = {}): Promise<T | void> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        message = payload.detail;
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

export async function getSession(): Promise<Session | null> {
  try {
    return await request<Session>("/auth/session", { method: "GET" });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  await request<{ ok: boolean }>("/auth/logout", { method: "POST", body: JSON.stringify({}) });
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
export async function getConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/conversations", { method: "GET" });
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function getConversationConnections(id: string): Promise<ConversationConnection[]> {
  const response = await request<{ connections: ConversationConnection[] }>(
    `/conversations/${encodeURIComponent(id)}/connections`,
    { method: "GET" },
  );
  return response.connections;
}

export async function search(q: string, limit = 10): Promise<SearchResult[]> {
  const normalized = q.toLowerCase().trim();
  if (!normalized) {
    return [];
  }
  return request<SearchResult[]>("/search", {
    method: "POST",
    body: JSON.stringify({ q: normalized, limit }),
  });
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

export async function getTopics(): Promise<TopicSummary[]> {
  const rows = await request<TopicApiSummaryItem[]>("/topics", { method: "GET" });
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
  options: { assignee?: string; attributedTo?: string } = {},
): Promise<Commitment[]> {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  if (options.assignee?.trim()) {
    params.set("assignee", options.assignee.trim());
  }
  if (options.attributedTo?.trim()) {
    params.set("attributed_to", options.attributedTo.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<Commitment[]>(`/commitments${suffix}`, { method: "GET" });
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
