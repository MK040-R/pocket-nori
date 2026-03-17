"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  BASE_URL,
  deleteChatSession,
  getChatMessages,
  getChatSessions,
  isApiErrorStatus,
  type ChatCitation,
  type ChatMessage,
  type ChatSessionSummary,
} from "@/lib/api";
import { formatMeetingTitle, formatRelativeTime } from "@/lib/presentation";

const EXAMPLE_PROMPTS = [
  "What decisions did we make about the Q2 launch?",
  "Which client concerns came up most often this month?",
  "Summarize open commitments from recent team meetings.",
  "What changed between the last two planning reviews?",
];

type MobilePanel = "sessions" | "chat";

type ParsedSseEvent = {
  event: string;
  data: string;
};

function parseSseEventBlock(block: string): ParsedSseEvent | null {
  const lines = block
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean);

  if (lines.length === 0) {
    return null;
  }

  let event = "message";
  const dataLines: string[] = [];

  lines.forEach((line) => {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      return;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  });

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: dataLines.join("\n"),
  };
}

function buildOptimisticSession(message: string, sessionId: string): ChatSessionSummary {
  const now = new Date().toISOString();
  return {
    id: sessionId,
    title: message.trim().slice(0, 52) || "New chat",
    created_at: now,
    updated_at: now,
    last_message_preview: message.trim().slice(0, 100),
  };
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 text-ink-tertiary">
      <span className="h-2 w-2 animate-pulse rounded-full bg-current [animation-delay:-0.2s]" />
      <span className="h-2 w-2 animate-pulse rounded-full bg-current [animation-delay:-0.1s]" />
      <span className="h-2 w-2 animate-pulse rounded-full bg-current" />
    </div>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.5]">
      <path d="M3.75 4.25h8.5" strokeLinecap="round" />
      <path d="M6 2.75h4" strokeLinecap="round" />
      <path d="m5 4.25.5 8h5l.5-8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.4]">
      <path d="m8 1.75 1.2 3.05L12.25 6 9.2 7.2 8 10.25 6.8 7.2 3.75 6 6.8 4.8Z" strokeLinejoin="round" />
      <path d="m12 10.25.55 1.45L14 12.25l-1.45.55L12 14.25l-.55-1.45L10 12.25l1.45-.55Z" strokeLinejoin="round" />
    </svg>
  );
}

function formatCitationDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function ChatMessageBubble({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <article
        className={`max-w-3xl rounded-[24px] border px-4 py-3 shadow-sm ${
          isUser
            ? "border-emphasis bg-accent text-[#041021]"
            : "border-soft bg-white text-ink-primary"
        }`}
      >
        {!message.content && isStreaming && !isUser ? (
          <TypingIndicator />
        ) : (
          <p
            className={`whitespace-pre-wrap text-sm leading-7 ${
              isUser ? "text-[#041021]" : "text-ink-secondary"
            }`}
          >
            {message.content}
          </p>
        )}

        {!isUser && message.citations.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.citations.map((citation) => (
              <Link
                key={`${message.id}-${citation.result_id}-${citation.conversation_id}`}
                href={`/meetings/${citation.conversation_id}`}
                className="inline-flex items-center gap-2 rounded-full border border-emphasis bg-accent-subtle px-3 py-1.5 text-xs font-medium text-accent transition hover:border-accent"
              >
                <span>{formatMeetingTitle(citation.conversation_title || citation.title)}</span>
                <span className="text-[11px] text-ink-tertiary">{formatCitationDate(citation.meeting_date)}</span>
              </Link>
            ))}
          </div>
        )}
      </article>
    </div>
  );
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("sessions");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [featureUnavailable, setFeatureUnavailable] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [composerError, setComposerError] = useState<string | null>(null);

  const streamAbortRef = useRef<AbortController | null>(null);
  const skipNextMessageLoadRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? null,
    [selectedSessionId, sessions],
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    let mounted = true;

    const loadSessions = async () => {
      setLoadingSessions(true);
      setPageError(null);
      try {
        const nextSessions = await getChatSessions();
        if (!mounted) {
          return;
        }

        setFeatureUnavailable(false);
        setSessions(nextSessions);
        setSelectedSessionId((current) => {
          if (current && nextSessions.some((session) => session.id === current)) {
            return current;
          }
          return nextSessions[0]?.id ?? null;
        });
        if (nextSessions[0]) {
          setMobilePanel("chat");
        }
      } catch (loadError) {
        if (!mounted) {
          return;
        }

        if (isApiErrorStatus(loadError, [404, 405, 501, 503])) {
          setFeatureUnavailable(true);
          setSessions([]);
          setSelectedSessionId(null);
          setMessages([]);
          return;
        }

        setPageError(loadError instanceof Error ? loadError.message : "Failed to load chat sessions");
      } finally {
        if (mounted) {
          setLoadingSessions(false);
        }
      }
    };

    void loadSessions();

    return () => {
      mounted = false;
      streamAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!selectedSessionId) {
      if (!sending) {
        setMessages([]);
      }
      return;
    }

    if (skipNextMessageLoadRef.current === selectedSessionId) {
      skipNextMessageLoadRef.current = null;
      return;
    }

    let mounted = true;

    const loadMessages = async () => {
      setLoadingMessages(true);
      setComposerError(null);
      try {
        const nextMessages = await getChatMessages(selectedSessionId);
        if (mounted) {
          setFeatureUnavailable(false);
          setMessages(nextMessages);
        }
      } catch (loadError) {
        if (!mounted) {
          return;
        }

        if (isApiErrorStatus(loadError, [404, 405, 501, 503])) {
          setFeatureUnavailable(true);
          return;
        }

        setComposerError(
          loadError instanceof Error ? loadError.message : "Failed to load this conversation",
        );
      } finally {
        if (mounted) {
          setLoadingMessages(false);
        }
      }
    };

    void loadMessages();

    return () => {
      mounted = false;
    };
  }, [selectedSessionId, sending]);

  const refreshSessions = async (preferredSessionId?: string | null) => {
    try {
      const nextSessions = await getChatSessions();
      setSessions(nextSessions);
      setSelectedSessionId((current) => {
        const target = preferredSessionId ?? current;
        if (target && nextSessions.some((session) => session.id === target)) {
          return target;
        }
        return nextSessions[0]?.id ?? null;
      });
    } catch {
      // Keep the optimistic state if the refresh fails.
    }
  };

  const handleDeleteSession = async (session: ChatSessionSummary) => {
    const confirmed = window.confirm(`Delete "${session.title}"? This will remove the full chat history.`);
    if (!confirmed) {
      return;
    }

    setPageError(null);
    try {
      await deleteChatSession(session.id);
      const remainingSessions = sessions.filter((item) => item.id !== session.id);
      setSessions(remainingSessions);

      if (selectedSessionId === session.id) {
        setSelectedSessionId(remainingSessions[0]?.id ?? null);
        setMessages([]);
      }

      if (remainingSessions.length === 0) {
        setMobilePanel("sessions");
      }
    } catch (deleteError) {
      setPageError(deleteError instanceof Error ? deleteError.message : "Failed to delete the chat");
    }
  };

  const handleSubmit = async (rawPrompt?: string) => {
    const messageText = (rawPrompt ?? draft).trim();
    if (!messageText || sending || featureUnavailable) {
      return;
    }

    streamAbortRef.current?.abort();

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: messageText,
      citations: [],
      created_at: new Date().toISOString(),
    };
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      citations: [],
      created_at: new Date().toISOString(),
    };

    const requestedSessionId = selectedSessionId;

    setComposerError(null);
    setDraft("");
    setMobilePanel("chat");
    setMessages((current) => [...current, userMessage, assistantPlaceholder]);
    setSending(true);

    const controller = new AbortController();
    streamAbortRef.current = controller;

    try {
      const response = await fetch(`${BASE_URL}/chat`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          message: messageText,
          ...(requestedSessionId ? { session_id: requestedSessionId } : {}),
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        if ([404, 405, 501, 503].includes(response.status)) {
          setFeatureUnavailable(true);
          throw new Error("Chat streaming is not available yet for this workspace.");
        }

        let detail = `Request failed (${response.status})`;
        try {
          const payload = (await response.json()) as { detail?: string };
          if (payload.detail) {
            detail = payload.detail;
          }
        } catch {
          // Ignore malformed error payloads.
        }
        throw new Error(detail);
      }

      const decoder = new TextDecoder();
      const reader = response.body.getReader();
      let buffer = "";
      let resolvedSessionId = requestedSessionId;

      const handleParsedEvent = (payload: ParsedSseEvent) => {
        if (payload.event === "session") {
          try {
            const data = JSON.parse(payload.data) as { session_id?: string };
            const nextSessionId = data.session_id;
            if (!nextSessionId) {
              return;
            }

            resolvedSessionId = nextSessionId;
            skipNextMessageLoadRef.current = nextSessionId;
            setSelectedSessionId(nextSessionId);
            setSessions((current) => {
              if (current.some((session) => session.id === nextSessionId)) {
                return current;
              }
              return [buildOptimisticSession(messageText, nextSessionId), ...current];
            });
          } catch {
            // Ignore malformed session events.
          }
          return;
        }

        if (payload.event === "delta") {
          try {
            const data = JSON.parse(payload.data) as { content?: string };
            const nextChunk = data.content ?? "";
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${nextChunk}` }
                  : message,
              ),
            );
          } catch {
            // Ignore malformed delta payloads.
          }
          return;
        }

        if (payload.event === "citations") {
          try {
            const data = JSON.parse(payload.data) as ChatCitation[];
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId ? { ...message, citations: data } : message,
              ),
            );
          } catch {
            // Ignore malformed citation payloads.
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        chunks.forEach((chunk) => {
          const parsed = parseSseEventBlock(chunk);
          if (parsed) {
            handleParsedEvent(parsed);
          }
        });
      }

      if (buffer.trim()) {
        const parsed = parseSseEventBlock(buffer);
        if (parsed) {
          handleParsedEvent(parsed);
        }
      }

      await refreshSessions(resolvedSessionId);
    } catch (sendError) {
      if (sendError instanceof Error && sendError.name === "AbortError") {
        return;
      }

      setMessages((current) => current.filter((message) => message.id !== assistantMessageId));
      setComposerError(
        sendError instanceof Error ? sendError.message : "Failed to send your message",
      );
    } finally {
      setSending(false);
      streamAbortRef.current = null;
    }
  };

  const chatTitle = selectedSession?.title ?? "New chat";

  return (
    <div className="space-y-6">
      <section className="card p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
              Intelligence Action Layer
            </p>
            <h1 className="mt-2 text-2xl font-semibold text-ink-primary">Chat</h1>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-ink-secondary">
              Ask across your meeting history, follow a thread over multiple turns, and jump from answers straight back into the source conversation.
            </p>
          </div>

          <button
            type="button"
            disabled={sending || featureUnavailable}
            onClick={() => {
              setSelectedSessionId(null);
              setMessages([]);
              setComposerError(null);
              setMobilePanel("chat");
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-emphasis bg-accent-subtle px-4 py-2.5 text-sm font-medium text-accent transition hover:border-accent disabled:cursor-not-allowed disabled:border-soft disabled:bg-bg-control disabled:text-ink-muted"
          >
            <SparkIcon />
            New chat
          </button>
        </div>
      </section>

      <div className="inline-flex rounded-full border border-soft bg-bg-control p-1 lg:hidden">
        <button
          type="button"
          onClick={() => {
            setMobilePanel("sessions");
          }}
          className={`rounded-full px-3 py-1.5 text-sm transition ${
            mobilePanel === "sessions"
              ? "bg-bg-surface text-ink-primary shadow-sm"
              : "text-ink-secondary"
          }`}
        >
          Sessions
        </button>
        <button
          type="button"
          onClick={() => {
            setMobilePanel("chat");
          }}
          className={`rounded-full px-3 py-1.5 text-sm transition ${
            mobilePanel === "chat"
              ? "bg-bg-surface text-ink-primary shadow-sm"
              : "text-ink-secondary"
          }`}
        >
          Active chat
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className={`${mobilePanel === "sessions" ? "block" : "hidden"} lg:block`}>
          <section className="card overflow-hidden p-0">
            <div className="border-b border-soft px-5 py-4">
              <h2 className="text-lg font-semibold text-ink-primary">Sessions</h2>
              <p className="mt-1 text-sm text-ink-secondary">
                Persistent Q&A threads over your meetings.
              </p>
            </div>

            <div className="max-h-[70vh] overflow-y-auto p-3">
              {loadingSessions && (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div key={index} className="animate-pulse rounded-2xl border border-soft p-4">
                      <div className="h-4 w-3/5 rounded bg-bg-control" />
                      <div className="mt-3 h-3 w-full rounded bg-bg-control" />
                      <div className="mt-2 h-3 w-2/5 rounded bg-bg-control" />
                    </div>
                  ))}
                </div>
              )}

              {!loadingSessions && featureUnavailable && (
                <div className="rounded-2xl border border-dashed border-soft bg-bg-surface-raised p-4">
                  <p className="text-sm font-medium text-ink-primary">Chat backend not live yet</p>
                  <p className="mt-2 text-sm leading-7 text-ink-secondary">
                    The UI is ready. Once `/chat` is deployed, saved sessions and streaming answers will appear here automatically.
                  </p>
                </div>
              )}

              {!loadingSessions && !featureUnavailable && sessions.length === 0 && (
                <div className="rounded-2xl border border-dashed border-soft bg-bg-surface-raised p-4">
                  <p className="text-sm font-medium text-ink-primary">No chat history yet</p>
                  <p className="mt-2 text-sm leading-7 text-ink-secondary">
                    Start a new thread and ask about decisions, commitments, or recurring themes across your meetings.
                  </p>
                </div>
              )}

              {!loadingSessions && sessions.length > 0 && (
                <div className="space-y-2">
                  {sessions.map((session) => {
                    const isActive = session.id === selectedSessionId;
                    return (
                      <article
                        key={session.id}
                        className={`w-full rounded-2xl border p-4 text-left transition ${
                          isActive
                            ? "border-emphasis bg-accent-subtle"
                            : "border-soft bg-white hover:border-emphasis"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedSessionId(session.id);
                              setComposerError(null);
                              setMobilePanel("chat");
                            }}
                            className="min-w-0 flex-1 text-left"
                          >
                            <p className="truncate text-sm font-semibold text-ink-primary">{session.title}</p>
                            <p className="mt-2 truncate text-xs text-ink-secondary">
                              {session.last_message_preview || "No messages yet"}
                            </p>
                            <p className="mt-3 text-[11px] uppercase tracking-[0.12em] text-ink-tertiary">
                              {formatRelativeTime(session.updated_at)}
                            </p>
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              void handleDeleteSession(session);
                            }}
                            className="rounded-full border border-transparent p-2 text-ink-tertiary transition hover:border-standard hover:text-ink-primary"
                            aria-label={`Delete ${session.title}`}
                          >
                            <TrashIcon />
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </aside>

        <section className={`${mobilePanel === "chat" ? "block" : "hidden"} lg:block`}>
          <article className="card flex min-h-[70vh] flex-col overflow-hidden p-0">
            <div className="border-b border-soft px-6 py-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-ink-tertiary">
                    Active thread
                  </p>
                  <h2 className="mt-2 text-xl font-semibold text-ink-primary">{chatTitle}</h2>
                </div>
                {selectedSession && (
                  <p className="text-xs text-ink-tertiary">
                    Updated {formatRelativeTime(selectedSession.updated_at)}
                  </p>
                )}
              </div>

              {pageError && (
                <div className="mt-4 rounded-2xl border border-[#f0c6c6] bg-[#fff5f5] px-4 py-3 text-sm text-[#b03a3a]">
                  {pageError}
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(0,194,122,0.08),_transparent_26%),linear-gradient(180deg,_rgba(255,255,255,0.88),_rgba(247,250,255,0.88))] px-5 py-5">
              {loadingMessages ? (
                <div className="space-y-4">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <div key={index} className={`flex ${index % 2 === 0 ? "justify-start" : "justify-end"}`}>
                      <div className="h-24 w-full max-w-2xl animate-pulse rounded-[24px] bg-bg-control" />
                    </div>
                  ))}
                </div>
              ) : messages.length > 0 ? (
                <div className="space-y-4">
                  {messages.map((message, index) => (
                    <ChatMessageBubble
                      key={message.id}
                      message={message}
                      isStreaming={sending && index === messages.length - 1}
                    />
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              ) : (
                <div className="mx-auto flex max-w-3xl flex-col items-center justify-center rounded-[28px] border border-dashed border-soft bg-white/80 px-8 py-12 text-center shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-subtle text-accent">
                    <SparkIcon />
                  </div>
                  <h3 className="mt-5 text-xl font-semibold text-ink-primary">Ask anything about your meetings</h3>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-ink-secondary">
                    Pull decisions, compare meeting threads, or trace who committed to what. Citations will link straight back to the meeting that supported the answer.
                  </p>

                  <div className="mt-6 flex flex-wrap justify-center gap-2">
                    {EXAMPLE_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        disabled={featureUnavailable}
                        onClick={() => {
                          setDraft(prompt);
                          void handleSubmit(prompt);
                        }}
                        className="rounded-full border border-standard bg-bg-surface-raised px-4 py-2 text-sm text-ink-secondary transition hover:border-emphasis hover:text-ink-primary disabled:cursor-not-allowed disabled:text-ink-muted"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-soft bg-bg-surface px-5 py-4">
              {composerError && (
                <div className="mb-3 rounded-2xl border border-[#f0c6c6] bg-[#fff5f5] px-4 py-3 text-sm text-[#b03a3a]">
                  {composerError}
                </div>
              )}

              <form
                className="rounded-[24px] border border-soft bg-bg-surface-raised p-3 shadow-[0_10px_24px_rgba(15,23,42,0.04)]"
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleSubmit();
                }}
              >
                <textarea
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                  }}
                  disabled={sending || featureUnavailable}
                  rows={3}
                  placeholder={
                    featureUnavailable
                      ? "Chat will unlock once the backend endpoints are live."
                      : "Ask about a topic, decision, commitment, or recurring thread..."
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleSubmit();
                    }
                  }}
                  className="w-full resize-none border-0 bg-transparent px-2 py-1 text-sm leading-7 text-ink-primary outline-none placeholder:text-ink-muted disabled:cursor-not-allowed"
                />

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-soft pt-3">
                  <p className="text-xs text-ink-tertiary">Enter to send. Shift + Enter for a new line.</p>

                  <button
                    type="submit"
                    disabled={!draft.trim() || sending || featureUnavailable}
                    className="rounded-xl border border-emphasis bg-accent-subtle px-4 py-2 text-sm font-medium text-accent transition hover:border-accent disabled:cursor-not-allowed disabled:border-soft disabled:bg-bg-control disabled:text-ink-muted"
                  >
                    {sending ? "Streaming..." : "Send"}
                  </button>
                </div>
              </form>
            </div>
          </article>
        </section>
      </div>
    </div>
  );
}
