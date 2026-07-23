"use client";

/**
 * Gate for authenticated routes: while the session resolves, show a loader; on
 * 401 redirect to /login; otherwise render the app chrome. The backend remains
 * the real access authority — this only governs what the shell displays.
 */

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { config } from "@/lib/config";
import { useAuth } from "@/components/AuthProvider";
import { Nav } from "@/components/Nav";
import { useT } from "@/lib/i18n/LocaleProvider";
import { getNavCollapsed, setNavCollapsed } from "@/services/uiPrefs";

const MOBILE_QUERY = "(max-width: 768px)";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { me, loading, error } = useAuth();
  const router = useRouter();
  const t = useT();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    // Lite mode has no login page to fall back to; the session is always present.
    if (config.liteMode) return;
    if (!loading && (error === "unauthenticated" || !me)) {
      router.replace("/login");
    }
  }, [loading, error, me, router]);

  useEffect(() => {
    // Honor a saved preference; otherwise start collapsed on narrow screens.
    const saved = getNavCollapsed();
    setCollapsed(saved ?? window.matchMedia(MOBILE_QUERY).matches);
  }, []);

  const toggleNav = () => {
    setCollapsed((prev) => {
      const next = !prev;
      setNavCollapsed(next);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink/50">
        {t("app.loadingSession")}
      </div>
    );
  }

  if (!me) return null; // redirecting

  return (
    <div className="flex min-h-screen">
      <aside
        className={`shrink-0 overflow-hidden bg-white transition-[width] duration-200 ${
          collapsed ? "w-0" : "w-64 border-r border-ink/10"
        }`}
      >
        <Nav />
      </aside>
      <main className="flex-1 p-8">
        <button
          type="button"
          onClick={toggleNav}
          aria-label={collapsed ? t("nav.openSidebar") : t("nav.closeSidebar")}
          aria-expanded={!collapsed}
          className="mb-6 inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink/15 text-ink/70 transition-colors hover:bg-ink/5"
        >
          {collapsed ? <MenuIcon /> : <PanelLeftIcon />}
        </button>
        {children}
      </main>
    </div>
  );
}

function MenuIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  );
}

function PanelLeftIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="9" y1="4" x2="9" y2="20" />
    </svg>
  );
}
