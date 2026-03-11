"use client";

import { FormEvent, useState } from "react";
import { useEffect } from "react";
import Link from "next/link";

import { getTopics, search, type SearchResult, type TopicSummary } from "@/lib/api";

export default function SearchPage() {
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

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setHasSubmitted(true);
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const data = await search(query, 10);
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
          Live semantic search using `POST /search` with topic chips from `GET /topics`.
        </p>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-[0.06em] text-ink-tertiary">Topic directory</p>
            <Link href="/topics" className="text-xs text-accent hover:text-accent-hover">
              View all topics
            </Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {topicsLoading && <span className="text-sm text-ink-tertiary">Loading topics...</span>}
            {!topicsLoading &&
              topics.map((topic) => (
                <button
                  key={topic.id}
                  type="button"
                  onClick={async () => {
                    setQuery(topic.label);
                    setHasSubmitted(true);
                    setLoading(true);
                    setError(null);
                    setResults([]);
                    try {
                      const data = await search(topic.label, 10);
                      setResults(data);
                    } catch (submitError) {
                      setError(submitError instanceof Error ? submitError.message : "Search failed");
                    } finally {
                      setLoading(false);
                    }
                  }}
                  className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                >
                  {topic.label} <span className="mono">({topic.conversation_count})</span>
                </button>
              ))}
          </div>
        </div>

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

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {hasSubmitted && !loading && !error && results.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">No results for this query.</section>
      )}

      <section className="space-y-3">
        {results.map((result) => (
          <article key={result.segment_id} className="card p-4">
            <p className="text-sm text-ink-primary">{result.text}</p>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink-tertiary">
              <span>{result.conversation_title}</span>
              <span>{new Date(result.meeting_date).toLocaleDateString()}</span>
              <span className="mono">score {result.score.toFixed(2)}</span>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
