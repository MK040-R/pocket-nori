"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  getConversation,
  getConversationConnections,
  type ActionType,
  type ConversationConnection,
  type ConversationDetail,
} from "@/lib/api";
import { formatDueDate, formatMeetingTitle } from "@/lib/presentation";

type DetailTab = "topics" | "actions" | "transcript";
type MeetingAction = ConversationDetail["commitments"][number];

type TranscriptGroup = {
  id: string;
  speakerId: string;
  startMs: number;
  endMs: number;
  text: string;
};

type ActionSection = {
  id: ActionType;
  title: string;
  emptyState: string;
  items: MeetingAction[];
};

const TABS: Array<{ id: DetailTab; label: string }> = [
  { id: "topics", label: "Topics" },
  { id: "actions", label: "Actions" },
  { id: "transcript", label: "Transcript" },
];

function formatMeetingMeta(value: string | null | undefined, fallback = "Unknown"): string {
  if (!value) {
    return fallback;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTranscriptTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function humanizeSpeaker(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "Unknown speaker";
  }
  return trimmed
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function buildTranscriptGroups(detail: ConversationDetail | null): TranscriptGroup[] {
  if (!detail || detail.segments.length === 0) {
    return [];
  }

  const groups: TranscriptGroup[] = [];

  detail.segments.forEach((segment) => {
    const lastGroup = groups[groups.length - 1];
    if (lastGroup && lastGroup.speakerId === segment.speaker_id) {
      lastGroup.endMs = segment.end_ms;
      lastGroup.text = `${lastGroup.text}\n\n${segment.text}`;
      return;
    }

    groups.push({
      id: segment.id,
      speakerId: segment.speaker_id,
      startMs: segment.start_ms,
      endMs: segment.end_ms,
      text: segment.text,
    });
  });

  return groups;
}

function buildActionSections(detail: ConversationDetail | null): ActionSection[] {
  if (!detail) {
    return [];
  }

  return [
    {
      id: "commitment",
      title: "Commitments",
      emptyState: "No commitments extracted from this meeting.",
      items: detail.commitments.filter(
        (commitment) => (commitment.action_type ?? "commitment") === "commitment",
      ),
    },
    {
      id: "follow_up",
      title: "Follow-ups",
      emptyState: "No follow-ups extracted from this meeting.",
      items: detail.commitments.filter((commitment) => commitment.action_type === "follow_up"),
    },
  ];
}

function ConnectionCard({ connection }: { connection: ConversationConnection }) {
  return (
    <article className="rounded border border-soft p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium text-ink-primary">{connection.label}</h3>
        <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
          {connection.linked_type}
        </span>
      </div>
      <p className="mt-2 text-sm text-ink-secondary">{connection.summary}</p>
      <p className="mt-2 text-xs text-ink-tertiary">
        Linked meeting: {formatMeetingTitle(connection.connected_conversation_title)}
      </p>
      <div className="mt-3 flex flex-wrap gap-3 text-xs">
        <Link
          href={`/meetings/${connection.connected_conversation_id}`}
          className="text-accent hover:text-accent-hover"
        >
          Open linked meeting
        </Link>
      </div>
    </article>
  );
}

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [connections, setConnections] = useState<ConversationConnection[]>([]);
  const [activeTab, setActiveTab] = useState<DetailTab>("topics");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [conversationData, connectionData] = await Promise.all([
          getConversation(id),
          getConversationConnections(id),
        ]);
        if (mounted) {
          setDetail(conversationData);
          setConnections(connectionData);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load meeting detail");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      mounted = false;
    };
  }, [id]);

  const transcriptGroups = useMemo(() => buildTranscriptGroups(detail), [detail]);
  const actionSections = useMemo(() => buildActionSections(detail), [detail]);

  if (loading) {
    return <section className="card p-4 text-sm text-ink-secondary">Loading meeting detail...</section>;
  }

  if (error || !detail) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Meeting detail not found"}
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <section className="card p-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{formatMeetingTitle(detail.conversation.title)}</h1>
          <span className="rounded-full border border-soft bg-bg-control px-2.5 py-1 text-xs font-medium text-ink-secondary">
            Online
          </span>
        </div>

        <p className="mt-2 text-sm text-ink-tertiary">
          {formatMeetingMeta(detail.conversation.meeting_date)} ·{" "}
          {detail.conversation.duration_seconds
            ? `${Math.round(detail.conversation.duration_seconds / 60)} min`
            : "Duration pending"}
        </p>

        <div className="mt-4 flex flex-wrap gap-2 text-xs text-ink-tertiary">
          <span className="rounded border border-soft bg-bg-control px-2 py-1">
            {detail.topics.length} topics
          </span>
          <span className="rounded border border-soft bg-bg-control px-2 py-1">
            {detail.commitments.length} actions
          </span>
          <span className="rounded border border-soft bg-bg-control px-2 py-1">
            {connections.length} connections
          </span>
        </div>

        {detail.conversation.latest_brief_id && (
          <p className="mt-4 text-sm">
            <Link
              href={`/briefs/${detail.conversation.latest_brief_id}`}
              className="text-accent hover:text-accent-hover"
            >
              Open latest brief
            </Link>
          </p>
        )}
      </section>

      <section className="card p-2">
        <div className="flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setActiveTab(tab.id);
              }}
              className={`rounded-xl px-4 py-2 text-sm transition ${
                activeTab === tab.id
                  ? "bg-bg-control text-ink-primary"
                  : "text-ink-secondary hover:bg-bg-control hover:text-ink-primary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "topics" && (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
          <article className="card p-5">
            <h2 className="text-lg font-semibold">Topics</h2>
            <div className="mt-3 space-y-3">
              {detail.topics.length === 0 && (
                <p className="text-sm text-ink-tertiary">No topics extracted for this meeting yet.</p>
              )}

              {detail.topics.map((topic) => (
                <Link
                  key={topic.id}
                  href={`/topics/${topic.id}`}
                  className="block rounded border border-soft p-3 transition hover:border-emphasis"
                >
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-medium">{topic.label}</h3>
                    <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                      {topic.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-ink-secondary">{topic.summary}</p>
                </Link>
              ))}
            </div>
          </article>

          <article className="card p-5">
            <h2 className="text-lg font-semibold">Connections</h2>
            <div className="mt-3 space-y-3">
              {connections.length === 0 && (
                <p className="text-sm text-ink-tertiary">No connections yet.</p>
              )}

              {connections.map((connection) => (
                <ConnectionCard key={connection.id} connection={connection} />
              ))}
            </div>
          </article>
        </section>
      )}

      {activeTab === "actions" && (
        <section className="space-y-4">
          <article className="card p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Actions</h2>
                <p className="mt-1 text-sm text-ink-secondary">
                  Meeting actions are split into direct commitments and lighter-weight follow-ups.
                </p>
              </div>
              <Link href="/commitments" className="text-xs text-accent hover:text-accent-hover">
                Open all actions
              </Link>
            </div>
          </article>

          <div className="grid gap-4 xl:grid-cols-2">
            {actionSections.map((section) => (
              <article key={section.id} className="card p-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-base font-semibold">{section.title}</h3>
                  <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                    {section.items.length}
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  {section.items.length === 0 && (
                    <p className="text-sm text-ink-tertiary">{section.emptyState}</p>
                  )}

                  {section.items.map((commitment) => (
                    <article key={commitment.id} className="rounded border border-soft p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium text-ink-primary">{commitment.text}</p>
                        <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                          {commitment.status}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-ink-tertiary">
                        {commitment.owner || "Unassigned"} · due {formatDueDate(commitment.due_date)}
                      </p>
                    </article>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {activeTab === "transcript" && (
        <section className="card p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Transcript</h2>
              <p className="mt-1 text-sm text-ink-secondary">
                Conversation view grouped by consecutive speaker turns.
              </p>
            </div>
            <span className="text-xs text-ink-tertiary">
              {detail.segments.length} segments
            </span>
          </div>

          <div className="mt-4 space-y-4">
            {transcriptGroups.length === 0 && (
              <p className="text-sm text-ink-tertiary">No transcript segments available.</p>
            )}

            {transcriptGroups.map((group, index) => {
              const alignRight = index % 2 === 1;
              return (
                <div
                  key={group.id}
                  className={`flex ${alignRight ? "justify-end" : "justify-start"}`}
                >
                  <article
                    className={`max-w-3xl rounded-2xl border border-soft p-4 ${
                      alignRight ? "bg-bg-control" : "bg-bg-surface-raised"
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-tertiary">
                      <span className="rounded-full border border-soft px-2 py-0.5">
                        {humanizeSpeaker(group.speakerId)}
                      </span>
                      <span>
                        {formatTranscriptTime(group.startMs)} - {formatTranscriptTime(group.endMs)}
                      </span>
                    </div>
                    <p className="mono mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-secondary">
                      {group.text}
                    </p>
                  </article>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
