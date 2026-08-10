"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { RegistrationStatus } from "@/services/api";

/** Reports a template's registration outcome (TM-3: four distinct states, not one
 *  `fallback` that made "still working" and "the engine rejected it" look the same).
 *
 *  Renders nothing for a healthy registration -- the absence of a badge is the
 *  signal. `no_source`/`failed` templates still exist as rows, just without a
 *  usable engine template behind them, which is exactly the failure users
 *  previously could not see. */
export function RegistrationBadge({
  status,
  error,
}: {
  status: RegistrationStatus;
  error: string | null;
}) {
  const t = useT();
  if (status === "registered") return null;

  if (status === "pending") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200/60 dark:border-blue-800/60">
        <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5 shrink-0 animate-spin">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        {t("templates.registrationPending")}
      </span>
    );
  }

  const isFailed = status === "failed";
  const tone = isFailed
    ? "bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-200/60 dark:border-red-800/60"
    : "bg-gray-50 dark:bg-gray-900/60 text-gray-600 dark:text-gray-400 border-gray-200/60 dark:border-gray-700/60";

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${tone}`}
      title={error ?? undefined}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5 shrink-0">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      {t(isFailed ? "templates.registrationFailed" : "templates.registrationNoSource")}
    </span>
  );
}
