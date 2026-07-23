"use client";

import { useCallback, useEffect, useState } from "react";

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
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{t("guide.title")}</h2>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="rounded-lg border border-ink/15 px-3 py-1.5 text-xs hover:bg-ink/5 disabled:opacity-40"
        >
          {loading
            ? t("guide.generating")
            : guide?.summary
              ? t("guide.regenerate")
              : t("guide.generate")}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {!guide?.summary && !loading && (
        <p className="text-sm text-ink/50">{t("guide.empty")}</p>
      )}

      {loading && !guide?.summary && (
        <p className="text-sm text-ink/50">{t("guide.reading")}</p>
      )}

      {guide?.summary && (
        <>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/80">
            {guide.summary}
          </p>
          {guide.suggested_questions.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs uppercase tracking-wide text-ink/50">{t("guide.tryAsking")}</p>
              <div className="flex flex-wrap gap-2">
                {guide.suggested_questions.map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onAsk(q)}
                    className="rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-left text-xs text-accent transition-colors hover:bg-accent/10"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
