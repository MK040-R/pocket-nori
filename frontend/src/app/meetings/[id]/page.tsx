"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getConversation, type ConversationDetail } from "@/lib/api";
import { formatDateTime, formatDueDate, formatMeetingTitle } from "@/lib/presentation";

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const conversationData = await getConversation(id);
        if (mounted) {
          setDetail(conversationData);
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
        <h1 className="text-2xl font-semibold">{formatMeetingTitle(detail.conversation.title)}</h1>
        <p className="mt-2 text-sm text-ink-tertiary">
          {formatDateTime(detail.conversation.meeting_date)} ·{" "}
          {detail.conversation.duration_seconds
            ? `${Math.round(detail.conversation.duration_seconds / 60)} min`
            : "Duration pending"}
        </p>
        {detail.conversation.latest_brief_id && (
          <p className="mt-3 text-sm">
            <Link
              href={`/briefs/${detail.conversation.latest_brief_id}`}
              className="text-accent hover:text-accent-hover"
            >
              Open latest brief
            </Link>
            {detail.conversation.latest_brief_generated_at && (
              <span className="text-ink-tertiary">
                {" "}
                · generated {formatDateTime(detail.conversation.latest_brief_generated_at)}
              </span>
            )}
          </p>
        )}
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Topics</h2>
        <div className="mt-3 space-y-3">
          {detail.topics.length === 0 && <p className="text-sm text-ink-tertiary">No topics yet.</p>}
          {detail.topics.map((topic) => (
            <article key={topic.id} className="rounded border border-soft p-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium">{topic.label}</h3>
                <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                  {topic.status}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-secondary">{topic.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Commitments</h2>
        <div className="mt-3 space-y-2">
          {detail.commitments.length === 0 && (
            <p className="text-sm text-ink-tertiary">No commitments extracted.</p>
          )}
          {detail.commitments.map((commitment) => (
            <article key={commitment.id} className="rounded border border-soft p-3">
              <p className="text-sm text-ink-primary">{commitment.text}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {commitment.owner} · due {formatDueDate(commitment.due_date)} · {commitment.status}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Entities</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {detail.entities.length === 0 && <p className="text-sm text-ink-tertiary">No entities detected.</p>}
          {detail.entities.map((entity) => (
            <span
              key={entity.id}
              className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-secondary"
            >
              {entity.name} · {entity.type} · {entity.mentions} mentions
            </span>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <details>
          <summary className="cursor-pointer text-lg font-semibold">Transcript segments</summary>
          <div className="mt-3 space-y-2">
            {detail.segments.length === 0 && <p className="text-sm text-ink-tertiary">No segments.</p>}
            {detail.segments.map((segment) => (
              <article key={segment.id} className="rounded border border-soft p-3">
                <p className="mono text-xs text-ink-tertiary">
                  {segment.speaker_id} · {segment.start_ms}ms - {segment.end_ms}ms
                </p>
                <p className="mono mt-1 text-sm text-ink-secondary">{segment.text}</p>
              </article>
            ))}
          </div>
        </details>
      </section>
    </div>
  );
}
