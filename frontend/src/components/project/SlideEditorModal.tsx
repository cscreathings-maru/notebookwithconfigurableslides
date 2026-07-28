"use client";

import React from "react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  editorUrl?: string;
}

export function SlideEditorModal({
  isOpen,
  onClose,
  title = "🎨 Interactive Presentation Canvas Launchpad",
  subtitle = "Move components, resize text boxes, and edit font styling like Google Slides",
  editorUrl = "/editor/",
}: Props) {
  if (!isOpen) return null;

  // Since Presenton is now hosted on the same domain under /editor/, we can use relative paths or the current origin
  const defaultBaseUrl = process.env.NEXT_PUBLIC_PRESENTON_UI_URL || ""; 
  const resolvedUrl = editorUrl.startsWith("/presenton")
    ? editorUrl.replace(/^\/presenton\/?/, `${defaultBaseUrl}/editor/`)
    : editorUrl.startsWith("http")
    ? editorUrl
    : `${defaultBaseUrl}${editorUrl.startsWith("/") ? "" : "/"}${editorUrl}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-ink w-full max-w-xl rounded-2xl shadow-elevated flex flex-col overflow-hidden border border-border/60">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border/50 bg-slate-50/80 dark:bg-slate-900/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-950/60 flex items-center justify-center text-blue-600 dark:text-blue-400 text-xl shadow-sm">
              🎨
            </div>
            <div>
              <h3 className="font-semibold text-base tracking-tight text-foreground flex items-center gap-2">
                {title}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-sm p-1.5 rounded-lg hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition"
          >
            ✕
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 flex flex-col gap-5">
          <div className="bg-blue-50/80 dark:bg-blue-950/40 rounded-xl p-4 border border-blue-200/60 dark:border-blue-900/50 flex flex-col gap-2.5 text-xs text-blue-900 dark:text-blue-200">
            <div className="flex items-center gap-2 font-semibold text-blue-700 dark:text-blue-300">
              <span className="text-sm">⚡</span>
              <span>Native Integrated Canvas</span>
            </div>
            <p className="leading-relaxed">
              Presenton launches securely as an integrated editor directly on this domain.
            </p>
            <div className="h-px bg-blue-200/60 dark:bg-blue-800/60 my-0.5" />
            <div className="grid grid-cols-2 gap-2 pt-0.5">
              <div className="flex items-center gap-1.5 text-[11px]">
                <span>🔐</span>
                <span>Auto-authenticated</span>
              </div>
              <div className="flex items-center gap-1.5 text-[11px]">
                <span>💾</span>
                <span>Auto-saves in real-time</span>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 bg-slate-50 dark:bg-slate-900/30 rounded-lg p-3 border border-border/40 text-xs">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Target Canvas URL</span>
            <code className="text-blue-600 dark:text-blue-400 font-mono break-all text-[11px] bg-white dark:bg-slate-900 px-2.5 py-1.5 rounded border border-border/50">
              {resolvedUrl}
            </code>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={onClose}
              className="btn-secondary text-xs py-2 px-4 font-medium"
            >
              Close / Done Editing
            </button>
            <a
              href={resolvedUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={onClose}
              className="btn-primary text-xs py-2 px-5 font-medium shadow-md flex items-center gap-2 hover:opacity-95 transition"
            >
              <span>↗ Open Live Interactive Canvas</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

