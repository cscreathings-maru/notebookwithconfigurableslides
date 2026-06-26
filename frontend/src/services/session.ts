/**
 * Client-side bearer-token storage for the authenticated session.
 *
 * The token is obtained via the OIDC flow (or pasted in dev mode) and attached
 * to every orchestrator API call. Stored in localStorage for the MVP shell;
 * a future iteration can move to httpOnly cookies set by an auth callback route.
 */

const TOKEN_KEY = "pnl.session.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}
