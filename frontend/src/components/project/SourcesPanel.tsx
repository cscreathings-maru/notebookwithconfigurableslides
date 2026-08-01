"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import { api, ApiError, type Source } from "@/services/api";

const STATUS_STYLE: Record<string, string> = {
  queued: "bg-gray-200 text-gray-500",
  processing: "bg-amber-500 text-amber-700",
  ready: "bg-emerald-500 text-emerald-700",
  failed: "bg-red-500 text-red-700",
};

export function SourcesPanel({ projectId }: { projectId: string }) {
  const t = useT();
  const [sources, setSources] = useState<Source[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listSources(projectId);
      setSources(data);
      const hasInFlight = data.some(s => s.status === 'queued' || s.status === 'processing');
      if (!hasInFlight && timer.current) {
        clearInterval(timer.current);
        timer.current = null;
      }
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
      if (!timer.current) timer.current = setInterval(load, 2500);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("sources.uploadFailed"));
    }
  };

  const addUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError(null);
    try {
      await api.uploadSource(projectId, { url });
      setUrl("");
      if (!timer.current) timer.current = setInterval(load, 2500);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("sources.addUrlFailed"));
    }
  };

  return (
    <div className="card p-5 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-4">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
        <h2 className="text-base font-semibold text-gray-900">{t("sources.title")}</h2>
      </div>

      <div className="flex flex-col gap-3 mb-5">
        <div 
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-gray-200 rounded-lg p-4 flex flex-col items-center justify-center text-center cursor-pointer transition-colors hover:border-accent hover:bg-accent-faint"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400 mb-2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span className="text-sm font-medium text-accent">Click to upload files</span>
          <span className="text-xs text-gray-500 mt-1">PDF, DOCX, TXT</span>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.[0]) uploadFile(e.target.files[0]);
              e.target.value = ''; // reset
            }}
          />
        </div>

        <form onSubmit={addUrl} className="flex gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-gray-400">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
              </svg>
            </div>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("sources.urlPlaceholder")}
              className="input-field pl-9"
            />
          </div>
          <button type="submit" className="btn-secondary whitespace-nowrap">
            {t("sources.addUrl")}
          </button>
        </form>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 flex items-start gap-2">
          <p>{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <ul className="flex flex-col gap-2">
          {sources.map((s) => (
            <li key={s.id} className="flex items-center justify-between bg-gray-50 rounded-lg p-3 group hover:bg-gray-100 transition-colors">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-gray-400 shrink-0">
                  <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                  <polyline points="13 2 13 9 20 9" />
                </svg>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 truncate">{s.name}</p>
                  <p className="text-xs text-gray-500 uppercase">{s.kind}</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 ml-2 shrink-0">
                <div className={`w-2 h-2 rounded-full ${STATUS_STYLE[s.status]?.split(' ')[0] ?? "bg-gray-200"}`} />
                <span className="text-xs font-medium text-gray-600 capitalize">
                  {t(`status.source.${s.status}` as MessageKey)}
                </span>
              </div>
            </li>
          ))}
          {sources.length === 0 && (
            <li className="flex flex-col items-center justify-center py-8 text-center text-gray-400">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-8 h-8 mb-2 opacity-50">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
              </svg>
              <span className="text-sm">{t("sources.empty")}</span>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
