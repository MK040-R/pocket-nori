"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  createCommitment,
  getCommitments,
  resolveCommitment,
  type ActionType,
  type Commitment,
} from "@/lib/api";
import { formatDueDate, formatMeetingTitle } from "@/lib/presentation";

type ActionFormState = {
  text: string;
  actionType: ActionType;
  owner: string;
  dueDate: string;
};

const EMPTY_FORM: ActionFormState = {
  text: "",
  actionType: "commitment",
  owner: "",
  dueDate: "",
};

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.6]">
      <path d="M3.5 8.5 6.5 11.5 12.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function OpenIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.6]">
      <path d="M6 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.5 5.5 4 12" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 9.5V12H4V4h2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ActionCard({
  item,
  resolving,
  onResolve,
}: {
  item: Commitment;
  resolving: boolean;
  onResolve: () => Promise<void>;
}) {
  const hasMeeting = item.conversation_id.trim() !== "";
  const sourceLabel = hasMeeting ? formatMeetingTitle(item.conversation_title) : "Manual action";

  return (
    <article className="rounded border border-soft p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-primary">{item.text}</p>
          <p className="mt-1 text-xs text-ink-tertiary">
            {item.owner || "Unassigned"} · due {formatDueDate(item.due_date)} · {sourceLabel}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={resolving}
            onClick={() => {
              void onResolve();
            }}
            aria-label="Mark action done"
            className="rounded border border-emphasis bg-accent-subtle p-2 text-accent transition hover:border-accent disabled:cursor-not-allowed disabled:border-soft disabled:bg-bg-control disabled:text-ink-muted"
          >
            <CheckIcon />
          </button>

          {hasMeeting ? (
            <Link
              href={`/meetings/${item.conversation_id}`}
              aria-label="Open source meeting"
              className="rounded border border-standard p-2 text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
            >
              <OpenIcon />
            </Link>
          ) : (
            <span
              aria-hidden="true"
              className="rounded border border-soft p-2 text-ink-muted"
              title="No linked meeting"
            >
              <OpenIcon />
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

export default function ActionsPage() {
  const [activeTab, setActiveTab] = useState<ActionType>("commitment");
  const [actions, setActions] = useState<Record<ActionType, Commitment[]>>({
    commitment: [],
    follow_up: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [form, setForm] = useState<ActionFormState>(EMPTY_FORM);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [commitmentsData, followUpsData] = await Promise.all([
          getCommitments("open", { actionType: "commitment" }),
          getCommitments("open", { actionType: "follow_up" }),
        ]);
        if (mounted) {
          setActions({
            commitment: commitmentsData,
            follow_up: followUpsData,
          });
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load actions");
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

  const activeItems = actions[activeTab];

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Actions</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Track what you owe and what you are waiting on. Resolved items archive automatically once marked done.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setShowForm((current) => !current);
              setForm((current) => ({ ...current, actionType: activeTab }));
            }}
            className="rounded border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-medium text-accent"
          >
            {showForm ? "Close form" : "Add manually"}
          </button>
        </div>

        <div className="mt-4 inline-flex rounded-full border border-soft bg-bg-control p-1">
          <button
            type="button"
            onClick={() => {
              setActiveTab("commitment");
              setForm((current) => ({ ...current, actionType: "commitment" }));
            }}
            className={`rounded-full px-3 py-1.5 text-sm transition ${
              activeTab === "commitment"
                ? "bg-bg-surface-raised text-ink-primary"
                : "text-ink-secondary hover:text-ink-primary"
            }`}
          >
            Commitments ({actions.commitment.length})
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab("follow_up");
              setForm((current) => ({ ...current, actionType: "follow_up" }));
            }}
            className={`rounded-full px-3 py-1.5 text-sm transition ${
              activeTab === "follow_up"
                ? "bg-bg-surface-raised text-ink-primary"
                : "text-ink-secondary hover:text-ink-primary"
            }`}
          >
            Follow-ups ({actions.follow_up.length})
          </button>
        </div>

        {showForm && (
          <form
            className="mt-4 space-y-3 rounded border border-soft bg-bg-surface-raised p-4"
            onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              setError(null);
              try {
                const created = await createCommitment({
                  text: form.text.trim(),
                  action_type: form.actionType,
                  owner: form.owner.trim(),
                  due_date: form.dueDate ? `${form.dueDate}T00:00:00+00:00` : null,
                });
                setActions((current) => ({
                  ...current,
                  [created.action_type]: [created, ...current[created.action_type]],
                }));
                setActiveTab(created.action_type);
                setForm({
                  ...EMPTY_FORM,
                  actionType: created.action_type,
                });
                setShowForm(false);
              } catch (saveError) {
                setError(saveError instanceof Error ? saveError.message : "Failed to create action");
              } finally {
                setSaving(false);
              }
            }}
          >
            <div className="space-y-2">
              <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                Action
              </label>
              <textarea
                required
                value={form.text}
                onChange={(event) => {
                  setForm((current) => ({ ...current, text: event.target.value }));
                }}
                rows={3}
                placeholder="Add the action you want to track"
                className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
              />
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                  Type
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setForm((current) => ({ ...current, actionType: "commitment" }));
                    }}
                    className={`rounded border px-3 py-2 text-sm transition ${
                      form.actionType === "commitment"
                        ? "border-emphasis bg-accent-subtle text-accent"
                        : "border-standard text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                    }`}
                  >
                    Commitment
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setForm((current) => ({ ...current, actionType: "follow_up" }));
                    }}
                    className={`rounded border px-3 py-2 text-sm transition ${
                      form.actionType === "follow_up"
                        ? "border-emphasis bg-accent-subtle text-accent"
                        : "border-standard text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                    }`}
                  >
                    Follow-up
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                  Responsible person
                </label>
                <input
                  value={form.owner}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, owner: event.target.value }));
                  }}
                  placeholder="Who owns this action?"
                  className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                  Due date
                </label>
                <input
                  type="date"
                  value={form.dueDate}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, dueDate: event.target.value }));
                  }}
                  className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-medium text-accent disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
              >
                {saving ? "Saving..." : "Save action"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setForm({ ...EMPTY_FORM, actionType: activeTab });
                  setShowForm(false);
                }}
                className="rounded border border-standard px-3 py-2 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>

      {loading && <section className="card p-4 text-sm text-ink-secondary">Loading actions...</section>}

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {!loading && !error && (
        <section className="card p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">
                {activeTab === "commitment" ? "Commitments" : "Follow-ups"}
              </h2>
              <p className="mt-1 text-xs text-ink-tertiary">
                {activeItems.length} open {activeItems.length === 1 ? "item" : "items"}
              </p>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {activeItems.length === 0 && (
              <p className="text-sm text-ink-tertiary">
                {activeTab === "commitment"
                  ? "No open commitments."
                  : "No open follow-ups."}
              </p>
            )}

            {activeItems.map((item) => (
              <ActionCard
                key={item.id}
                item={item}
                resolving={resolvingId === item.id}
                onResolve={async () => {
                  setResolvingId(item.id);
                  setError(null);
                  try {
                    await resolveCommitment(item.id);
                    setActions((current) => ({
                      ...current,
                      [item.action_type]: current[item.action_type].filter(
                        (candidate) => candidate.id !== item.id,
                      ),
                    }));
                  } catch (resolveError) {
                    setError(
                      resolveError instanceof Error
                        ? resolveError.message
                        : "Failed to resolve action",
                    );
                  } finally {
                    setResolvingId(null);
                  }
                }}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
