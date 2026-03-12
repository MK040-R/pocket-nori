"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getTopic, getTopicArc, type TopicArc, type TopicDetail } from "@/lib/api";
import { formatDateTime, formatMeetingTitle } from "@/lib/presentation";

function formatOffset(value: number | null): string {
  if (value === null || value < 0) {
    return "--:--";
  }
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function TopicDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [topic, setTopic] = useState<TopicDetail | null>(null);
  const [topicArc, setTopicArc] = useState<TopicArc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [topicData, arcData] = await Promise.all([getTopic(id), getTopicArc(id)]);
        if (mounted) {
          setTopic(topicData);
          setTopicArc(arcData);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load topic");
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
    return <section className="card p-4 text-sm text-ink-secondary">Loading topic...</section>;
  }

  if (error || !topic || !topicArc) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Topic not found"}
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="mb-2 text-xs uppercase tracking-[0.06em] text-ink-tertiary">Topic detail</p>
            <h1 className="text-2xl font-semibold text-ink-primary">{topic.label}</h1>
            <p className="mt-2 max-w-3xl text-sm text-ink-secondary">{topic.summary}</p>
          </div>
          <Link
            href="/topics"
            className="rounded border border-standard px-3 py-1.5 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
          >
            All topics
          </Link>
        </div>
      </section>

      <section className="card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Topic arc</h2>
            <p className="mt-1 text-sm text-ink-secondary">{topicArc.summary}</p>
          </div>
          <div className="text-right text-xs text-ink-tertiary">
            <p>Status: {topicArc.status}</p>
            <p>Trend: {topicArc.trend}</p>
            <p>Meetings: {topicArc.conversation_count}</p>
          </div>
        </div>

        <div className="mt-3 space-y-3">
          {topicArc.arc_points.length === 0 && (
            <p className="text-sm text-ink-tertiary">No timeline points available yet.</p>
          )}

          {topicArc.arc_points.map((point) => (
            <article key={`${point.topic_id}-${point.conversation_id}`} className="rounded border border-soft p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Link
                    href={`/meetings/${point.conversation_id}`}
                    className="text-sm font-medium text-ink-primary hover:text-accent"
                  >
                    {formatMeetingTitle(point.conversation_title)}
                  </Link>
                  <p className="mt-1 text-xs text-ink-tertiary">{formatDateTime(point.occurred_at)}</p>
                </div>
                <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                  {point.topic_status}
                </span>
              </div>

              <p className="mt-2 text-sm text-ink-secondary">{point.summary}</p>

              {(point.citation_segment_id || point.citation_snippet) && (
                <div className="mt-2 rounded border border-soft bg-bg-control px-3 py-2">
                  <p className="mono text-xs text-ink-tertiary">
                    Citation · {formatOffset(point.transcript_offset_seconds)}
                    {point.citation_segment_id ? ` · ${point.citation_segment_id}` : ""}
                  </p>
                  {point.citation_snippet && (
                    <p className="mono mt-1 text-xs text-ink-secondary">
                      &quot;{point.citation_snippet}&quot;
                    </p>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Related conversations</h2>
        <div className="mt-3 space-y-2">
          {topic.conversations.length === 0 && (
            <p className="text-sm text-ink-tertiary">No conversations linked yet.</p>
          )}
          {topic.conversations.map((conversation) => (
            <Link
              key={conversation.id}
              href={`/meetings/${conversation.id}`}
              className="block rounded border border-soft p-3 transition hover:border-emphasis"
            >
              <p className="text-sm font-medium text-ink-primary">
                {formatMeetingTitle(conversation.title)}
              </p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {formatDateTime(conversation.meeting_date)}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Key quotes</h2>
        <div className="mt-3 space-y-2">
          {topic.key_quotes.length === 0 && (
            <p className="text-sm text-ink-tertiary">No quotes available for this topic.</p>
          )}
          {topic.key_quotes.map((quote, index) => (
            <blockquote
              key={`${topic.id}-quote-${index + 1}`}
              className="rounded border border-soft bg-bg-control px-3 py-2 text-sm text-ink-secondary"
            >
              “{quote}”
            </blockquote>
          ))}
        </div>
      </section>
    </div>
  );
}
