"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getConversations, type ConversationSummary } from "@/lib/api";
import { formatDateTime, formatMeetingTitle, formatSourceLabel } from "@/lib/presentation";

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return "Duration pending";
  }
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

export default function MeetingsPage() {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

      <section className="grid gap-3">
        {items.map((meeting) => (
          <Link
            href={`/meetings/${meeting.id}`}
            key={meeting.id}
            className="card block p-4 transition hover:border-emphasis"
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">{formatMeetingTitle(meeting.title)}</h2>
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

            <div className="mt-2 flex flex-wrap gap-3 text-sm text-ink-tertiary">
              <span>{formatDateTime(meeting.meeting_date)}</span>
              <span className="mono">{formatDuration(meeting.duration_seconds)}</span>
              <span>{formatSourceLabel(meeting.source)}</span>
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
