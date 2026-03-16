"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BASE_URL, getSession, logout, subscribeToAuth, type Session } from "@/lib/api";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/meetings", label: "Meetings" },
  { href: "/search", label: "Search" },
  { href: "/topics", label: "Topics" },
  { href: "/commitments", label: "Actions" },
  { href: "/onboarding", label: "Onboarding" },
];

type AppFrameProps = {
  children: React.ReactNode;
};

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

export function AppFrame({ children }: AppFrameProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<Session | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const [globalQuery, setGlobalQuery] = useState("");

  const loadSession = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!options.silent) {
      setLoadingSession(true);
      setAuthError(null);
    }
    try {
      const current = await getSession();
      setSession(current);
      setAuthError(null);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Failed to load session");
    } finally {
      setLoadingSession(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

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
    const refreshVisibleSession = () => {
      void loadSession({ silent: true });
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        refreshVisibleSession();
      }
    };

    window.addEventListener("focus", refreshVisibleSession);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("focus", refreshVisibleSession);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [loadSession]);

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

  useEffect(() => {
    setGlobalQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  const loginUrl = useMemo(() => `${BASE_URL}/auth/login`, []);
  const profileName = useMemo(
    () => (session?.email ? deriveDisplayName(session.email) : "Profile"),
    [session?.email],
  );
  const profileInitials = useMemo(
    () => (session?.email ? deriveInitials(session.email) : "PN"),
    [session?.email],
  );
  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } finally {
      setProfileOpen(false);
      router.push("/");
      router.refresh();
    }
  }, [router]);
  const handleGlobalSearch = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = globalQuery.trim();
      const params = new URLSearchParams();
      if (trimmed) {
        params.set("q", trimmed);
      }
      router.push(`/search${params.toString() ? `?${params.toString()}` : ""}`);
    },
    [globalQuery, router],
  );

  return (
    <div className="min-h-screen bg-bg-base text-ink-primary">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px]">
        <aside className="sidebar-shell w-[248px] px-4 py-6">
          <div className="sidebar-logo mb-8 px-4 py-3 text-sm font-bold tracking-[0.18em] text-white">
            Pocket Nori
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`sidebar-nav-link block px-4 py-2.5 text-sm font-medium ${
                    isActive
                      ? "sidebar-nav-link--active"
                      : ""
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

        </aside>

        <div className="flex min-h-screen flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-standard bg-bg-surface-raised px-6 py-4">
            <form onSubmit={handleGlobalSearch} className="flex min-w-[240px] flex-1 max-w-xl gap-2">
              <input
                value={globalQuery}
                onChange={(event) => {
                  setGlobalQuery(event.target.value);
                }}
                placeholder="Search all meetings"
                className="w-full rounded border border-standard bg-bg-control px-3 py-2 text-sm text-ink-primary outline-none focus:border-emphasis"
                aria-label="Global search"
              />
              <button
                type="submit"
                className="rounded border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-medium text-accent"
              >
                Search
              </button>
            </form>

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

              {!loadingSession && !session && (
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
                          onClick={() => {
                            void handleLogout();
                          }}
                          className="block w-full rounded-xl px-3 py-2 text-left text-sm text-ink-primary transition hover:bg-bg-control"
                        >
                          Sign out
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </header>

          <main className="flex-1 px-6 py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
