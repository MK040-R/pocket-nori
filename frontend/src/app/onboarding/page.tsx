"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getAvailableRecordings,
  getAllImportStatus,
  startImport,
  type ImportJob,
  type ImportJobStatus,
  type RecordingItem,
} from "@/lib/api";

function formatBytes(value: number | null): string {
  if (value === null) {
    return "Unknown size";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return date.toLocaleString();
}

function parseDateBoundary(value: string, boundary: "start" | "end"): number | null {
  if (!value) {
    return null;
  }

  const suffix = boundary === "start" ? "T00:00:00.000" : "T23:59:59.999";
  const timestamp = Date.parse(`${value}${suffix}`);
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return timestamp;
}

function chunkFileIds(fileIds: string[], chunkSize: number): string[][] {
  const chunks: string[][] = [];
  for (let index = 0; index < fileIds.length; index += chunkSize) {
    chunks.push(fileIds.slice(index, index + chunkSize));
  }
  return chunks;
}

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
const MAX_CONSECUTIVE_POLL_ERRORS = 5;
const MAX_IMPORT_BATCH_SIZE = 20;

export default function OnboardingPage() {
  const [recordings, setRecordings] = useState<RecordingItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [jobStatuses, setJobStatuses] = useState<Record<string, ImportJobStatus>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRecordings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const items = await getAvailableRecordings();
      setRecordings(items);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load recordings");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecordings();
  }, [loadRecordings]);

  useEffect(() => {
    setSelectedIds((current) => {
      const selectableIds = new Set(
        recordings.filter((recording) => !recording.already_imported).map((recording) => recording.file_id),
      );

      let changed = false;
      for (const id of current) {
        if (!selectableIds.has(id)) {
          changed = true;
          break;
        }
      }

      if (!changed) {
        return current;
      }

      return new Set(Array.from(current).filter((id) => selectableIds.has(id)));
    });
  }, [recordings]);

  useEffect(() => {
    if (jobs.length === 0) {
      return;
    }

    let isCancelled = false;
    const pollStartedAt = Date.now();
    let consecutivePollErrors = 0;

    const poll = async () => {
      if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
        if (!isCancelled) {
          setError("Import status polling timed out after 10 minutes. Refresh to check current state.");
        }
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        return;
      }

      try {
        const aggregate = await getAllImportStatus(jobs.map((job) => job.job_id));
        consecutivePollErrors = 0;

        if (isCancelled) {
          return;
        }

        const nextStatuses: Record<string, ImportJobStatus> = {};
        aggregate.jobs.forEach((status) => {
          nextStatuses[status.job_id] = status;
        });

        setJobStatuses(nextStatuses);

        const allTerminal = aggregate.jobs.every(
          (status) => status.status === "success" || status.status === "failure",
        );

        if (allTerminal && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
          void loadRecordings();
        }
      } catch (pollError) {
        consecutivePollErrors += 1;
        if (!isCancelled) {
          setError(pollError instanceof Error ? pollError.message : "Failed to poll import status");
        }
        if (consecutivePollErrors >= MAX_CONSECUTIVE_POLL_ERRORS && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    void poll();

    intervalRef.current = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);

    return () => {
      isCancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobs, loadRecordings]);

  const summary = useMemo(() => {
    const total = jobs.length;
    if (total === 0) {
      return null;
    }

    let pending = 0;
    let progress = 0;
    let success = 0;
    let failure = 0;

    jobs.forEach((job) => {
      const state = jobStatuses[job.job_id]?.status ?? "pending";
      if (state === "pending") {
        pending += 1;
      } else if (state === "progress" || state === "processing") {
        progress += 1;
      } else if (state === "success") {
        success += 1;
      } else if (state === "failure") {
        failure += 1;
      }
    });

    return {
      total,
      pending,
      progress,
      success,
      failure,
    };
  }, [jobs, jobStatuses]);

  const queueImports = useCallback(async (fileIds: string[]) => {
    const deduplicatedIds = Array.from(new Set(fileIds));
    if (deduplicatedIds.length === 0) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const batches = chunkFileIds(deduplicatedIds, MAX_IMPORT_BATCH_SIZE);
      const allJobs: ImportJob[] = [];

      for (const batch of batches) {
        const response = await startImport(batch);
        allJobs.push(...response.jobs);
      }

      setJobs(allJobs);

      const initialStates: Record<string, ImportJobStatus> = {};
      allJobs.forEach((job) => {
        initialStates[job.job_id] = {
          job_id: job.job_id,
          status: "pending",
        };
      });
      setJobStatuses(initialStates);
      setSelectedIds(new Set());
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to queue import");
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const hasInvalidDateRange = fromDate !== "" && toDate !== "" && fromDate > toDate;
  const hasDateFilter = fromDate !== "" || toDate !== "";

  const filteredRecordings = useMemo(() => {
    if (hasInvalidDateRange) {
      return [];
    }

    const fromBoundary = parseDateBoundary(fromDate, "start");
    const toBoundary = parseDateBoundary(toDate, "end");

    return recordings.filter((recording) => {
      const createdAt = Date.parse(recording.created_time);
      if (Number.isNaN(createdAt)) {
        return true;
      }
      if (fromBoundary !== null && createdAt < fromBoundary) {
        return false;
      }
      if (toBoundary !== null && createdAt > toBoundary) {
        return false;
      }
      return true;
    });
  }, [fromDate, hasInvalidDateRange, recordings, toDate]);

  const selectableIds = useMemo(
    () =>
      recordings.filter((recording) => !recording.already_imported).map((recording) => recording.file_id),
    [recordings],
  );

  const visibleSelectableIds = useMemo(
    () =>
      filteredRecordings
        .filter((recording) => !recording.already_imported)
        .map((recording) => recording.file_id),
    [filteredRecordings],
  );

  const selectableCount = selectableIds.length;
  const visibleSelectableCount = visibleSelectableIds.length;
  const allVisibleSelected =
    visibleSelectableIds.length > 0 && visibleSelectableIds.every((id) => selectedIds.has(id));

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Onboarding</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Import past Google Meet notes and transcripts in batches so Pocket Nori can build your meeting history.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            onClick={() => {
              void loadRecordings();
            }}
            className="rounded border border-standard px-3 py-1.5 text-ink-secondary hover:border-emphasis hover:text-ink-primary"
          >
            Refresh recordings
          </button>
          {lastUpdated && <span className="text-ink-tertiary">Last updated: {lastUpdated}</span>}
        </div>
      </section>

      {error && (
        <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
          {error}
        </section>
      )}

      {summary && (
        <section className="card p-4">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <span className="font-semibold text-ink-primary">Import progress</span>
            <span className="mono text-ink-secondary">Total {summary.total}</span>
            <span className="mono text-ink-secondary">Pending {summary.pending}</span>
            <span className="mono text-ink-secondary">Running {summary.progress}</span>
            <span className="mono text-ink-secondary">Success {summary.success}</span>
            <span className="mono text-ink-secondary">Failed {summary.failure}</span>
          </div>
        </section>
      )}

      <section className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Available recordings</h2>
          <div className="text-sm text-ink-tertiary">
            {isLoading
              ? "Loading..."
              : hasDateFilter
                ? `${filteredRecordings.length} shown of ${recordings.length} (${visibleSelectableCount} selectable)`
                : `${recordings.length} found (${selectableCount} selectable)`}
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs uppercase tracking-[0.06em] text-ink-tertiary">
            From
            <input
              type="date"
              value={fromDate}
              onChange={(event) => {
                setFromDate(event.target.value);
              }}
              className="rounded border border-standard bg-bg-control px-3 py-1.5 text-sm text-ink-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs uppercase tracking-[0.06em] text-ink-tertiary">
            To
            <input
              type="date"
              value={toDate}
              onChange={(event) => {
                setToDate(event.target.value);
              }}
              className="rounded border border-standard bg-bg-control px-3 py-1.5 text-sm text-ink-primary"
            />
          </label>
          <button
            type="button"
            disabled={!hasDateFilter || isSubmitting}
            onClick={() => {
              setFromDate("");
              setToDate("");
            }}
            className="rounded border border-standard px-3 py-1.5 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            Clear dates
          </button>
        </div>

        {hasInvalidDateRange && (
          <p className="mb-4 text-sm text-accent">From date must be earlier than or equal to To date.</p>
        )}

        <div className="mb-4 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={visibleSelectableIds.length === 0 || hasInvalidDateRange || isSubmitting}
            onClick={() => {
              setSelectedIds((current) => {
                const next = new Set(current);
                if (allVisibleSelected) {
                  visibleSelectableIds.forEach((id) => {
                    next.delete(id);
                  });
                } else {
                  visibleSelectableIds.forEach((id) => {
                    next.add(id);
                  });
                }
                return next;
              });
            }}
            className="rounded border border-standard px-4 py-2 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            {allVisibleSelected
              ? `Deselect visible (${visibleSelectableCount})`
              : `Select visible (${visibleSelectableCount})`}
          </button>

          <button
            type="button"
            disabled={selectedIds.size === 0 || isSubmitting}
            onClick={() => {
              setSelectedIds(new Set());
            }}
            className="rounded border border-standard px-4 py-2 text-sm text-ink-secondary hover:border-emphasis hover:text-ink-primary disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            Clear selection
          </button>

          <button
            type="button"
            disabled={selectableIds.length === 0 || hasInvalidDateRange || isSubmitting}
            onClick={() => {
              void queueImports(selectableIds);
            }}
            className="rounded border border-standard px-4 py-2 text-sm font-medium text-ink-secondary hover:border-emphasis hover:text-ink-primary disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            {isSubmitting ? "Queueing..." : `Import all selectable (${selectableCount})`}
          </button>

          <button
            type="button"
            disabled={selectedIds.size === 0 || isSubmitting}
            onClick={() => {
              void queueImports(Array.from(selectedIds));
            }}
            className="rounded border border-emphasis bg-accent-subtle px-4 py-2 text-sm font-medium text-accent disabled:cursor-not-allowed disabled:border-soft disabled:text-ink-muted"
          >
            {isSubmitting ? "Queueing..." : `Import selected (${selectedIds.size})`}
          </button>
        </div>

        {recordings.length === 0 && !isLoading && (
          <p className="text-sm text-ink-tertiary">No recordings were returned for the current lookback window.</p>
        )}
        {recordings.length > 0 && filteredRecordings.length === 0 && !isLoading && !hasInvalidDateRange && (
          <p className="text-sm text-ink-tertiary">No recordings match the selected date range.</p>
        )}

        <div className="space-y-3">
          {filteredRecordings.map((recording) => {
            const job = jobs.find((candidate) => candidate.file_id === recording.file_id);
            const status = job ? jobStatuses[job.job_id]?.status : null;

            return (
              <label
                key={recording.file_id}
                className={`block rounded-md border px-4 py-3 ${
                  recording.already_imported
                    ? "border-soft bg-bg-control"
                    : "border-standard bg-bg-surface-raised hover:border-emphasis"
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    disabled={recording.already_imported}
                    checked={selectedIds.has(recording.file_id)}
                    onChange={(event) => {
                      setSelectedIds((current) => {
                        const next = new Set(current);
                        if (event.target.checked) {
                          next.add(recording.file_id);
                        } else {
                          next.delete(recording.file_id);
                        }
                        return next;
                      });
                    }}
                  />

                  <div className="flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium text-ink-primary">{recording.name}</p>
                      <span className="mono text-xs text-ink-tertiary">{formatBytes(recording.size_bytes)}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink-tertiary">Created {formatDate(recording.created_time)}</p>
                    <p className="mt-1 text-xs text-ink-muted">{recording.mime_type}</p>

                    {recording.already_imported && (
                      <p className="mt-2 inline-flex rounded border border-soft px-2 py-1 text-xs text-ink-secondary">
                        Already imported
                      </p>
                    )}

                    {!recording.already_imported && status && (
                      <p className="mt-2 inline-flex rounded border border-soft px-2 py-1 text-xs text-ink-secondary">
                        Job status: {status}
                      </p>
                    )}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </section>
    </div>
  );
}
