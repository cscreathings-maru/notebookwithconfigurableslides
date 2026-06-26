"use client";

import { useState } from "react";

import { config } from "@/lib/config";
import { beginOidcLogin, loginWithDevToken } from "@/services/auth";

export default function LoginPage() {
  const [devToken, setDevToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSso = () => {
    try {
      beginOidcLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  const onDev = (e: React.FormEvent) => {
    e.preventDefault();
    if (!devToken.trim()) return;
    loginWithDevToken(devToken);
    window.location.href = "/projects";
  };

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <section
        aria-labelledby="login-heading"
        className="w-full max-w-sm rounded-2xl border border-ink/10 bg-white p-8 shadow-sm"
      >
        <h1 id="login-heading" className="text-xl font-semibold text-ink">
          Sign in
        </h1>
        <p className="mt-1 text-sm text-ink/60">
          Presentation Notebook LLM orchestration console.
        </p>

        <button
          type="button"
          onClick={onSso}
          className="mt-6 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          Continue with SSO
        </button>

        {config.devMode && (
          <form onSubmit={onDev} className="mt-6 border-t border-ink/10 pt-6">
            <label htmlFor="dev-token" className="text-xs font-medium text-ink/60">
              Dev token (OIDC_DEV_MODE)
            </label>
            <input
              id="dev-token"
              value={devToken}
              onChange={(e) => setDevToken(e.target.value)}
              placeholder="Paste an HS256 dev token"
              className="mt-1 w-full rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
            <button
              type="submit"
              className="mt-3 w-full rounded-lg border border-ink/15 px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ink/5"
            >
              Use dev token
            </button>
          </form>
        )}

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-600">
            {error}
          </p>
        )}
      </section>
    </main>
  );
}
