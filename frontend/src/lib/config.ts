/**
 * Public client configuration.
 *
 * Only NEXT_PUBLIC_* values reach the browser. These are public OIDC parameters
 * and the orchestrator's same-origin API base — never engine URLs or secrets,
 * which live exclusively in the backend.
 */

export const config = {
  // Same-origin: the browser hits Traefik -> orchestrator. Override for local dev.
  // On the server side (SSR), we must hit the internal Docker service to avoid NAT loopback timeouts.
  apiBase: typeof window === "undefined" 
    ? (process.env.INTERNAL_API_URL ?? "http://orchestrator:8000") 
    : (process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1"),

  oidc: {
    issuer: process.env.NEXT_PUBLIC_OIDC_ISSUER ?? "",
    clientId: process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "orchestrator",
    // Public client redirect target after IdP login.
    redirectUri: process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI ?? "",
  },

  // Enables the local dev token form on the login page (pairs with backend
  // OIDC_DEV_MODE). Never enable in production.
  devMode: process.env.NEXT_PUBLIC_DEV_MODE === "true",
} as const;
