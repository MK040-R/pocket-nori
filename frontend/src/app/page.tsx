"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getCommitments,
  getHomeSummary,
  getIndexStats,
  getTodayBriefing,
  type ActionType,
  type Commitment,
  type HomeSummary,
  type IndexStats,
  type TodayBriefing,
} from "@/lib/api";
import { formatDueDate, formatMeetingTitle } from "@/lib/presentation";

const kpiCards = [
  { label: "Conversations", href: "/meetings", key: "conversation_count" as const },
  { label: "Topics", href: "/topics", key: "topic_count" as const },
  { label: "Actions", href: "/commitments", key: "commitment_count" as const },
  { label: "Entities", href: "/entities", key: "entity_count" as const },
];

function ActionList({
  items,
  emptyLabel,
}: {
  items: Commitment[];
  emptyLabel: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-ink-tertiary">{emptyLabel}</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.id} className="rounded border border-soft px-3 py-2">
          <p className="text-sm text-ink-primary">{item.text}</p>
          <p className="mt-1 text-xs text-ink-tertiary">
            {item.owner || "Unassigned"} · due {formatDueDate(item.due_date)} ·{" "}
            {item.conversation_title ? formatMeetingTitle(item.conversation_title) : "Manual action"}
          </p>
        </div>
      ))}
    </div>
  );
}

function formatSummaryUpdatedAt(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Updated recently";
  }

  const now = new Date();
  const diffMinutes = Math.max(1, Math.round((now.getTime() - parsed.getTime()) / 60000));
  if (diffMinutes < 60) {
    return `Updated ${diffMinutes}m ago`;
  }

  const diffHours = Math.max(1, Math.round(diffMinutes / 60));
  if (now.toDateString() === parsed.toDateString()) {
    return `Updated ${diffHours}h ago`;
  }

  return `Updated ${parsed.toLocaleDateString()}`;
}

export default function HomePage() {
  const [briefing, setBriefing] = useState<TodayBriefing | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [homeSummary, setHomeSummary] = useState<HomeSummary | null>(null);
  const [homeSummaryState, setHomeSummaryState] = useState<"loading" | "ready" | "hidden">("loading");
  const [actions, setActions] = useState<Record<ActionType, Commitment[]>>({
    commitment: [],
    follow_up: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const loadSummary = async () => {
      setHomeSummaryState("loading");
      try {
        const summaryData = await getHomeSummary();
        if (!mounted) {
          return;
        }
        if (summaryData.summary.trim()) {
          setHomeSummary(summaryData);
          setHomeSummaryState("ready");
          return;
        }
      } catch {
        // Hide the summary card silently if this optional endpoint fails.
      }

      if (mounted) {
        setHomeSummary(null);
        setHomeSummaryState("hidden");
      }
    };

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [todayData, statsData, commitmentsData, followUpsData] = await Promise.all([
          getTodayBriefing(),
          getIndexStats(),
          getCommitments("open", { actionType: "commitment", limit: 3 }),
          getCommitments("open", { actionType: "follow_up", limit: 3 }),
        ]);
        if (mounted) {
          setBriefing(todayData);
          setStats(statsData);
          setActions({
            commitment: commitmentsData,
            follow_up: followUpsData,
          });
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load home");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    void loadSummary();
    void load();

    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <section className="card p-4 text-sm text-ink-secondary">Loading home...</section>;
  }

  if (error || !briefing || !stats) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Home unavailable"}
      </section>
    );
  }

  const formatCalendarDate = (value: string) =>
    new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      weekday: "short",
    });

  const formatCalendarTime = (value: string) =>
    new Date(value).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Home</h1>
      </section>

      {homeSummaryState !== "hidden" && (
        <section className="card p-6">
          {homeSummaryState === "loading" ? (
            <div className="space-y-3 animate-pulse">
              <div className="h-4 w-28 rounded bg-bg-control" />
              <div className="h-4 w-full rounded bg-bg-control" />
              <div className="h-4 w-4/5 rounded bg-bg-control" />
            </div>
          ) : homeSummary ? (
            <div>
              <h2 className="text-lg font-semibold">Quick Summary</h2>
              <p className="mt-3 text-sm leading-7 text-ink-secondary">{homeSummary.summary}</p>
              <p className="mt-4 text-xs text-ink-tertiary">
                {formatSummaryUpdatedAt(homeSummary.generated_at)}
              </p>
            </div>
          ) : null}
        </section>
      )}

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
            <h2 className="text-lg font-semibold">Coming Up</h2>
            <Link href="/today" className="text-xs text-accent hover:text-accent-hover">
              Open full view
            </Link>
          </div>
          <div className="mt-3 space-y-2">
            {briefing.upcoming_meetings.map((meeting) => (
              <div
                key={meeting.id}
                className="grid grid-cols-[92px_minmax(0,1fr)] gap-3 rounded border border-soft px-3 py-2"
              >
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                  {formatCalendarDate(meeting.start_time)}
                </p>
                <p className="min-w-0 text-sm text-ink-primary">
                  <span className="text-ink-secondary">{formatCalendarTime(meeting.start_time)}</span>
                  {" · "}
                  <span className="font-medium">{formatMeetingTitle(meeting.title)}</span>
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
            <h2 className="text-lg font-semibold">Actions</h2>
            <Link href="/commitments" className="text-xs text-accent hover:text-accent-hover">
              View all
            </Link>
          </div>

          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                Commitments
              </p>
              <ActionList
                items={actions.commitment}
                emptyLabel="No open commitments in the current dataset."
              />
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                Follow-ups
              </p>
              <ActionList
                items={actions.follow_up}
                emptyLabel="No open follow-ups in the current dataset."
              />
            </div>
          </div>
        </article>
      </section>
    </div>
  );
}
