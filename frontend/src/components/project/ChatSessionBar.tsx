"use client";

import { useEffect, useRef, useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { ChatSession } from "@/services/api";

/**
 * Session switcher: one active thread at a time.
 *
 * Deliberately NOT stacked accordions. Several threads expanded in one column
 * rebuilds the unbounded-height scrolling this workspace just fixed — the message
 * list can only stay pinned if exactly one thread is mounted.
 */
interface ChatSessionBarProps {
  sessions: ChatSession[];
  activeId: string | null;
  busy: boolean;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onRename: (sessionId: string, title: string) => void;
  onDelete: (sessionId: string) => void;
}

export function ChatSessionBar({
  sessions,
  activeId,
  busy,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: ChatSessionBarProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const active = sessions.find((s) => s.id === activeId) ?? null;

  // Close the menu on outside click or Escape — a dropdown that traps the user is
  // worse than no dropdown.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setRenamingId(null);
      }
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (renamingId) inputRef.current?.focus();
  }, [renamingId]);

  const startRename = (session: ChatSession) => {
    setRenamingId(session.id);
    setDraft(session.title ?? "");
  };

  const commitRename = () => {
    const next = draft.trim();
    if (renamingId && next) onRename(renamingId, next);
    setRenamingId(null);
  };

  const label = active?.title?.trim() || t("chat.session.untitled");

  return (
    <div ref={containerRef} className="relative flex items-center gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex min-w-0 flex-1 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-left text-sm text-gray-700 transition-colors hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-light"
      >
        <span className="truncate">{label}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="ml-auto h-3.5 w-3.5 shrink-0 text-gray-400"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <button
        type="button"
        onClick={onCreate}
        disabled={busy}
        title={t("chat.session.new")}
        aria-label={t("chat.session.new")}
        className="shrink-0 rounded-lg border border-gray-200 bg-white p-1.5 text-gray-500 transition-colors hover:border-gray-300 hover:text-accent disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-accent-light"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label={t("chat.session.switch")}
          className="absolute left-0 top-full z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
        >
          {sessions.length === 0 && (
            <li className="px-3 py-2 text-xs text-gray-400">{t("chat.session.none")}</li>
          )}
          {sessions.map((session) => (
            <li key={session.id} role="option" aria-selected={session.id === activeId}>
              {renamingId === session.id ? (
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  aria-label={t("chat.session.rename")}
                  className="w-full border-none px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-light"
                />
              ) : (
                <div
                  className={`flex items-center gap-1 px-1 ${
                    session.id === activeId ? "bg-accent/5" : ""
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(session.id);
                      setOpen(false);
                    }}
                    className="min-w-0 flex-1 truncate px-2 py-2 text-left text-sm text-gray-700 hover:text-accent"
                  >
                    {session.title?.trim() || t("chat.session.untitled")}
                  </button>
                  <button
                    type="button"
                    onClick={() => startRename(session)}
                    aria-label={`${t("chat.session.rename")}: ${session.title ?? ""}`}
                    className="shrink-0 rounded p-1 text-gray-400 hover:text-accent"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onDelete(session.id);
                      setOpen(false);
                    }}
                    aria-label={`${t("chat.session.delete")}: ${session.title ?? ""}`}
                    className="shrink-0 rounded p-1 text-gray-400 hover:text-red-500"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
