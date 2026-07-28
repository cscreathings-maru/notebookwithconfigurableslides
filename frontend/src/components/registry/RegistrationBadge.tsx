"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { RegistrationStatus } from "@/services/api";

/** Warns when a template's branding will not reach the renderer.
 *
 *  Renders nothing for a healthy registration -- the absence of a warning is the
 *  signal. A `fallback` template still generates decks, just with the engine's stock
 *  theme, which is exactly the failure users previously could not see. */
export function RegistrationBadge({
  status,
  error,
}: {
  status: RegistrationStatus;
  error: string | null;
}) {
  const t = useT();
  if (status === "registered") return null;

  const isFailed = status === "failed";
  const tone = isFailed
    ? "bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-200/60 dark:border-red-800/60"
    : "bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-200/60 dark:border-amber-800/60";

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
      {t(isFailed ? "templates.registrationFailed" : "templates.registrationFallback")}
    </span>
  );
}
