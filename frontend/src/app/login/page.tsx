"use client";

import { useState } from "react";

import { config } from "@/lib/config";
import { useT } from "@/lib/i18n/LocaleProvider";
import { beginOidcLogin, loginWithDevToken } from "@/services/auth";

export default function LoginPage() {
  const t = useT();
  const [devToken, setDevToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSso = () => {
    try {
      beginOidcLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.failed"));
    }
  };

  const onDev = (e: React.FormEvent) => {
    e.preventDefault();
    if (!devToken.trim()) return;
    loginWithDevToken(devToken);
    window.location.href = "/projects";
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[25%] -left-[10%] w-[50%] h-[50%] rounded-full bg-accent/5 blur-[100px]" />
        <div className="absolute top-[20%] -right-[10%] w-[40%] h-[60%] rounded-full bg-accent/5 blur-[120px]" />
      </div>

      <section
        aria-labelledby="login-heading"
        className="z-10 w-full max-w-[400px] animate-slide-up rounded-2xl border border-gray-100 bg-white p-10 shadow-elevated"
      >
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-md">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="h-7 w-7">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </div>
          <h1 id="login-heading" className="text-2xl font-bold tracking-tight text-gray-900">
            {t("login.title")}
          </h1>
          <p className="mt-2 text-sm text-gray-500">{t("login.subtitle")}</p>
        </div>

        <button
          type="button"
          onClick={onSso}
          className="btn-primary w-full py-2.5 text-base"
        >
          {t("login.sso")}
        </button>

        {config.devMode && (
          <div className="mt-8">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-white px-2 text-gray-400">Dev mode access</span>
              </div>
            </div>

            <form onSubmit={onDev} className="mt-6 flex flex-col gap-3">
              <label htmlFor="dev-token" className="sr-only">
                {t("login.devTokenLabel")}
              </label>
              <input
                id="dev-token"
                value={devToken}
                onChange={(e) => setDevToken(e.target.value)}
                placeholder={t("login.devTokenPlaceholder")}
                className="input-field text-center font-mono text-xs"
              />
              <button
                type="submit"
                className="btn-secondary w-full"
              >
                {t("login.useDevToken")}
              </button>
            </form>
          </div>
        )}

        {error && (
          <div role="alert" className="mt-6 rounded-lg bg-red-50 p-3 text-sm text-red-600 flex items-start gap-2">
            <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <p>{error}</p>
          </div>
        )}
      </section>
    </main>
  );
}
