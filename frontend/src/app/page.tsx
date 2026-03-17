"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getCommitments,
  getHomeSummary,
  getIndexStats,
  getTodayBriefing,
  getUpcomingBriefs,
  isApiErrorStatus,
  type ActionType,
  type Commitment,
  type HomeSummary,
  type IndexStats,
  type TodayBriefing,
  type UpcomingBrief,
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

function formatMinutesUntilStart(minutes: number): string {
  if (minutes <= 0) {
    return "Starting now";
  }
  if (minutes === 1) {
    return "Starting in 1 minute";
  }
  return `Starting in ${minutes} minutes`;
}

function formatUpcomingTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function HomePage() {
  const [briefing, setBriefing] = useState<TodayBriefing | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [homeSummary, setHomeSummary] = useState<HomeSummary | null>(null);
  const [homeSummaryState, setHomeSummaryState] = useState<"loading" | "ready" | "hidden">("loading");
  const [upcomingBrief, setUpcomingBrief] = useState<UpcomingBrief | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission | "unsupported">("unsupported");
  const [actions, setActions] = useState<Record<ActionType, Commitment[]>>({
    commitment: [],
    follow_up: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) {
      setNotificationPermission("unsupported");
      return;
    }

    setNotificationPermission(Notification.permission);
  }, []);

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

    const loadUpcomingBriefs = async () => {
      try {
        const upcoming = await getUpcomingBriefs();
        if (!mounted) {
          return;
        }

        const nextBrief = [...upcoming]
          .filter((item) => item.minutes_until_start <= 60)
          .sort((left, right) => left.minutes_until_start - right.minutes_until_start)[0] ?? null;
        setUpcomingBrief(nextBrief);
      } catch (loadError) {
        if (!mounted) {
          return;
        }

        if (isApiErrorStatus(loadError, [404, 405, 501])) {
          setUpcomingBrief(null);
          return;
        }

        setUpcomingBrief(null);
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
    void loadUpcomingBriefs();
    void load();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (
      !upcomingBrief ||
      notificationPermission !== "granted" ||
      upcomingBrief.minutes_until_start > 30 ||
      typeof window === "undefined" ||
      !("Notification" in window)
    ) {
      return;
    }

    const notificationKey = `pocket-nori:brief:${upcomingBrief.brief_id}`;
    if (window.localStorage.getItem(notificationKey)) {
      return;
    }

    const notification = new Notification(`Brief ready: ${formatMeetingTitle(upcomingBrief.event_title)}`, {
      body: `${formatMinutesUntilStart(upcomingBrief.minutes_until_start)} · ${upcomingBrief.open_commitments_count} open actions`,
    });

    window.localStorage.setItem(notificationKey, new Date().toISOString());

    return () => {
      notification.close();
    };
  }, [notificationPermission, upcomingBrief]);

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

      {upcomingBrief && (
        <section className="card overflow-hidden border border-emphasis bg-[linear-gradient(135deg,rgba(0,194,122,0.14),rgba(255,255,255,0.96))] p-0">
          <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div className="px-6 py-6">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                Prep push
              </p>
              <h2 className="mt-2 text-xl font-semibold text-ink-primary">
                {formatMeetingTitle(upcomingBrief.event_title)}
              </h2>
              <p className="mt-2 text-sm font-medium text-accent">
                {formatMinutesUntilStart(upcomingBrief.minutes_until_start)}
              </p>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-ink-secondary">
                {upcomingBrief.preview}
              </p>

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-soft bg-white/80 px-3 py-1 text-xs font-medium text-ink-secondary">
                  {upcomingBrief.open_commitments_count} open actions
                </span>
                <span className="rounded-full border border-soft bg-white/80 px-3 py-1 text-xs font-medium text-ink-secondary">
                  {upcomingBrief.related_topic_count} related topics
                </span>
                {notificationPermission === "default" && upcomingBrief.minutes_until_start <= 30 && (
                  <button
                    type="button"
                    onClick={async () => {
                      if (!("Notification" in window)) {
                        return;
                      }
                      const result = await Notification.requestPermission();
                      setNotificationPermission(result);
                    }}
                    className="rounded-full border border-standard bg-white/80 px-3 py-1 text-xs font-medium text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
                  >
                    Enable browser alerts
                  </button>
                )}
              </div>
            </div>

            <div className="border-t border-soft bg-white/75 px-6 py-6 lg:border-l lg:border-t-0">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                Next up
              </p>
              <p className="mt-2 text-lg font-semibold text-ink-primary">
                {formatUpcomingTime(upcomingBrief.event_start)}
              </p>
              <p className="mt-2 text-sm leading-7 text-ink-secondary">
                Open the brief before the meeting starts and use the related topics as a fast agenda refresher.
              </p>
              <Link
                href={`/briefs/${upcomingBrief.brief_id}`}
                className="mt-5 inline-flex rounded-xl border border-emphasis bg-accent-subtle px-4 py-2 text-sm font-medium text-accent transition hover:border-accent"
              >
                View brief
              </Link>
            </div>
          </div>
        </section>
      )}

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
