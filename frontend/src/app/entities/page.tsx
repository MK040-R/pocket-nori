"use client";

import { useEffect, useMemo, useState } from "react";

import { getEntities, type EntitySummary } from "@/lib/api";

export default function EntitiesPage() {
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getEntities();
        if (mounted) {
          setEntities(data);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load entities");
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

  const filteredEntities = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return entities;
    }
    return entities.filter((entity) => {
      return (
        entity.name.toLowerCase().includes(normalized) ||
        entity.type.toLowerCase().includes(normalized)
      );
    });
  }, [entities, query]);

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Entities</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Review the people, companies, products, and projects that appear most often in your meetings.
        </p>

        <div className="mt-4">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder="Filter entities"
            className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />
        </div>
      </section>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading entities...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && !error && filteredEntities.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">No entities match your filter.</section>
      )}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {filteredEntities.map((entity) => (
          <article key={`${entity.type}-${entity.name}`} className="card p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-ink-primary">{entity.name}</h2>
              <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                {entity.type}
              </span>
            </div>
            <div className="mt-3 flex gap-3 text-xs text-ink-tertiary">
              <span className="mono">{entity.mentions} mentions</span>
              <span className="mono">{entity.conversation_count} meetings</span>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
