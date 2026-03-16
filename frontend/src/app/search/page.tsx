"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ask,
  getTopics,
  search,
  type AskResponse,
  type SearchResult,
  type TopicSummary,
} from "@/lib/api";
import { formatDate, formatMeetingTitle } from "@/lib/presentation";

const FEATURED_TOPICS_LIMIT = 12;
const SEARCH_RESULTS_LIMIT = 10;

type SearchMode = "find" | "ask";

function normalizeValue(value: string): string {
  return value.trim().toLowerCase();
}

function buildSearchParams(query: string): string {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  return params.toString();
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

function truncateText(value: string, maxLength = 280): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) {
    return compact;
  }
  return `${compact.slice(0, maxLength).trimEnd()}...`;
}

const RESULT_TYPE_LABELS: Record<SearchResult["result_type"], string> = {
  topic: "Topic",
  entity: "Person / Project",
  meeting: "Meeting",
  segment: "Transcript",
};

const RESULT_TYPE_LINKS: Record<SearchResult["result_type"], (r: SearchResult) => string> = {
  topic: (r) => `/topics/${r.result_id}`,
  entity: (r) => `/meetings/${r.conversation_id}`,
  meeting: (r) => `/meetings/${r.result_id}`,
  segment: (r) => `/meetings/${r.conversation_id}`,
};

export default function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<SearchMode>("find");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [askResponse, setAskResponse] = useState<AskResponse | null>(null);
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const manualUrlSyncRef = useRef<string | null>(null);
  const urlQuery = searchParams.get("q") ?? "";

  useEffect(() => {
    let mounted = true;

    const loadTopics = async () => {
      setTopicsLoading(true);
      try {
        const data = await getTopics({ minConversations: 1 });
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
        .filter((topic) => topic.conversation_count >= 2)
        .sort((left, right) => {
          if (left.conversation_count !== right.conversation_count) {
            return right.conversation_count - left.conversation_count;
          }
          return new Date(right.latest_date).getTime() - new Date(left.latest_date).getTime();
        })
        .slice(0, FEATURED_TOPICS_LIMIT),
    [topics],
  );

  const emergingTopics = useMemo(
    () =>
      [...topics]
        .filter((topic) => topic.conversation_count === 1)
        .sort((left, right) => new Date(right.latest_date).getTime() - new Date(left.latest_date).getTime())
        .slice(0, 4),
    [topics],
  );

  // Group "find" results by result_type
  const groupedResults = useMemo(() => {
    const order: SearchResult["result_type"][] = ["topic", "meeting", "entity", "segment"];
    const groups = new Map<SearchResult["result_type"], SearchResult[]>();
    for (const result of results) {
      const existing = groups.get(result.result_type);
      if (existing) {
        existing.push(result);
      } else {
        groups.set(result.result_type, [result]);
      }
    }
    return order.map((type) => ({ type, items: groups.get(type) ?? [] })).filter((g) => g.items.length > 0);
  }, [results]);

  const runSearch = useCallback(
    async (
      rawQuery: string,
      nextMode: SearchMode,
      options: { allowTopicRedirect: boolean },
    ) => {
      const trimmedQuery = rawQuery.trim();
      if (!trimmedQuery) {
        setQuery("");
        setHasSubmitted(false);
        setLoading(false);
        setError(null);
        setResults([]);
        setAskResponse(null);
        return;
      }

      if (nextMode === "find" && options.allowTopicRedirect && exactTopicMatch) {
        router.push(`/topics/${exactTopicMatch.id}`);
        return;
      }

      setHasSubmitted(true);
      setLoading(true);
      setError(null);
      setResults([]);
      setAskResponse(null);

      const dateOptions = {
        ...(dateFrom ? { dateFrom } : {}),
        ...(dateTo ? { dateTo } : {}),
      };

      try {
        if (nextMode === "ask") {
          const data = await ask(trimmedQuery, dateOptions);
          setAskResponse(data);
        } else {
          const data = await search(trimmedQuery, SEARCH_RESULTS_LIMIT, dateOptions);
          setResults(data);
        }
      } catch (submitError) {
        setError(submitError instanceof Error ? submitError.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [dateFrom, dateTo, exactTopicMatch, router],
  );

  useEffect(() => {
    if (manualUrlSyncRef.current !== null) {
      const shouldSkipSync = manualUrlSyncRef.current === urlQuery;
      manualUrlSyncRef.current = null;
      if (shouldSkipSync) {
        return;
      }
    }

    setQuery(urlQuery);

    if (!urlQuery.trim()) {
      setHasSubmitted(false);
      setLoading(false);
      setError(null);
      setResults([]);
      setAskResponse(null);
      return;
    }

    setMode("find");
    void runSearch(urlQuery, "find", { allowTopicRedirect: false });
  }, [runSearch, urlQuery]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    const nextParams = buildSearchParams(trimmedQuery);
    setQuery(trimmedQuery);
    manualUrlSyncRef.current = trimmedQuery;
    router.replace(`/search${nextParams ? `?${nextParams}` : ""}`);
    await runSearch(trimmedQuery, mode, { allowTopicRedirect: true });
  };

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Search</h1>
            <p className="mt-1 text-sm text-ink-secondary">
              {mode === "find"
                ? "Search across topics, meetings, people, and transcripts."
                : "Ask a question — Pocket Nori will answer from your meeting history with citations."}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex rounded border border-soft overflow-hidden shrink-0">
            <button
              type="button"
              onClick={() => { setMode("find"); setHasSubmitted(false); setResults([]); setAskResponse(null); setError(null); }}
              className={`px-4 py-2 text-sm font-medium transition ${
                mode === "find"
                  ? "bg-accent-subtle text-accent border-r border-emphasis"
                  : "text-ink-muted hover:text-ink-primary border-r border-soft"
              }`}
            >
              Find
            </button>
            <button
              type="button"
              onClick={() => { setMode("ask"); setHasSubmitted(false); setResults([]); setAskResponse(null); setError(null); }}
              className={`px-4 py-2 text-sm font-medium transition ${
                mode === "ask"
                  ? "bg-accent-subtle text-accent"
                  : "text-ink-muted hover:text-ink-primary"
              }`}
            >
              Ask
            </button>
          </div>
        </div>

        <form onSubmit={onSubmit} className="mt-4 space-y-3">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
              className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
              placeholder={mode === "ask" ? "What was decided about the AWS migration?" : "Search your conversations"}
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded border border-emphasis bg-accent-subtle px-4 py-2 text-sm font-medium text-accent disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted shrink-0"
            >
              {loading ? (mode === "ask" ? "Thinking..." : "Searching...") : (mode === "ask" ? "Ask" : "Search")}
            </button>
          </div>

          {/* Optional date range filters */}
          <div className="flex flex-wrap gap-3 items-center">
            <span className="text-xs text-ink-tertiary">Filter by date:</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); }}
              className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-primary outline-none focus:border-emphasis"
              aria-label="From date"
            />
            <span className="text-xs text-ink-tertiary">to</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); }}
              className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-primary outline-none focus:border-emphasis"
              aria-label="To date"
            />
            {(dateFrom || dateTo) && (
              <button
                type="button"
                onClick={() => { setDateFrom(""); setDateTo(""); }}
                className="text-xs text-ink-tertiary hover:text-ink-primary"
              >
                Clear dates
              </button>
            )}
          </div>
        </form>
      </section>

      {/* Matched topics (Find mode only, client-side) */}
      {mode === "find" && !topicsLoading && normalizedQuery && matchedTopics.length > 0 && (
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

      {hasSubmitted && !loading && !error && mode === "find" && matchedTopics.length === 0 && results.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">No results for this query.</section>
      )}

      {hasSubmitted && !loading && !error && mode === "ask" && !askResponse && (
        <section className="card p-4 text-sm text-ink-tertiary">No answer available.</section>
      )}

      {/* Ask mode: answer card */}
      {mode === "ask" && askResponse && (
        <section className="space-y-4">
          <article className="card p-6">
            <h2 className="text-base font-semibold text-ink-primary mb-3">Answer</h2>
            <p className="text-sm text-ink-primary leading-relaxed whitespace-pre-wrap">{askResponse.answer}</p>

            {askResponse.citations.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-ink-secondary hover:text-ink-primary">
                  Sources ({askResponse.citations.length})
                </summary>
                <div className="mt-3 space-y-3">
                  {askResponse.citations.map((citation, index) => (
                    <div key={`${citation.result_id}-${index}`} className="rounded border border-soft bg-surface-raised p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="mono text-xs text-ink-tertiary">[{index + 1}]</span>
                        <span className="rounded border border-soft px-1.5 py-0.5 text-xs text-ink-secondary capitalize">
                          {citation.result_type}
                        </span>
                        <span className="text-xs text-ink-secondary">{citation.conversation_title}</span>
                        <span className="text-xs text-ink-tertiary">{formatDate(citation.meeting_date)}</span>
                      </div>
                      {citation.snippet && (
                        <p className="text-xs text-ink-tertiary mt-1">{truncateText(citation.snippet, 200)}</p>
                      )}
                      <Link
                        href={`/meetings/${citation.conversation_id}`}
                        className="mt-2 inline-block text-xs text-accent hover:text-accent-hover"
                      >
                        Open meeting
                      </Link>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </article>
        </section>
      )}

      {/* Find mode: grouped results */}
      {mode === "find" && groupedResults.length > 0 && (
        <section className="space-y-6">
          {groupedResults.map(({ type, items }) => (
            <div key={type} className="space-y-3">
              <h2 className="text-lg font-semibold">{RESULT_TYPE_LABELS[type]}</h2>
              {items.map((result) => (
                <article key={result.result_id} className="card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium text-ink-primary">{result.title}</p>
                    <span className="mono shrink-0 rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                      {result.score.toFixed(2)}
                    </span>
                  </div>
                  {result.text && result.text !== result.title && (
                    <p className="mt-1 text-sm text-ink-secondary">{truncateText(result.text)}</p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-tertiary">
                    <span>{formatMeetingTitle(result.conversation_title)}</span>
                    <span>{formatDate(result.meeting_date)}</span>
                  </div>
                  <div className="mt-3">
                    <Link
                      href={RESULT_TYPE_LINKS[result.result_type](result)}
                      className="text-sm text-accent hover:text-accent-hover"
                    >
                      {type === "topic" ? "Open topic detail" : type === "entity" ? "Open meeting" : "Open meeting detail"}
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          ))}
        </section>
      )}

      <section className="card p-6">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Topic directory</h2>
            <p className="mt-1 text-sm text-ink-secondary">
              Jump straight into the strongest recurring topics. Emerging one-off topics stay searchable without crowding the main view.
            </p>
          </div>
          <Link href="/topics" className="text-xs text-accent hover:text-accent-hover">
            View all topics
          </Link>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {topicsLoading && <span className="text-sm text-ink-tertiary">Loading topics...</span>}
          {!topicsLoading && featuredTopics.length === 0 && (
            <span className="text-sm text-ink-tertiary">Recurring topics will appear here once Pocket Nori sees the same thread across meetings.</span>
          )}
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
        {!topicsLoading && emergingTopics.length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-ink-secondary">
              Emerging topics ({emergingTopics.length})
            </summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {emergingTopics.map((topic) => (
                <Link
                  key={topic.id}
                  href={`/topics/${topic.id}`}
                  className="rounded border border-soft bg-bg-control px-2 py-1 text-xs text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                >
                  {topic.label}
                </Link>
              ))}
            </div>
          </details>
        )}
      </section>
    </div>
  );
}
