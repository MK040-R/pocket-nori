"use client";

import { useEffect, useMemo, useState } from "react";

import {
  generateDraft,
  isApiErrorStatus,
  type DraftFormat,
  type DraftResponse,
} from "@/lib/api";

type DraftEditorState = {
  subject: string;
  body: string;
};

type CommitmentDraftButtonProps = {
  commitmentId: string;
  label?: string;
  className?: string;
};

function DraftIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.5]">
      <path d="M3.75 12.25h8.5" strokeLinecap="round" />
      <path d="M5 9.25 10.75 3.5a1.06 1.06 0 0 1 1.5 0l.25.25a1.06 1.06 0 0 1 0 1.5L6.75 11H5Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function buildCopyPayload(format: DraftFormat, editor: DraftEditorState): string {
  if (format === "message") {
    return editor.body.trim();
  }
  const subject = editor.subject.trim();
  const body = editor.body.trim();
  return [`Subject: ${subject}`, "", body].join("\n").trim();
}

export function CommitmentDraftButton({
  commitmentId,
  label = "Draft",
  className,
}: CommitmentDraftButtonProps) {
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState<DraftFormat>("email");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Partial<Record<DraftFormat, DraftResponse>>>({});
  const [edits, setEdits] = useState<Partial<Record<DraftFormat, DraftEditorState>>>({});
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const currentDraft = drafts[format] ?? null;
  const currentEditor = useMemo(
    () =>
      edits[format] ?? {
        subject: currentDraft?.subject ?? "",
        body: currentDraft?.body ?? "",
      },
    [currentDraft, edits, format],
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (drafts[format]) {
      return;
    }

    void (async () => {
      setLoading(true);
      setError(null);
      setCopyState("idle");
      try {
        const response = await generateDraft(commitmentId, format);
        setDrafts((current) => ({ ...current, [format]: response }));
        setEdits((current) => ({
          ...current,
          [format]: {
            subject: response.subject,
            body: response.body,
          },
        }));
      } catch (loadError) {
        setError(
          isApiErrorStatus(loadError, [404, 405, 501, 503])
            ? "Draft generation is not available yet for this workspace."
            : loadError instanceof Error
              ? loadError.message
              : "Couldn't generate a draft. Try again.",
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [commitmentId, drafts, format, open]);

  useEffect(() => {
    if (copyState !== "copied") {
      return;
    }

    const timeout = window.setTimeout(() => {
      setCopyState("idle");
    }, 1600);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [copyState]);

  const handleRetry = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await generateDraft(commitmentId, format);
      setDrafts((current) => ({ ...current, [format]: response }));
      setEdits((current) => ({
        ...current,
        [format]: {
          subject: response.subject,
          body: response.body,
        },
      }));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Couldn't generate a draft. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildCopyPayload(format, currentEditor));
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        className={[
          "inline-flex items-center gap-1.5 rounded border border-standard px-2.5 py-1.5 text-xs font-medium text-ink-secondary transition hover:border-emphasis hover:text-ink-primary",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <DraftIcon />
        {label}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#041021]/35 px-4 py-8">
          <div
            className="absolute inset-0"
            onClick={() => {
              setOpen(false);
            }}
            aria-hidden="true"
          />

          <section className="card relative z-10 w-full max-w-3xl overflow-hidden border border-soft">
            <div className="flex items-start justify-between gap-4 border-b border-soft px-6 py-5">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                  Draft Assistant
                </p>
                <h2 className="mt-2 text-xl font-semibold text-ink-primary">Generate a follow-up draft</h2>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                }}
                className="rounded-full border border-standard px-3 py-1.5 text-sm text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
              >
                Close
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <div className="inline-flex rounded-full border border-soft bg-bg-control p-1">
                {(["email", "message"] as DraftFormat[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      setFormat(option);
                      setCopyState("idle");
                    }}
                    className={`rounded-full px-3 py-1.5 text-sm transition ${
                      format === option
                        ? "bg-bg-surface text-ink-primary shadow-sm"
                        : "text-ink-secondary hover:text-ink-primary"
                    }`}
                  >
                    {option === "email" ? "Email" : "Message"}
                  </button>
                ))}
              </div>

              {loading && (
                <div className="space-y-4 animate-pulse">
                  <div className="h-10 rounded-xl bg-bg-control" />
                  <div className="h-40 rounded-2xl bg-bg-control" />
                  <div className="h-10 w-2/5 rounded-xl bg-bg-control" />
                </div>
              )}

              {!loading && error && (
                <div className="rounded-2xl border border-[#f0c6c6] bg-[#fff5f5] p-5">
                  <p className="text-sm text-[#b03a3a]">{error}</p>
                  <button
                    type="button"
                    onClick={() => {
                      void handleRetry();
                    }}
                    className="mt-4 rounded-xl border border-standard px-3 py-2 text-sm font-medium text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
                  >
                    Retry
                  </button>
                </div>
              )}

              {!loading && !error && currentDraft && (
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="space-y-2">
                      <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                        Subject
                      </label>
                      <input
                        value={currentEditor.subject}
                        onChange={(event) => {
                          const nextSubject = event.target.value;
                          setEdits((current) => ({
                            ...current,
                            [format]: {
                              subject: nextSubject,
                              body: currentEditor.body,
                            },
                          }));
                        }}
                        disabled={format === "message"}
                        placeholder={format === "message" ? "Messages skip the subject line" : "Subject"}
                        className="w-full rounded-xl border border-standard bg-bg-control px-3 py-2.5 text-sm text-ink-primary outline-none transition focus:border-emphasis disabled:cursor-not-allowed disabled:text-ink-muted"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                        Suggested recipient
                      </label>
                      <div className="rounded-xl border border-soft bg-bg-surface-raised px-3 py-2.5 text-sm text-ink-secondary">
                        {currentDraft.recipient_suggestion || "No recipient identified"}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                      Body
                    </label>
                    <textarea
                      value={currentEditor.body}
                      onChange={(event) => {
                        const nextBody = event.target.value;
                        setEdits((current) => ({
                          ...current,
                          [format]: {
                            subject: currentEditor.subject,
                            body: nextBody,
                          },
                        }));
                      }}
                      rows={12}
                      className="w-full rounded-2xl border border-standard bg-bg-control px-4 py-3 text-sm leading-7 text-ink-primary outline-none transition focus:border-emphasis"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-soft bg-bg-surface-raised px-6 py-4">
              <p className="text-xs text-ink-tertiary">
                {copyState === "copied"
                  ? "Copied to clipboard."
                  : copyState === "failed"
                    ? "Clipboard access failed."
                    : "Edit the text before copying if you want to personalize it."}
              </p>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                  }}
                  className="rounded-xl border border-standard px-3 py-2 text-sm text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void handleCopy();
                  }}
                  disabled={loading || !!error || !currentDraft}
                  className="rounded-xl border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-medium text-accent transition hover:border-accent disabled:cursor-not-allowed disabled:border-soft disabled:bg-bg-control disabled:text-ink-muted"
                >
                  Copy to clipboard
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
