"use client";

/**
 * Auth context: resolves the current session via GET /auth/me and exposes it.
 *
 * Identity and role come from the backend (server-side, from the token) — the
 * client never decides its own tenant or role. On 401 the consumer redirects
 * to /login.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { config } from "@/lib/config";
import { api, ApiError, type Me } from "@/services/api";
import { clearToken } from "@/services/session";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

// Static admin session used in lite mode — no /auth/me fetch, no token, no login.
const LITE_ME: Me = {
  user: { id: "lite", email: "demo@local", role: "admin", status: "active" },
  tenant: {
    id: "lite",
    name: config.liteTenantName,
    slug: "demo",
    status: "active",
    region: null,
  },
  role: "admin",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(config.liteMode ? LITE_ME : null);
  const [loading, setLoading] = useState(!config.liteMode);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Lite mode: the session is static; never call the auth endpoint.
    if (config.liteMode) return;

    let active = true;
    api
      .me()
      .then((data) => active && setMe(data))
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          setError("unauthenticated");
        } else {
          setError(err instanceof Error ? err.message : "Failed to load session");
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const signOut = () => {
    // No auth to sign out of in lite mode.
    if (config.liteMode) return;
    clearToken();
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ me, loading, error, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
