"use client";

import { useCallback, useEffect, useState } from "react";

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
      setError(err instanceof ApiError ? err.message : "Could not generate the guide.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Notebook guide</h2>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="rounded-lg border border-ink/15 px-3 py-1.5 text-xs hover:bg-ink/5 disabled:opacity-40"
        >
          {loading ? "Generating…" : guide?.summary ? "Regenerate" : "Generate"}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {!guide?.summary && !loading && (
        <p className="text-sm text-ink/50">
          Once your sources are ready, generate an overview and starter questions.
        </p>
      )}

      {loading && !guide?.summary && (
        <p className="text-sm text-ink/50">Reading your sources…</p>
      )}

      {guide?.summary && (
        <>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/80">
            {guide.summary}
          </p>
          {guide.suggested_questions.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs uppercase tracking-wide text-ink/50">Try asking</p>
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
