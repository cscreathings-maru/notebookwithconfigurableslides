"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type Source } from "@/services/api";

const STATUS_STYLE: Record<string, string> = {
  queued: "text-ink/50",
  processing: "text-amber-600",
  ready: "text-emerald-600",
  failed: "text-red-600",
};

export function SourcesPanel({ projectId }: { projectId: string }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setSources(await api.listSources(projectId));
    } catch {
      /* ignore transient */
    }
  }, [projectId]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 2500);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [load]);

  const uploadFile = async (file: File) => {
    setError(null);
    try {
      await api.uploadSource(projectId, { file });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    }
  };

  const addUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError(null);
    try {
      await api.uploadSource(projectId, { url });
      setUrl("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Add URL failed");
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <h2 className="text-lg font-semibold text-ink">Sources</h2>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="file"
          onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])}
          className="text-sm text-ink/70"
        />
        <form onSubmit={addUrl} className="flex items-center gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
            className="rounded-lg border border-ink/15 px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            className="rounded-lg border border-ink/15 px-3 py-1.5 text-sm hover:bg-ink/5"
          >
            Add URL
          </button>
        </form>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <ul className="flex flex-col gap-1 text-sm">
        {sources.map((s) => (
          <li key={s.id} className="flex items-center justify-between border-b border-ink/5 py-2">
            <span className="truncate text-ink/80">
              {s.name} <span className="text-ink/40">({s.kind})</span>
            </span>
            <span className={STATUS_STYLE[s.status] ?? "text-ink/50"}>{s.status}</span>
          </li>
        ))}
        {sources.length === 0 && <li className="py-2 text-ink/40">No sources yet.</li>}
      </ul>
    </div>
  );
}
