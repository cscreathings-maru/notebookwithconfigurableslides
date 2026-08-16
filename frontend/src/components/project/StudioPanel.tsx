"use client";

import { useCallback, useEffect, useState } from "react";

import { OutlineBuilderCard } from "@/components/project/OutlineBuilderCard";
import { saveBlob } from "@/lib/download";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import { api, type Generation } from "@/services/api";

const STATUS_STYLE: Record<string, string> = {
  ready: "bg-emerald-500 text-emerald-700",
  failed: "bg-red-500 text-red-700",
  queued: "bg-gray-200 text-gray-500",
  // Vestigial (LD-9): no new generation ever lands here anymore -- the
  // per-deck review gate moved to the template's catalog (L3). Kept only so
  // a pre-cutover row still renders a sane colour instead of falling
  // through to the default.
  awaiting_review: "bg-amber-400 text-amber-800",
  generating: "bg-amber-500 text-amber-700",
  validating: "bg-amber-500 text-amber-700",
};

const TERMINAL = new Set(["ready", "failed", "awaiting_review"]);
const IN_FLIGHT = new Set(["queued", "generating", "validating"]);

/** Which consistency checks a failed governed deck actually tripped. The report
 *  has always carried this; nothing rendered it, so "failed" was the whole
 *  explanation the user got. */
function failedChecks(g: Generation): string[] {
  return (g.consistency_report?.checks ?? []).filter((c) => !c.passed).map((c) => c.name);
}

/**
 * Studio's own generation surface now IS the outline-first flow
 * (OutlineBuilderCard, `embedded`) -- previously a separate one-shot form that
 * bypassed the outline confirmation step chat's `/generate` already required.
 * Kept as two entry points to the same component rather than two different
 * generation experiences that could drift.
 */
export function StudioPanel({ projectId }: { projectId: string }) {
  const t = useT();
  const [decks, setDecks] = useState<Generation[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Bumping this remounts OutlineBuilderCard from scratch -- Studio is a
  // persistent panel (nothing to dismiss the way a chat card is), so "start
  // over" after Cancel/Discard is a fresh mount instead of a fresh card.
  const [formKey, setFormKey] = useState(0);

  const loadDecks = useCallback(() => {
    api.listGenerations(projectId).then(setDecks).catch(() => setDecks([]));
  }, [projectId]);

  useEffect(() => {
    loadDecks();
  }, [loadDecks]);

  const pollUntilDone = useCallback(
    async (id: string) => {
      for (let i = 0; i < 200; i++) {
        try {
          const g = await api.getGeneration(id);
          loadDecks();
          if (TERMINAL.has(g.status)) return;
        } catch {
          /* keep polling */
        }
        await new Promise((r) => setTimeout(r, 2500));
      }
    },
    [loadDecks],
  );

  const download = async (g: Generation, fmt: "pptx" | "pdf") => {
    try {
      const blob = await api.downloadGeneration(g.id, fmt);
      saveBlob(blob, `deck-${g.id}.${fmt}`);
    } catch {
      setError(t("studio.downloadUnavailable"));
    }
  };

  return (
    // No `h-full` and no inner scroller: the right rail is the single scroll region
    // (`overflow-y-auto` on its content area). Forcing this panel to the rail's height
    // squeezed the form into ~200px of its ~450px of controls, clipping a select
    // mid-row. Flowing naturally lets the rail scroll the whole panel instead.
    <div className="p-6 flex flex-col gap-6">
      <div className="flex items-center gap-2 border-b border-gray-100 pb-4">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
          <path d="M12 2a10 10 0 0 0-10 10c0 5.523 4.477 10 10 10s10-4.477 10-10a10 10 0 0 0-10-10z" />
          <path d="M12 6v6l4 2" />
        </svg>
        <h2 className="text-base font-semibold text-gray-900">{t("studio.title")}</h2>
      </div>

      <OutlineBuilderCard
        key={formKey}
        projectId={projectId}
        embedded
        onCancel={() => setFormKey((k) => k + 1)}
        onGenerated={(gen) => {
          loadDecks();
          pollUntilDone(gen.id);
          setFormKey((k) => k + 1);
        }}
      />

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="pt-4 border-t border-gray-100 flex flex-col gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t("studio.decks")}</h3>
        {decks.length === 0 && (
          <div className="py-4 text-center rounded-lg border border-dashed border-gray-200">
            <p className="text-sm text-gray-400">{t("studio.noDecks")}</p>
          </div>
        )}

        <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
          {decks.map((g) => (
            <div
              key={g.id}
              className="flex flex-col gap-2 rounded-lg border border-gray-100 bg-white p-3 shadow-sm transition-shadow hover:shadow"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_STYLE[g.status]?.split(" ")[0] ?? "bg-gray-200"} ${
                      IN_FLIGHT.has(g.status) ? "animate-pulse" : ""
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium capitalize text-gray-900">
                      {t(`status.gen.${g.status}` as MessageKey)}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      {(g.params.tone as string) ?? "—"} · {(g.params.n_slides as number) ?? "—"}{" "}
                      {t("studio.slidesUnit")}
                    </p>
                  </div>
                </div>

                {/* Always visible, never hover-gated: these were
                    `opacity-0 group-hover:opacity-100`, which on any touch
                    device meant the only way to get the finished deck out of
                    the product was unreachable. */}
                {g.status === "ready" && (
                  <div className="ml-3 flex shrink-0 gap-1.5">
                    {g.artifacts.pptx && (
                      <button
                        type="button"
                        onClick={() => download(g, "pptx")}
                        className="btn-secondary flex h-7 items-center gap-1 px-2 py-1 text-xs"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        {t("studio.downloadPptx")}
                      </button>
                    )}
                    {g.artifacts.pdf && (
                      <button
                        type="button"
                        onClick={() => download(g, "pdf")}
                        className="btn-secondary flex h-7 items-center gap-1 px-2 py-1 text-xs"
                      >
                        PDF
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Vestigial (LD-9): the per-deck review gate that used to park
                  a generation here is retired -- no new deck ever reaches
                  this status. A pre-cutover row stuck here has no action
                  left to take (the approve endpoint is gone); this just
                  says so rather than offering a dead button. */}
              {g.status === "awaiting_review" && (
                <div className="rounded-md bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
                  {t("studio.awaitingReviewStale")}
                </div>
              )}

              {/* A failed deck used to render the word "failed" and nothing
                  else -- the reason was on the wire the whole time. */}
              {g.status === "failed" && (
                <div className="rounded-md bg-red-50 px-2.5 py-2 text-xs text-red-700">
                  <p>{g.error ?? t("studio.generationFailed")}</p>
                  {failedChecks(g).length > 0 && (
                    <ul className="mt-1 list-disc pl-4">
                      {failedChecks(g).map((name) => (
                        <li key={name}>{t(`consistency.${name}` as MessageKey)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
