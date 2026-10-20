"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { BASE_URL, DEMO_MODE, getSession, logout, subscribeToAuth, type Session } from "@/lib/api";

function deriveDisplayName(email: string): string {
  const localPart = email.split("@")[0] ?? email;
  const tokens = localPart
    .split(/[._+-]+/)
    .map((token) => token.trim())
    .filter(Boolean);

  if (tokens.length === 0) {
    return email;
  }

  return tokens
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function deriveInitials(email: string): string {
  const localPart = email.split("@")[0] ?? email;
  const tokens = localPart
    .split(/[._+-]+/)
    .map((token) => token.trim())
    .filter(Boolean);

  if (tokens.length >= 2) {
    return `${tokens[0][0] ?? ""}${tokens[1][0] ?? ""}`.toUpperCase();
  }

  return localPart.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() || "PN";
}

export function SessionControls() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const hasLoadedSessionRef = useRef(false);

  const loadSession = async () => {
    setLoadingSession(true);
    setAuthError(null);
    try {
      const current = await getSession();
      setSession(current);
      setAuthError(null);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Failed to load session");
    } finally {
      setLoadingSession(false);
    }
  };

  useEffect(() => {
    if (hasLoadedSessionRef.current) {
      return;
    }
    hasLoadedSessionRef.current = true;

    let mounted = true;

    void (async () => {
      setLoadingSession(true);
      setAuthError(null);
      try {
        const current = await getSession();
        if (!mounted) {
          return;
        }
        setSession(current);
        setAuthError(null);
      } catch (error) {
        if (!mounted) {
          return;
        }
        setAuthError(error instanceof Error ? error.message : "Failed to load session");
      } finally {
        if (mounted) {
          setLoadingSession(false);
        }
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    return subscribeToAuth((event) => {
      if (event.type === "refreshed") {
        setSession(event.session);
        setAuthError(null);
        setLoadingSession(false);
        return;
      }
      if (event.type === "expired") {
        setSession(null);
        setAuthError("Session expired. Sign in again.");
        setLoadingSession(false);
        return;
      }
      setSession(null);
      setAuthError(null);
      setLoadingSession(false);
    });
  }, []);

  useEffect(() => {
    if (!profileOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [profileOpen]);

  const loginUrl = `${BASE_URL}/auth/login`;
  const profileName = session?.email ? deriveDisplayName(session.email) : "Profile";
  const profileInitials = session?.email ? deriveInitials(session.email) : "PN";

  return (
    <div className="flex items-center gap-3 text-sm">
      {loadingSession && <span className="text-ink-tertiary">Checking session...</span>}

      {!loadingSession && authError && (
        <>
          <span className="rounded border border-soft px-2 py-1 text-ink-tertiary">{authError}</span>
          <button
            type="button"
            onClick={() => {
              void loadSession();
            }}
            className="rounded border border-standard px-3 py-1.5 text-ink-secondary hover:border-emphasis hover:text-ink-primary"
          >
            Retry
          </button>
        </>
      )}

      {!loadingSession && !authError && !session && (
        <a
          href={loginUrl}
          className="rounded border border-emphasis bg-accent-subtle px-3 py-1.5 font-medium text-accent hover:border-accent"
        >
          Sign in with Google
        </a>
      )}

      {!loadingSession && session && (
        <div className="relative" ref={profileMenuRef}>
          <button
            type="button"
            onClick={() => {
              setProfileOpen((current) => !current);
            }}
            className="flex items-center gap-2 rounded-full border border-standard bg-bg-control px-2 py-1.5 text-ink-secondary transition hover:border-emphasis hover:text-ink-primary"
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            aria-label="Open profile menu"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-bg-surface-raised text-xs font-semibold text-ink-primary">
              {profileInitials}
            </span>
            <span className="hidden text-sm md:inline">{profileName}</span>
          </button>

          {profileOpen && (
            <div className="absolute right-0 top-[calc(100%+0.5rem)] z-20 w-72 rounded-2xl border border-standard bg-bg-surface-raised p-2 shadow-lg shadow-black/5">
              <div className="rounded-2xl border border-soft bg-bg-control px-4 py-3">
                <p className="text-xs font-medium uppercase tracking-[0.08em] text-ink-tertiary">
                  Profile
                </p>
                <p className="mt-2 text-sm font-semibold text-ink-primary">{profileName}</p>
                <p className="mt-1 text-sm text-ink-secondary">{session.email}</p>
              </div>

              <div className="mt-2 space-y-1">
                <Link
                  href="/entities"
                  onClick={() => {
                    setProfileOpen(false);
                  }}
                  className="block rounded-xl px-3 py-2 text-sm text-ink-primary transition hover:bg-bg-control"
                >
                  Manage Entities
                </Link>
                <button
                  type="button"
                  disabled
                  className="block w-full cursor-not-allowed rounded-xl px-3 py-2 text-left text-sm text-ink-muted"
                >
                  Language
                </button>
                <button
                  type="button"
                  disabled
                  className="block w-full cursor-not-allowed rounded-xl px-3 py-2 text-left text-sm text-ink-muted"
                >
                  Help Center
                </button>
                <button
                  type="button"
                  disabled={DEMO_MODE}
                  onClick={async () => {
                    try {
                      await logout();
                    } finally {
                      setProfileOpen(false);
                      router.push("/");
                      router.refresh();
                    }
                  }}
                  className="block w-full rounded-xl px-3 py-2 text-left text-sm text-ink-primary transition hover:bg-bg-control disabled:cursor-not-allowed disabled:text-ink-muted"
                >
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
