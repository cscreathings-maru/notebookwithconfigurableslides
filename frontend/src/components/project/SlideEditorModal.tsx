"use client";

import React, { useState } from "react";

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
  title = "🎨 Interactive Slide & Template Editor",
  subtitle = "Move components, resize text boxes, and edit font styling like Google Slides",
  editorUrl = "/presenton/",
}: Props) {
  const [isLoading, setIsLoading] = useState(true);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 md:p-8 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-ink w-full max-w-7xl h-[88vh] rounded-2xl shadow-elevated flex flex-col overflow-hidden border border-border/60">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50 bg-slate-50/80 dark:bg-slate-900/40">
          <div className="flex flex-col">
            <div className="flex items-center gap-2.5">
              <h3 className="font-semibold text-lg tracking-tight text-foreground flex items-center gap-2">
                {title}
              </h3>
              <span className="text-xs bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 px-2.5 py-0.5 rounded-full font-medium border border-blue-200/60 dark:border-blue-800/60">
                Live Interactive Canvas
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={editorUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 transition"
              title="Open editor in a new fullscreen tab"
            >
              <span>↗ Open Fullscreen</span>
            </a>
            <button
              onClick={onClose}
              className="btn-primary text-xs py-1.5 px-4 font-medium shadow-sm"
            >
              Done Editing
            </button>
          </div>
        </div>

        {/* Toolbar Notice / Guidance */}
        <div className="bg-blue-50/70 dark:bg-blue-950/30 px-6 py-2 border-b border-blue-100 dark:border-blue-900/40 flex items-center justify-between text-xs text-blue-800 dark:text-blue-200">
          <div className="flex items-center gap-2">
            <span className="font-bold">💡 Tip:</span>
            <span>
              Click on any text box or component on the slide canvas to drag, resize, or adjust font sizes. Changes are auto-saved to Presenton.
            </span>
          </div>
          <button
            onClick={() => setIsLoading(true)}
            className="underline hover:text-blue-600 transition"
          >
            Reload Canvas
          </button>
        </div>

        {/* Canvas Body */}
        <div className="flex-1 w-full bg-slate-100 dark:bg-slate-950 relative overflow-hidden flex items-center justify-center">
          {isLoading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/80 dark:bg-ink/80 backdrop-blur-sm gap-3">
              <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-muted-foreground">Loading Presenton Interactive Canvas...</p>
            </div>
          )}
          <iframe
            src={editorUrl}
            onLoad={() => setIsLoading(false)}
            className="w-full h-full border-0 bg-white"
            title="Presenton Interactive Canvas Editor"
          />
        </div>
      </div>
    </div>
  );
}
