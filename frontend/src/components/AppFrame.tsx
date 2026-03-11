"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BASE_URL, getSession, logout, type Session } from "@/lib/api";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/meetings", label: "Meetings" },
  { href: "/search", label: "Search" },
  { href: "/topics", label: "Topics" },
  { href: "/commitments", label: "Commitments" },
  { href: "/onboarding", label: "Onboarding" },
];

type AppFrameProps = {
  children: React.ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    setLoadingSession(true);
    setAuthError(null);
    try {
      const current = await getSession();
      setSession(current);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Failed to load session");
    } finally {
      setLoadingSession(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const loginUrl = useMemo(() => `${BASE_URL}/auth/login`, []);

  return (
    <div className="min-h-screen bg-bg-base text-ink-primary">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px]">
        <aside className="w-[240px] border-r border-standard bg-bg-surface px-4 py-6">
          <div className="mb-8 border border-emphasis bg-accent-subtle px-3 py-2 text-sm font-semibold tracking-wide text-accent">
            FARZ
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`block rounded-md border px-3 py-2 text-sm transition ${
                    isActive
                      ? "border-emphasis bg-accent-subtle text-accent"
                      : "border-transparent text-ink-secondary hover:border-soft hover:text-ink-primary"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-8 rounded-md border border-soft px-3 py-3 text-xs text-ink-tertiary">
            Live backend mode active. Calendar sync is now wired to Google Calendar. Phase 4
            brief generation is the next milestone.
          </div>
        </aside>

        <div className="flex min-h-screen flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-standard bg-bg-surface-raised px-6 py-4">
            <div className="text-sm text-ink-secondary">Private Office Interface</div>
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
                <>
                  <span className="rounded border border-soft px-2 py-1 text-ink-secondary">
                    {session.email}
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await logout();
                      } finally {
                        setSession(null);
                        setAuthError(null);
                        router.push("/");
                        router.refresh();
                      }
                    }}
                    className="rounded border border-standard px-3 py-1.5 text-ink-secondary hover:border-emphasis hover:text-ink-primary"
                  >
                    Logout
                  </button>
                </>
              )}
            </div>
          </header>

          <main className="flex-1 px-6 py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
