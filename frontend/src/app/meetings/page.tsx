"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getConversations, type ConversationSummary } from "@/lib/api";
import { formatDateTime, formatMeetingTitle, formatSourceLabel } from "@/lib/presentation";

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return "Duration pending";
  }
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

type MeetingGroupKey = "today" | "this_week" | "earlier";

function startOfDay(value: Date): Date {
  const next = new Date(value);
  next.setHours(0, 0, 0, 0);
  return next;
}

function startOfWeek(value: Date): Date {
  const next = startOfDay(value);
  const dayIndex = (next.getDay() + 6) % 7;
  next.setDate(next.getDate() - dayIndex);
  return next;
}

function classifyMeetingGroup(value: string, now: Date): MeetingGroupKey {
  const meetingDate = new Date(value);
  if (Number.isNaN(meetingDate.getTime())) {
    return "earlier";
  }

  const meetingDay = startOfDay(meetingDate);
  const todayStart = startOfDay(now);
  const weekStart = startOfWeek(now);

  if (meetingDay.getTime() === todayStart.getTime()) {
    return "today";
  }
  if (meetingDay >= weekStart) {
    return "this_week";
  }
  return "earlier";
}

const MEETING_GROUP_LABELS: Record<MeetingGroupKey, string> = {
  today: "Today",
  this_week: "This week",
  earlier: "Earlier",
};

export default function MeetingsPage() {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const groupedItems = useMemo(() => {
    const groups: Record<MeetingGroupKey, ConversationSummary[]> = {
      today: [],
      this_week: [],
      earlier: [],
    };
    const sorted = [...items].sort(
      (left, right) => new Date(right.meeting_date).getTime() - new Date(left.meeting_date).getTime(),
    );

    sorted.forEach((meeting) => {
      groups[classifyMeetingGroup(meeting.meeting_date, new Date())].push(meeting);
    });

    return (Object.keys(groups) as MeetingGroupKey[])
      .map((key) => ({
        key,
        label: MEETING_GROUP_LABELS[key],
        items: groups[key],
      }))
      .filter((group) => group.items.length > 0);
  }, [items]);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await getConversations();
        if (mounted) {
          setItems(result);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load conversations");
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

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Meetings</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Review indexed meetings, open each conversation, and move into topic and action detail.
        </p>
      </section>

      <Link
        href="/onboarding"
        className="card flex items-center justify-between gap-4 border-soft bg-bg-control px-5 py-4 transition hover:border-emphasis"
      >
        <div>
          <p className="text-sm font-medium text-ink-primary">Import past meetings</p>
          <p className="mt-1 text-sm text-ink-secondary">
            Bring in additional recordings whenever you want to expand your meeting history.
          </p>
        </div>
        <span className="shrink-0 text-sm text-ink-tertiary" aria-hidden="true">
          →
        </span>
      </Link>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading meetings...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && !error && items.length === 0 && (
        <section className="card p-5">
          <p className="text-sm text-ink-secondary">No meetings yet. Import past recordings to get started.</p>
        </section>
      )}

      {items.length > 0 && (
        <div className="space-y-6">
          {groupedItems.map((group) => (
            <section key={group.key} className="space-y-3">
              <h2 className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                {group.label}
              </h2>

              <div className="grid gap-3">
                {group.items.map((meeting) => (
                  <Link
                    href={`/meetings/${meeting.id}`}
                    key={meeting.id}
                    className="card block p-4 transition hover:border-emphasis"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="text-base font-semibold">{formatMeetingTitle(meeting.title)}</h3>
                        {meeting.topic_labels.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {meeting.topic_labels.slice(0, 3).map((label) => (
                              <span
                                key={`${meeting.id}-${label}`}
                                className="rounded-full border border-emphasis bg-accent-subtle px-2 py-0.5 text-xs text-accent"
                              >
                                {label}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      <span
                        className={`inline-flex items-center gap-2 rounded border px-2 py-1 text-xs ${
                          meeting.status === "indexed"
                            ? "border-emphasis bg-accent-subtle text-accent"
                            : "border-soft text-ink-tertiary"
                        }`}
                      >
                        {meeting.status === "indexed" ? (
                          <span className="h-2 w-2 rounded-full bg-accent" />
                        ) : (
                          <span className="h-3 w-3 animate-spin rounded-full border border-ink-tertiary border-t-transparent" />
                        )}
                        {meeting.status}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-3 text-sm text-ink-tertiary">
                      <span>{formatDateTime(meeting.meeting_date)}</span>
                      <span className="mono">{formatDuration(meeting.duration_seconds)}</span>
                      <span>{formatSourceLabel(meeting.source)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
