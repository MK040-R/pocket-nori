"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getCommitments,
  getIndexStats,
  getTodayBriefing,
  type Commitment,
  type IndexStats,
  type TodayBriefing,
} from "@/lib/api";
import { formatDueDate, formatMeetingTitle, formatDateTime } from "@/lib/presentation";

const kpiCards = [
  { label: "Conversations", href: "/meetings", key: "conversation_count" as const },
  { label: "Topics", href: "/topics", key: "topic_count" as const },
  { label: "Commitments", href: "/commitments", key: "commitment_count" as const },
  { label: "Entities", href: "/entities", key: "entity_count" as const },
];

export default function DashboardPage() {
  const [briefing, setBriefing] = useState<TodayBriefing | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [todayData, statsData, commitmentData] = await Promise.all([
          getTodayBriefing(),
          getIndexStats(),
          getCommitments("open"),
        ]);
        if (mounted) {
          setBriefing(todayData);
          setStats(statsData);
          setCommitments(commitmentData);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard");
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
    return <section className="card p-4 text-sm text-ink-secondary">Loading dashboard...</section>;
  }

  if (error || !briefing || !stats) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Dashboard unavailable"}
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          A quick view of your indexed meetings, active commitments, and the next two days of calendar context.
        </p>
      </section>

      <section className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card) => (
          <Link key={card.key} href={card.href} className="card block p-4 transition hover:border-emphasis">
            <p className="text-ink-tertiary">{card.label}</p>
            <p className="mono mt-1 text-xl text-ink-primary">{stats[card.key]}</p>
          </Link>
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="card p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Upcoming today and tomorrow</h2>
            <Link href="/today" className="text-xs text-accent hover:text-accent-hover">
              Open full view
            </Link>
          </div>
          <div className="mt-3 space-y-2">
            {briefing.upcoming_meetings.map((meeting) => (
              <div key={meeting.id} className="rounded border border-soft px-3 py-2">
                <p className="font-medium text-ink-primary">{formatMeetingTitle(meeting.title)}</p>
                <p className="mt-1 text-xs text-ink-tertiary">
                  {formatDateTime(meeting.start_time)} · {meeting.attendees.join(", ")}
                </p>
              </div>
            ))}
            {briefing.upcoming_meetings.length === 0 && (
              <p className="text-sm text-ink-tertiary">No upcoming meetings in the next two days.</p>
            )}
          </div>
        </article>

        <article className="card p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Open commitments</h2>
            <Link href="/commitments" className="text-xs text-accent hover:text-accent-hover">
              View all
            </Link>
          </div>

          <div className="mt-3 space-y-2">
            {commitments.slice(0, 4).map((commitment) => (
              <div key={commitment.id} className="rounded border border-soft px-3 py-2">
                <p className="text-sm text-ink-primary">{commitment.text}</p>
                <p className="mt-1 text-xs text-ink-tertiary">
                  {commitment.owner} · due {formatDueDate(commitment.due_date)} ·{" "}
                  {formatMeetingTitle(commitment.conversation_title)}
                </p>
              </div>
            ))}

            {commitments.length === 0 && (
              <p className="text-sm text-ink-tertiary">No open commitments in the current dataset.</p>
            )}
          </div>
        </article>
      </section>
    </div>
  );
}
