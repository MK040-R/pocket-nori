"use client";

import { useEffect, useMemo, useState } from "react";

import { getEntities, type EntitySummary } from "@/lib/api";

type EntityType = EntitySummary["type"];
type TypeFilter = "all" | EntityType;
type SortOption = "mentions" | "meetings" | "name";

type ManagedEntity = EntitySummary & {
  entityKey: string;
  displayName: string;
  hasOverride: boolean;
};

const ENTITY_LABEL_OVERRIDES_KEY = "pocket-nori.entity-label-overrides";
const TYPE_FILTERS: Array<{ value: TypeFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "person", label: "People" },
  { value: "company", label: "Companies" },
  { value: "product", label: "Products" },
  { value: "project", label: "Projects" },
];

function getEntityKey(entity: EntitySummary): string {
  return `${entity.type}:${entity.name}`;
}

function readStoredOverrides(): Record<string, string> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(ENTITY_LABEL_OVERRIDES_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, string>;
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, string] => {
        return typeof entry[0] === "string" && typeof entry[1] === "string";
      }),
    );
  } catch {
    return {};
  }
}

function writeStoredOverrides(overrides: Record<string, string>): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(ENTITY_LABEL_OVERRIDES_KEY, JSON.stringify(overrides));
}

export default function EntitiesPage() {
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [nameOverrides, setNameOverrides] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [sortBy, setSortBy] = useState<SortOption>("mentions");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNameOverrides(readStoredOverrides());
  }, []);

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

  const typeCounts = useMemo(() => {
    return entities.reduce<Record<TypeFilter, number>>(
      (counts, entity) => {
        counts.all += 1;
        counts[entity.type] += 1;
        return counts;
      },
      {
        all: 0,
        person: 0,
        company: 0,
        product: 0,
        project: 0,
      },
    );
  }, [entities]);

  const filteredEntities = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return entities
      .map<ManagedEntity>((entity) => {
        const entityKey = getEntityKey(entity);
        const override = nameOverrides[entityKey]?.trim();
        return {
          ...entity,
          entityKey,
          displayName: override || entity.name,
          hasOverride: Boolean(override && override !== entity.name),
        };
      })
      .filter((entity) => {
        if (typeFilter !== "all" && entity.type !== typeFilter) {
          return false;
        }

        if (!normalizedQuery) {
          return true;
        }

        return (
          entity.displayName.toLowerCase().includes(normalizedQuery) ||
          entity.name.toLowerCase().includes(normalizedQuery) ||
          entity.type.toLowerCase().includes(normalizedQuery)
        );
      })
      .sort((left, right) => {
        if (sortBy === "name") {
          return left.displayName.localeCompare(right.displayName);
        }
        if (sortBy === "meetings") {
          if (right.conversation_count !== left.conversation_count) {
            return right.conversation_count - left.conversation_count;
          }
          return right.mentions - left.mentions;
        }
        if (right.mentions !== left.mentions) {
          return right.mentions - left.mentions;
        }
        return right.conversation_count - left.conversation_count;
      });
  }, [entities, nameOverrides, query, sortBy, typeFilter]);

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Manage Entities</h1>
            <p className="mt-2 max-w-2xl text-sm text-ink-secondary">
              Filter and sort the people, companies, products, and projects Pocket Nori sees most often. Label edits change how names display in this browser only.
            </p>
          </div>
          <div className="rounded-2xl border border-soft bg-bg-control px-4 py-3 text-xs text-ink-tertiary">
            <p className="uppercase tracking-[0.08em]">Visible Entities</p>
            <p className="mono mt-2 text-lg text-ink-primary">{filteredEntities.length}</p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder="Search entities"
            className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
          />

          <label className="flex items-center gap-3 rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-secondary">
            <span className="shrink-0">Sort</span>
            <select
              value={sortBy}
              onChange={(event) => {
                setSortBy(event.target.value as SortOption);
              }}
              className="w-full bg-transparent text-ink-primary outline-none"
            >
              <option value="mentions">Most mentions</option>
              <option value="meetings">Most meetings</option>
              <option value="name">Alphabetical</option>
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {TYPE_FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              onClick={() => {
                setTypeFilter(filter.value);
              }}
              className={`rounded-full border px-3 py-1.5 text-sm transition ${
                typeFilter === filter.value
                  ? "border-emphasis bg-accent-subtle text-accent"
                  : "border-standard text-ink-secondary hover:border-emphasis hover:text-ink-primary"
              }`}
            >
              {filter.label} ({typeCounts[filter.value]})
            </button>
          ))}
        </div>
      </section>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading entities...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && !error && filteredEntities.length === 0 && (
        <section className="card p-4 text-sm text-ink-tertiary">
          No entities match the current search or filter.
        </section>
      )}

      <section className="grid gap-3">
        {filteredEntities.map((entity) => {
          const isEditing = editingKey === entity.entityKey;

          return (
            <article key={entity.entityKey} className="card p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-ink-primary">{entity.displayName}</h2>
                    <span className="rounded border border-soft px-2 py-0.5 text-xs text-ink-tertiary">
                      {entity.type}
                    </span>
                    {entity.hasOverride && (
                      <span className="rounded border border-soft bg-bg-control px-2 py-0.5 text-xs text-ink-tertiary">
                        Local label
                      </span>
                    )}
                  </div>

                  {entity.hasOverride && (
                    <p className="mt-1 text-xs text-ink-tertiary">Original name: {entity.name}</p>
                  )}

                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-ink-tertiary">
                    <span className="mono">{entity.mentions} mentions</span>
                    <span className="mono">{entity.conversation_count} meetings</span>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {!isEditing && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingKey(entity.entityKey);
                        setDraftLabel(entity.displayName);
                      }}
                      className="rounded border border-standard px-3 py-1.5 text-sm text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
                    >
                      Edit label
                    </button>
                  )}
                </div>
              </div>

              {isEditing && (
                <div className="mt-4 rounded-2xl border border-soft bg-bg-control p-4">
                  <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                    Display label
                  </label>
                  <input
                    value={draftLabel}
                    onChange={(event) => {
                      setDraftLabel(event.target.value);
                    }}
                    className="mt-2 w-full rounded border border-standard bg-bg-surface-raised px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
                  />
                  <p className="mt-2 text-xs text-ink-tertiary">
                    Saved only in this browser. The shared backend entity record is unchanged.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const nextOverrides = { ...nameOverrides };
                        const trimmed = draftLabel.trim();
                        if (!trimmed || trimmed === entity.name) {
                          delete nextOverrides[entity.entityKey];
                        } else {
                          nextOverrides[entity.entityKey] = trimmed;
                        }
                        setNameOverrides(nextOverrides);
                        writeStoredOverrides(nextOverrides);
                        setEditingKey(null);
                        setDraftLabel("");
                      }}
                      className="rounded border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-medium text-accent"
                    >
                      Save label
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const nextOverrides = { ...nameOverrides };
                        delete nextOverrides[entity.entityKey];
                        setNameOverrides(nextOverrides);
                        writeStoredOverrides(nextOverrides);
                        setEditingKey(null);
                        setDraftLabel("");
                      }}
                      className="rounded border border-standard px-3 py-2 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                    >
                      Reset to source
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingKey(null);
                        setDraftLabel("");
                      }}
                      className="rounded border border-standard px-3 py-2 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}
