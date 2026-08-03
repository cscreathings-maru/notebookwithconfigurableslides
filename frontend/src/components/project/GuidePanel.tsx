"use client";

import { useCallback, useEffect, useState } from "react";

import { Markdown } from "@/components/ui/Markdown";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Guide } from "@/services/api";

/**
 * Auto notebook guide: a generated summary + suggested starter questions.
 * Clicking a suggested question routes it into the chat (via `onAsk`).
 */
export function GuidePanel({
  projectId,
  onAsk,
}: {
  projectId: string;
  onAsk: (question: string) => void;
}) {
  const t = useT();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setGuide(await api.getGuide(projectId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setGuide(null);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      setGuide(await api.regenerateGuide(projectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("guide.failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    // `overflow-hidden` clips the decorative blur; height is left to the rail, which
    // owns the single scroll region for this column.
    <div className="p-6 flex flex-col gap-5 relative overflow-hidden">
      {/* Decorative background element */}
      <div className="absolute -right-4 -top-4 w-24 h-24 bg-accent-faint rounded-full opacity-50 blur-xl pointer-events-none" />

      <div className="flex items-center justify-between relative z-10">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <h2 className="text-base font-semibold text-gray-900">{t("guide.title")}</h2>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="btn-secondary py-1.5 px-3 text-xs flex items-center gap-1.5"
        >
          {loading ? (
            <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          )}
          {loading ? t("guide.generating") : guide?.summary ? t("guide.regenerate") : t("guide.generate")}
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {!guide?.summary && !loading && (
        <div className="py-6 flex flex-col items-center justify-center text-center">
          <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
          </div>
          <p className="text-sm text-gray-500">{t("guide.empty")}</p>
        </div>
      )}

      {loading && !guide?.summary && (
        <div className="py-8 flex flex-col items-center justify-center text-center animate-pulse">
          <div className="flex gap-1 mb-3">
            <div className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <p className="text-sm text-gray-500">{t("guide.reading")}</p>
        </div>
      )}

      {guide?.summary && (
        <div className="flex flex-col gap-5 animate-fade-in relative z-10">
          {/* `prose`/`prose-sm` were no-ops here: @tailwindcss/typography is not a
              dependency of this project, so the summary rendered as unstyled raw
              markdown. `Markdown` does the job the class names implied. */}
          <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-gray-700">
            <Markdown>{guide.summary}</Markdown>
          </div>
          {guide.suggested_questions.length > 0 && (
            <div className="flex flex-col gap-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                {t("guide.tryAsking")}
              </p>
              <div className="flex flex-wrap gap-2">
                {guide.suggested_questions.map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onAsk(q)}
                    className="inline-flex items-center rounded-full bg-accent-faint px-3.5 py-1.5 text-xs font-medium text-accent hover:bg-accent-light hover:text-accent-active transition-all active:scale-[0.98] text-left"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
