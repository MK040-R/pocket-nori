"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getIndexStats, getTodayBriefing, type IndexStats, type TodayBriefing } from "@/lib/api";

export default function TodayPage() {
  const [briefing, setBriefing] = useState<TodayBriefing | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [todayData, statsData] = await Promise.all([getTodayBriefing(), getIndexStats()]);
        if (mounted) {
          setBriefing(todayData);
          setStats(statsData);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load today view");
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
  }, []);

  if (loading) {
    return <section className="card p-4 text-sm text-ink-secondary">Loading today view...</section>;
  }

  if (error || !briefing || !stats) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Today view not available"}
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Today&apos;s briefing</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Live view for `GET /calendar/today` and `GET /index/stats`.
        </p>

        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          <div className="rounded border border-soft p-3">
            <p className="text-ink-tertiary">Conversations</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.conversation_count}</p>
          </div>
          <div className="rounded border border-soft p-3">
            <p className="text-ink-tertiary">Topics</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.topic_count}</p>
          </div>
          <div className="rounded border border-soft p-3">
            <p className="text-ink-tertiary">Commitments</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.commitment_count}</p>
          </div>
          <div className="rounded border border-soft p-3">
            <p className="text-ink-tertiary">Entities</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.entity_count}</p>
          </div>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Upcoming meetings</h2>
        <div className="mt-3 space-y-2">
          {briefing.upcoming_meetings.map((meeting) => (
            <article key={meeting.id} className="rounded border border-soft p-3">
              <p className="font-medium">{meeting.title}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {new Date(meeting.start_time).toLocaleString()} · {meeting.attendees.join(", ")}
              </p>
            </article>
          ))}
          {briefing.upcoming_meetings.length === 0 && (
            <p className="text-sm text-ink-tertiary">No upcoming meetings from calendar yet.</p>
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Recent indexed activity</h2>
        <div className="mt-3 space-y-2">
          {briefing.recent_activity.map((activity) => (
            <article key={activity.conversation_id} className="rounded border border-soft p-3">
              <p className="font-medium">{activity.title}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {new Date(activity.meeting_date).toLocaleString()} · {activity.status}
              </p>
              <Link
                href={`/meetings/${activity.conversation_id}`}
                className="mt-2 inline-block text-xs text-accent underline decoration-accent/40 underline-offset-2"
              >
                Open meeting
              </Link>
            </article>
          ))}
          {briefing.recent_activity.length === 0 && (
            <p className="text-sm text-ink-tertiary">No indexed meetings yet.</p>
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Open commitments</h2>
        <div className="mt-3 space-y-2">
          {briefing.open_commitments.map((commitment) => (
            <article key={commitment.id} className="rounded border border-soft p-3">
              <p className="text-sm text-ink-primary">{commitment.text}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {commitment.owner} · due {commitment.due_date ?? "not specified"} · from{" "}
                {commitment.conversation_title}
              </p>
              <Link
                href={`/meetings/${commitment.conversation_id}`}
                className="mt-2 inline-block text-xs text-accent underline decoration-accent/40 underline-offset-2"
              >
                Open source meeting
              </Link>
            </article>
          ))}
          {briefing.open_commitments.length === 0 && (
            <p className="text-sm text-ink-tertiary">No open commitments right now.</p>
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">New cross-meeting connections</h2>
        <div className="mt-3 space-y-2">
          {briefing.recent_connections.map((connection) => (
            <article key={connection.id} className="rounded border border-soft p-3">
              <p className="font-medium">{connection.label}</p>
              <p className="mt-1 text-xs text-ink-tertiary">{connection.summary}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {connection.linked_type} · detected {new Date(connection.created_at).toLocaleString()}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {connection.related_conversations.map((conversation) => (
                  <Link
                    key={conversation.conversation_id}
                    href={`/meetings/${conversation.conversation_id}`}
                    className="rounded border border-soft px-2 py-1 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                  >
                    {conversation.title}
                  </Link>
                ))}
              </div>
            </article>
          ))}
          {briefing.recent_connections.length === 0 && (
            <p className="text-sm text-ink-tertiary">No new cross-meeting links detected yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
