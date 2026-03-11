"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { getTopics, search, type SearchResult, type TopicSummary } from "@/lib/api";

const FEATURED_TOPICS_LIMIT = 12;
const SEARCH_RESULTS_LIMIT = 10;

function normalizeValue(value: string): string {
  return value.trim().toLowerCase();
}

function formatTopicDate(value: string): string {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString();
}

function formatMeetingDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString();
}

function truncateText(value: string, maxLength = 280): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) {
    return compact;
  }
  return `${compact.slice(0, maxLength).trimEnd()}...`;
}

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSubmitted, setHasSubmitted] = useState(false);

  useEffect(() => {
    let mounted = true;

    const loadTopics = async () => {
      setTopicsLoading(true);
      try {
        const data = await getTopics();
        if (mounted) {
          setTopics(data);
        }
      } catch {
        if (mounted) {
          setTopics([]);
        }
      } finally {
        if (mounted) {
          setTopicsLoading(false);
        }
      }
    };

    void loadTopics();

    return () => {
      mounted = false;
    };
  }, []);

  const normalizedQuery = useMemo(() => normalizeValue(query), [query]);

  const matchedTopics = useMemo(() => {
    if (!normalizedQuery) {
      return [];
    }

    const terms = normalizedQuery.split(/\s+/).filter(Boolean);

    return [...topics]
      .filter((topic) => {
        const label = topic.label.toLowerCase();
        return label.includes(normalizedQuery) || terms.every((term) => label.includes(term));
      })
      .sort((left, right) => {
        const leftExact = left.label.toLowerCase() === normalizedQuery ? 1 : 0;
        const rightExact = right.label.toLowerCase() === normalizedQuery ? 1 : 0;
        if (leftExact !== rightExact) {
          return rightExact - leftExact;
        }
        if (left.conversation_count !== right.conversation_count) {
          return right.conversation_count - left.conversation_count;
        }
        return new Date(right.latest_date).getTime() - new Date(left.latest_date).getTime();
      });
  }, [normalizedQuery, topics]);

  const exactTopicMatch = useMemo(
    () => matchedTopics.find((topic) => topic.label.toLowerCase() === normalizedQuery) ?? null,
    [matchedTopics, normalizedQuery],
  );

  const featuredTopics = useMemo(
    () =>
      [...topics]
        .sort((left, right) => {
          if (left.conversation_count !== right.conversation_count) {
            return right.conversation_count - left.conversation_count;
          }
          return new Date(right.latest_date).getTime() - new Date(left.latest_date).getTime();
        })
        .slice(0, FEATURED_TOPICS_LIMIT),
    [topics],
  );

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setHasSubmitted(false);
      setLoading(false);
      setError(null);
      setResults([]);
      return;
    }

    if (exactTopicMatch) {
      router.push(`/topics/${exactTopicMatch.id}`);
      return;
    }

    setHasSubmitted(true);
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const data = await search(trimmedQuery, SEARCH_RESULTS_LIMIT);
      setResults(data);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Search across your meeting history. If your query matches a known topic, Farz will surface the
          topic first and route exact matches to the topic detail view.
        </p>

        <form onSubmit={onSubmit} className="mt-4 flex gap-2">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
            placeholder="Search your conversations"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded border border-emphasis bg-accent-subtle px-4 py-2 text-sm font-medium text-accent disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>
      </section>

      {!topicsLoading && normalizedQuery && matchedTopics.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Matching topics</h2>
            <p className="text-xs text-ink-tertiary">
              {matchedTopics.length === 1
                ? "1 topic matches this query"
                : `${matchedTopics.length} topics match this query`}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {matchedTopics.map((topic) => (
              <Link
                key={topic.id}
                href={`/topics/${topic.id}`}
                className="card block p-4 transition hover:border-emphasis"
              >
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold text-ink-primary">{topic.label}</h3>
                  <span className="mono rounded border border-soft px-2 py-1 text-xs text-ink-tertiary">
                    {topic.conversation_count}
                  </span>
                </div>
                <p className="mt-2 text-xs text-ink-tertiary">
                  Last mention: {formatTopicDate(topic.latest_date)}
                </p>
                <p className="mt-3 text-sm text-accent">Open topic detail</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {hasSubmitted && !loading && !error && matchedTopics.length === 0 && results.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">No results for this query.</section>
      )}

      {results.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Conversation excerpts</h2>
            <p className="text-xs text-ink-tertiary">
              Transcript context is shown as short excerpts only. Use the meeting link for full detail.
            </p>
          </div>
          {results.map((result) => (
            <article key={result.segment_id} className="card p-4">
              <p className="text-sm text-ink-primary">{truncateText(result.text)}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-ink-tertiary">
                <span>{result.conversation_title}</span>
                <span>{formatMeetingDate(result.meeting_date)}</span>
                <span className="mono">score {result.score.toFixed(2)}</span>
              </div>
              <div className="mt-3">
                <Link
                  href={`/meetings/${result.conversation_id}`}
                  className="text-sm text-accent hover:text-accent-hover"
                >
                  Open meeting detail
                </Link>
              </div>
            </article>
          ))}
        </section>
      )}

      <section className="card p-6">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Topic directory</h2>
            <p className="mt-1 text-sm text-ink-secondary">Jump straight into the strongest recurring topics.</p>
          </div>
          <Link href="/topics" className="text-xs text-accent hover:text-accent-hover">
            View all topics
          </Link>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {topicsLoading && <span className="text-sm text-ink-tertiary">Loading topics...</span>}
          {!topicsLoading &&
            featuredTopics.map((topic) => (
              <Link
                key={topic.id}
                href={`/topics/${topic.id}`}
                className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
              >
                {topic.label} <span className="mono">({topic.conversation_count})</span>
              </Link>
            ))}
        </div>
      </section>
    </div>
  );
}
