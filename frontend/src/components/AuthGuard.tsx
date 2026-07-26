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
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 text-sm text-gray-500 bg-surface">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-accent"></div>
        {t("app.loadingSession")}
      </div>
    );
  }

  if (!me) return null; // redirecting

  return (
    <div className="flex min-h-screen bg-surface">
      <aside
        className={`shrink-0 overflow-hidden bg-ink transition-[width] duration-300 ease-in-out ${
          collapsed ? "w-0" : "w-64 border-r border-ink/10"
        }`}
      >
        <div className="w-64 h-full">
          <Nav />
        </div>
      </aside>
      <main className="flex-1 flex flex-col h-screen overflow-y-auto animate-fade-in">
        <div className="p-8 pb-16">
          <button
            type="button"
            onClick={toggleNav}
            aria-label={collapsed ? t("nav.openSidebar") : t("nav.closeSidebar")}
            aria-expanded={!collapsed}
            className="mb-8 inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 shadow-sm transition-all hover:bg-gray-50 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-light"
          >
            {collapsed ? <MenuIcon /> : <PanelLeftIcon />}
          </button>
          {children}
        </div>
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
