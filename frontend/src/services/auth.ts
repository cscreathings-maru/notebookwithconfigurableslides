/**
 * OIDC login helpers.
 *
 * Production: redirect to the IdP's authorization endpoint (Authorization Code +
 * PKCE for a public client). The callback route exchanges the code and stores the
 * resulting token via session.ts. Dev mode: a pasted token is stored directly,
 * matching the backend's OIDC_DEV_MODE.
 */

import { config } from "@/lib/config";
import { setToken } from "@/services/session";

export function beginOidcLogin(): void {
  if (!config.oidc.issuer || !config.oidc.redirectUri) {
    throw new Error("OIDC is not configured (set NEXT_PUBLIC_OIDC_* env vars).");
  }
  const params = new URLSearchParams({
    client_id: config.oidc.clientId,
    redirect_uri: config.oidc.redirectUri,
    response_type: "code",
    scope: "openid profile email",
  });
  const authorize = `${config.oidc.issuer.replace(/\/$/, "")}/protocol/openid-connect/auth`;
  window.location.href = `${authorize}?${params.toString()}`;
}

export function loginWithDevToken(token: string): void {
  setToken(token.trim());
}
