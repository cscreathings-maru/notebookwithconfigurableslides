"use client";

import { useState } from "react";

import { Markdown } from "@/components/ui/Markdown";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { ChatMessage } from "@/services/api";

/**
 * Phase F4: a full-height reader for a long chat answer.
 *
 * NOT a modal, NOT a new browser window (both were considered — see
 * revamp/PLAN-LONG-ANSWERS-AND-LINKS.md). It renders as a third right-rail tab
 * beside Ringkasan and Studio, the same column already used to view supporting
 * material, so the conversation stays visible while reading. A new window loses
 * the app shell, the citations and the session; a modal covers the very thread the
 * answer came from.
 */
interface ReaderPanelProps {
  message: ChatMessage;
  onClose: () => void;
  onContinue: () => void;
  continuing: boolean;
  error?: string | null;
}

export function ReaderPanel({
  message,
  onClose,
  onContinue,
  continuing,
  error,
}: ReaderPanelProps) {
  const t = useT();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard permission denied -- not worth surfacing an error for */
    }
  };

  const download = () => {
    const blob = new Blob([message.content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `jawaban-${message.id.slice(0, 8)}.md`;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1.5 border-b border-gray-100 bg-white p-3">
        <button
          type="button"
          onClick={copy}
          className="rounded-md px-2 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        >
          {copied ? t("reader.copied") : t("reader.copy")}
        </button>
        <button
          type="button"
          onClick={download}
          className="rounded-md px-2 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        >
          {t("reader.download")}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("reader.close")}
          className="ml-auto rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {error && (
          <div role="alert" className="mb-4 rounded-lg bg-red-50 p-2.5 text-sm text-red-600">
            {error}
          </div>
        )}

        <Markdown>{message.content}</Markdown>

        {message.truncated && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5 shrink-0">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span className="flex-1">{t("chat.truncated")}</span>
            <button
              type="button"
              onClick={onContinue}
              disabled={continuing}
              className="shrink-0 font-semibold underline underline-offset-2 hover:no-underline disabled:opacity-50"
            >
              {continuing ? t("chat.continuing") : t("chat.continue")}
            </button>
          </div>
        )}

        {message.citations.length > 0 && (
          <div className="mt-5 flex flex-col gap-2 border-t border-gray-100 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              {t("reader.sources")}
            </p>
            {message.citations.map((c, i) => (
              <div
                key={i}
                className="rounded-lg border border-accent/15 bg-accent/5 p-2.5 text-xs leading-relaxed text-gray-600"
              >
                {c.snippet}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
