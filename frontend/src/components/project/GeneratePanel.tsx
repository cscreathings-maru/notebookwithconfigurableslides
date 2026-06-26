"use client";

import { useEffect, useRef, useState } from "react";

import { api, ApiError, type Generation } from "@/services/api";

const TERMINAL = new Set(["ready", "failed"]);

export function GeneratePanel({
  projectId,
  outlineId,
  onSettled,
}: {
  projectId: string;
  outlineId: string | null;
  onSettled?: () => void;
}) {
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  const poll = (id: string) => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const g = await api.getGeneration(id);
        setGeneration(g);
        if (TERMINAL.has(g.status)) {
          if (timer.current) clearInterval(timer.current);
          onSettled?.();
        }
      } catch {
        /* keep polling */
      }
    }, 1800);
  };

  const generate = async () => {
    if (!outlineId) return;
    setError(null);
    setBusy(true);
    try {
      const g = await api.createGeneration(projectId, outlineId);
      setGeneration(g);
      onSettled?.(); // surface the queued version in history immediately
      poll(g.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Generate failed");
    } finally {
      setBusy(false);
    }
  };

  const download = async (format: "pptx" | "pdf") => {
    if (!generation) return;
    try {
      const { url } = await api.downloadGeneration(generation.id, format);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Download failed");
    }
  };

  const status = generation?.status;
  const inProgress = status !== undefined && !TERMINAL.has(status);

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Generate deck</h2>
        <button
          type="button"
          onClick={generate}
          disabled={busy || !outlineId || inProgress}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          title={!outlineId ? "Build a valid outline first" : undefined}
        >
          {inProgress ? "Generating…" : "Generate"}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {generation && (
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-ink/60">Status:</span>
            <span
              className={
                status === "ready"
                  ? "font-medium text-emerald-600"
                  : status === "failed"
                    ? "font-medium text-red-600"
                    : "text-amber-600"
              }
            >
              {status}
            </span>
            {inProgress && (
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" aria-hidden />
            )}
          </div>

          {generation.consistency_report && (
            <ul className="rounded-lg bg-ink/[0.03] p-3 text-xs">
              {generation.consistency_report.checks.map((c) => (
                <li key={c.name} className="flex items-center gap-2 py-0.5">
                  <span className={c.passed ? "text-emerald-600" : "text-red-600"}>
                    {c.passed ? "✓" : "✕"}
                  </span>
                  <span className="text-ink/70">{c.name}</span>
                </li>
              ))}
            </ul>
          )}

          {generation.error && <p className="text-red-600">{generation.error}</p>}

          {status === "ready" && (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => download("pptx")}
                disabled={!generation.artifacts.pptx}
                className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-40"
              >
                Download PPTX
              </button>
              <button
                type="button"
                onClick={() => download("pdf")}
                disabled={!generation.artifacts.pdf}
                className="rounded-lg border border-ink/15 px-3 py-1.5 text-xs hover:bg-ink/5 disabled:opacity-40"
              >
                Download PDF
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
