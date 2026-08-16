"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import type { CatalogStatus } from "@/services/api";

/** LD-3: the LLM cataloguing job's own lifecycle, shown independently of
 *  `InspectionBadge` (which reports the still-active geometric render path).
 *  Two badges on one row, deliberately -- they track different things during
 *  the transition described in `PLAN-LLM-DECK-PLANNING.md`. */
const STYLES: Record<CatalogStatus, string> = {
  cataloguing:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800/60",
  ready:
    "bg-emerald-50 text-emerald-700 border-emerald-200/60 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800/60",
  failed:
    "bg-red-50 text-red-700 border-red-200/60 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800/60",
  no_source:
    "bg-gray-50 text-gray-500 border-gray-200/60 dark:bg-gray-900/60 dark:text-gray-400 dark:border-gray-700/60",
};

export function CatalogStatusBadge({
  status,
  error,
  reviewed,
}: {
  status: CatalogStatus;
  error: string | null;
  reviewed: boolean;
}) {
  const t = useT();
  return (
    <span className={`inline-flex max-w-xs flex-col gap-0.5 rounded-md border px-2 py-1 text-xs font-medium ${STYLES[status]}`}>
      <span className="inline-flex items-center gap-1.5">
        {status === "cataloguing" && (
          <svg className="h-3 w-3 shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
            <circle cx="12" cy="12" r="9" opacity="0.25" />
            <path d="M21 12a9 9 0 0 0-9-9" />
          </svg>
        )}
        {t(`catalog.status.${status}` as MessageKey)}
        {status === "ready" && (
          <span className={reviewed ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}>
            · {t(reviewed ? "catalog.reviewed" : "catalog.notReviewed")}
          </span>
        )}
      </span>
      {error && status === "failed" && <span className="font-normal leading-snug opacity-90">{error}</span>}
    </span>
  );
}
