"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { config } from "@/lib/config";
import { useAuth } from "@/components/AuthProvider";
import { LOCALES, type Locale } from "@/lib/i18n/config";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { visibleNav } from "@/lib/nav";

function NavIcon({ name, className }: { name: string; className?: string }) {
  const baseClass = className || "w-5 h-5";
  switch (name) {
    case "nav.projects":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      );
    case "nav.profiles":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "nav.templates":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <path d="M12 2a10 10 0 0 0-10 10c0 5.523 4.477 10 10 10s10-4.477 10-10a10 10 0 0 0-10-10z" />
          <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          <line x1="9" y1="9" x2="9.01" y2="9" />
          <line x1="15" y1="9" x2="15.01" y2="9" />
        </svg>
      );
    case "nav.usage":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <path d="M3 3v18h18" />
          <path d="M18 17V9" />
          <path d="M13 17V5" />
          <path d="M8 17v-3" />
        </svg>
      );
    case "nav.llm":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
          <rect x="9" y="9" width="6" height="6" />
          <line x1="9" y1="1" x2="9" y2="4" />
          <line x1="15" y1="1" x2="15" y2="4" />
          <line x1="9" y1="20" x2="9" y2="23" />
          <line x1="15" y1="20" x2="15" y2="23" />
          <line x1="20" y1="9" x2="23" y2="9" />
          <line x1="20" y1="14" x2="23" y2="14" />
          <line x1="1" y1="9" x2="4" y2="9" />
          <line x1="1" y1="14" x2="4" y2="14" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={baseClass}>
          <circle cx="12" cy="12" r="10" />
        </svg>
      );
  }
}

/** Role-aware sidebar navigation. */
export function Nav() {
  const { me, signOut } = useAuth();
  const { locale, setLocale } = useLocale();
  const t = useT();
  const pathname = usePathname();
  if (!me) return null;

  const items = visibleNav(me.role);

  return (
    <nav aria-label="Main navigation" className="flex h-full flex-col bg-ink text-gray-300">
      {/* Brand area */}
      <div className="flex h-16 items-center px-6 border-b border-white/10">
        <div className="flex items-center gap-2 font-bold text-white tracking-tight">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-white">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="h-4 w-4">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </div>
          <span className="text-xl">NoteAI</span>
        </div>
      </div>

      {/* Nav items */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <ul className="flex flex-col gap-1.5">
          {items.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                    active 
                      ? "bg-accent/15 text-accent-light" 
                      : "text-gray-400 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <NavIcon name={item.labelKey} className={`h-5 w-5 ${active ? "text-accent-light" : "text-gray-500"}`} />
                  {t(item.labelKey)}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Footer / User section */}
      <div className="border-t border-white/10 p-4">
        <div className="mb-4 flex items-center gap-3 rounded-xl bg-white/5 p-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/20 text-sm font-semibold text-accent-light">
            {me.user.email?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{me.tenant.name}</p>
            <p className="truncate text-xs text-gray-400 capitalize">{me.role}</p>
          </div>
        </div>

        <label className="flex flex-col gap-1.5 text-xs text-gray-500">
          <span className="uppercase tracking-wider px-1">{t("nav.language")}</span>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value as Locale)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-sm text-gray-300 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          >
            {LOCALES.map((l) => (
              <option key={l.code} value={l.code} className="bg-ink text-gray-300">
                {l.label}
              </option>
            ))}
          </select>
        </label>

        {!config.liteMode && (
          <button
            type="button"
            onClick={signOut}
            className="mt-3 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            {t("nav.signOut")}
          </button>
        )}
      </div>
    </nav>
  );
}
