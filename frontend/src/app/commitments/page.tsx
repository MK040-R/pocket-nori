"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getCommitments, resolveCommitment, type Commitment } from "@/lib/api";
import { formatDate, formatDueDate, formatMeetingTitle } from "@/lib/presentation";

type FilterState = {
  assignee: string;
  topic: string;
  meeting: string;
  fromDate: string;
  toDate: string;
};

const EMPTY_FILTERS: FilterState = {
  assignee: "",
  topic: "",
  meeting: "",
  fromDate: "",
  toDate: "",
};

function buildCommitmentOptions(filters: FilterState) {
  return {
    assignee: filters.assignee.trim() || undefined,
    topic: filters.topic.trim() || undefined,
    meeting: filters.meeting.trim() || undefined,
    meetingDateFrom: filters.fromDate ? `${filters.fromDate}T00:00:00+00:00` : undefined,
    meetingDateTo: filters.toDate ? `${filters.toDate}T23:59:59+00:00` : undefined,
  };
}

function FilterSummary({ filters }: { filters: FilterState }) {
  const entries = [
    filters.assignee && `Assignee: ${filters.assignee}`,
    filters.topic && `Topic: ${filters.topic}`,
    filters.meeting && `Meeting: ${filters.meeting}`,
    filters.fromDate && `From: ${filters.fromDate}`,
    filters.toDate && `To: ${filters.toDate}`,
  ].filter(Boolean);

  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs text-ink-tertiary">
      {entries.map((entry) => (
        <span key={entry} className="rounded border border-soft bg-bg-control px-2 py-1">
          {entry}
        </span>
      ))}
    </div>
  );
}

function CommitmentCard({
  item,
  expanded,
  onToggle,
  resolving,
  onResolve,
  showResolve,
}: {
  item: Commitment;
  expanded: boolean;
  onToggle: () => void;
  resolving: boolean;
  onResolve?: () => Promise<void>;
  showResolve: boolean;
}) {
  return (
    <article className="rounded border border-soft p-3">
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left"
      >
        <p className="text-sm text-ink-primary">{item.text}</p>
        <p className="mt-1 text-xs text-ink-tertiary">
          {item.owner} · due {formatDueDate(item.due_date)} · {formatMeetingTitle(item.conversation_title)}
        </p>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-soft pt-3 text-sm">
          <div className="grid gap-2 text-xs text-ink-tertiary md:grid-cols-2">
            <p>Assignee: <span className="text-ink-secondary">{item.owner}</span></p>
            <p>Due date: <span className="text-ink-secondary">{formatDueDate(item.due_date)}</span></p>
            <p>Meeting date: <span className="text-ink-secondary">{formatDate(item.meeting_date, "Unknown")}</span></p>
            <p>Status: <span className="text-ink-secondary">{item.status}</span></p>
          </div>

          <div>
            <p className="text-xs uppercase tracking-[0.06em] text-ink-tertiary">Topic thread</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.topic_labels.length > 0 ? (
                item.topic_labels.map((label) => (
                  <span
                    key={`${item.id}-${label}`}
                    className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-secondary"
                  >
                    {label}
                  </span>
                ))
              ) : (
                <span className="text-xs text-ink-tertiary">No linked topic thread yet.</span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href={`/meetings/${item.conversation_id}`}
              className="text-xs text-accent hover:text-accent-hover"
            >
              Open meeting detail
            </Link>
            {showResolve && onResolve && (
              <button
                type="button"
                disabled={resolving}
                onClick={async (event) => {
                  event.stopPropagation();
                  await onResolve();
                }}
                className="rounded border border-emphasis bg-accent-subtle px-2 py-1 text-xs font-medium text-accent disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
              >
                {resolving ? "Resolving..." : "Mark resolved"}
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export default function CommitmentsPage() {
  const [openItems, setOpenItems] = useState<Commitment[]>([]);
  const [resolvedItems, setResolvedItems] = useState<Commitment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [activeFilters, setActiveFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const options = buildCommitmentOptions(activeFilters);
        const [openData, resolvedData] = await Promise.all([
          getCommitments("open", options),
          getCommitments("resolved", options),
        ]);
        if (mounted) {
          setOpenItems(openData);
          setResolvedItems(resolvedData);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load commitments");
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
  }, [activeFilters]);

  const hasActiveFilters = useMemo(
    () => Object.values(activeFilters).some((value) => value.trim() !== ""),
    [activeFilters],
  );

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Commitments</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Review real action items across your meetings, filter them by owner, topic, meeting, and date,
          and resolve them once the work is done.
        </p>

        <form
          className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            setActiveFilters({ ...filters });
          }}
        >
          <input
            value={filters.assignee}
            onChange={(event) => {
              setFilters((current) => ({ ...current, assignee: event.target.value }));
            }}
            placeholder="Assignee"
            className="rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
          <input
            value={filters.topic}
            onChange={(event) => {
              setFilters((current) => ({ ...current, topic: event.target.value }));
            }}
            placeholder="Topic"
            className="rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
          <input
            value={filters.meeting}
            onChange={(event) => {
              setFilters((current) => ({ ...current, meeting: event.target.value }));
            }}
            placeholder="Meeting"
            className="rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
          <input
            type="date"
            value={filters.fromDate}
            onChange={(event) => {
              setFilters((current) => ({ ...current, fromDate: event.target.value }));
            }}
            className="rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
          <input
            type="date"
            value={filters.toDate}
            onChange={(event) => {
              setFilters((current) => ({ ...current, toDate: event.target.value }));
            }}
            className="rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
          <div className="flex gap-2 md:col-span-2 xl:col-span-5">
            <button
              type="submit"
              className="rounded border border-emphasis bg-accent-subtle px-3 py-2 text-xs font-medium text-accent"
            >
              Apply filters
            </button>
            {hasActiveFilters && (
              <button
                type="button"
                onClick={() => {
                  setFilters(EMPTY_FILTERS);
                  setActiveFilters(EMPTY_FILTERS);
                }}
                className="rounded border border-standard px-3 py-2 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
              >
                Clear
              </button>
            )}
          </div>
        </form>

        <FilterSummary filters={activeFilters} />
      </section>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading commitments...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && (
        <section className="grid gap-4 lg:grid-cols-2">
          <article className="card p-5">
            <h2 className="text-lg font-semibold">Open</h2>
            <div className="mt-3 space-y-2">
              {openItems.length === 0 && <p className="text-sm text-ink-tertiary">No open commitments.</p>}
              {openItems.map((item) => (
                <CommitmentCard
                  key={item.id}
                  item={item}
                  expanded={expandedId === item.id}
                  onToggle={() => {
                    setExpandedId((current) => (current === item.id ? null : item.id));
                  }}
                  resolving={resolvingId === item.id}
                  showResolve
                  onResolve={async () => {
                    setResolvingId(item.id);
                    setError(null);
                    try {
                      const resolved = await resolveCommitment(item.id);
                      setOpenItems((current) => current.filter((candidate) => candidate.id !== resolved.id));
                      setResolvedItems((current) => [resolved, ...current]);
                      setExpandedId(resolved.id);
                    } catch (resolveError) {
                      setError(
                        resolveError instanceof Error
                          ? resolveError.message
                          : "Failed to resolve commitment",
                      );
                    } finally {
                      setResolvingId(null);
                    }
                  }}
                />
              ))}
            </div>
          </article>

          <article className="card p-5">
            <h2 className="text-lg font-semibold">Resolved</h2>
            <div className="mt-3 space-y-2">
              {resolvedItems.length === 0 && (
                <p className="text-sm text-ink-tertiary">No resolved commitments.</p>
              )}
              {resolvedItems.map((item) => (
                <CommitmentCard
                  key={item.id}
                  item={item}
                  expanded={expandedId === item.id}
                  onToggle={() => {
                    setExpandedId((current) => (current === item.id ? null : item.id));
                  }}
                  resolving={false}
                  showResolve={false}
                />
              ))}
            </div>
          </article>
        </section>
      )}
    </div>
  );
}
