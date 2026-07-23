/**
 * Client-side UI preferences persisted in localStorage.
 *
 * Small, SSR-safe get/set helpers mirroring session.ts (same `pnl.` key prefix
 * and `typeof window` guard). Values that are unset return null so callers can
 * fall back to a context-aware default (e.g. collapse the nav on narrow screens).
 */

import type { Locale } from "@/lib/i18n/config";

const NAV_COLLAPSED_KEY = "pnl.ui.navCollapsed";
const LOCALE_KEY = "pnl.ui.locale";

export function getNavCollapsed(): boolean | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(NAV_COLLAPSED_KEY);
  return value === null ? null : value === "true";
}

export function setNavCollapsed(collapsed: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(NAV_COLLAPSED_KEY, String(collapsed));
}

export function getStoredLocale(): Locale | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(LOCALE_KEY);
  return value === "id" || value === "en" ? value : null;
}

export function setStoredLocale(locale: Locale): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCALE_KEY, locale);
}
