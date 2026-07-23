/**
 * Client-side UI preferences persisted in localStorage.
 *
 * Small, SSR-safe get/set helpers mirroring session.ts (same `pnl.` key prefix
 * and `typeof window` guard). Values that are unset return null so callers can
 * fall back to a context-aware default (e.g. collapse the nav on narrow screens).
 */

const NAV_COLLAPSED_KEY = "pnl.ui.navCollapsed";

export function getNavCollapsed(): boolean | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(NAV_COLLAPSED_KEY);
  return value === null ? null : value === "true";
}

export function setNavCollapsed(collapsed: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(NAV_COLLAPSED_KEY, String(collapsed));
}
