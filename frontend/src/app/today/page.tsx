"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getIndexStats, getTodayBriefing, type IndexStats, type TodayBriefing } from "@/lib/api";
import { formatDateTime, formatDueDate, formatMeetingTitle } from "@/lib/presentation";

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
          See your next two days of meetings, the latest indexed activity, and the commitments still open.
        </p>

        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          <Link href="/meetings" className="rounded border border-soft p-3 transition hover:border-emphasis">
            <p className="text-ink-tertiary">Conversations</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.conversation_count}</p>
          </Link>
          <Link href="/topics" className="rounded border border-soft p-3 transition hover:border-emphasis">
            <p className="text-ink-tertiary">Topics</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.topic_count}</p>
          </Link>
          <Link href="/commitments" className="rounded border border-soft p-3 transition hover:border-emphasis">
            <p className="text-ink-tertiary">Commitments</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.commitment_count}</p>
          </Link>
          <Link href="/entities" className="rounded border border-soft p-3 transition hover:border-emphasis">
            <p className="text-ink-tertiary">Entities</p>
            <p className="mono mt-1 text-lg text-ink-primary">{stats.entity_count}</p>
          </Link>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Upcoming meetings</h2>
        <div className="mt-3 space-y-2">
          {briefing.upcoming_meetings.map((meeting) => (
            <article key={meeting.id} className="rounded border border-soft p-3">
              <p className="font-medium">{formatMeetingTitle(meeting.title)}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {formatDateTime(meeting.start_time)} · {meeting.attendees.join(", ")}
              </p>
            </article>
          ))}
          {briefing.upcoming_meetings.length === 0 && (
            <p className="text-sm text-ink-tertiary">No upcoming meetings in the next two days.</p>
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Recent indexed activity</h2>
        <div className="mt-3 space-y-2">
          {briefing.recent_activity.map((activity) => (
            <article key={activity.conversation_id} className="rounded border border-soft p-3">
              <p className="font-medium">{formatMeetingTitle(activity.title)}</p>
              <p className="mt-1 text-xs text-ink-tertiary">
                {formatDateTime(activity.meeting_date)} · {activity.status}
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
                {commitment.owner} · due {formatDueDate(commitment.due_date)} · from{" "}
                {formatMeetingTitle(commitment.conversation_title)}
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
    </div>
  );
}
