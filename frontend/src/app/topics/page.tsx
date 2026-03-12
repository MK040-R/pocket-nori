"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getTopics, type TopicSummary } from "@/lib/api";
import { formatDate } from "@/lib/presentation";

export default function TopicsPage() {
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getTopics();
        if (mounted) {
          setTopics(data);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load topics");
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

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return topics;
    }
    return topics.filter((topic) => topic.label.toLowerCase().includes(normalized));
  }, [topics, query]);

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Topics</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Explore the recurring threads that keep showing up across your meetings.
        </p>

        <div className="mt-4">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder="Filter topics"
            className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
        </div>
      </section>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading topics...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && !error && filtered.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">No topics match your filter.</section>
      )}

      <section className="grid gap-3 md:grid-cols-2">
        {filtered.map((topic) => (
          <Link
            key={topic.id}
            href={`/topics/${topic.id}`}
            className="card block p-4 transition hover:border-emphasis"
          >
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-ink-primary">{topic.label}</h2>
              <span className="mono rounded border border-soft px-2 py-1 text-xs text-ink-tertiary">
                {topic.conversation_count}
              </span>
            </div>
            <p className="mt-2 text-xs text-ink-tertiary">
              Last mention: {formatDate(topic.latest_date)}
            </p>
          </Link>
        ))}
      </section>
    </div>
  );
}
