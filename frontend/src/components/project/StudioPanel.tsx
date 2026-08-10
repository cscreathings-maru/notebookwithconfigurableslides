"use client";

import { useCallback, useEffect, useState } from "react";

import { OutlineBuilderCard } from "@/components/project/OutlineBuilderCard";
import { SlideEditorModal } from "@/components/project/SlideEditorModal";
import { saveBlob } from "@/lib/download";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import { api, type Generation } from "@/services/api";

const STATUS_STYLE: Record<string, string> = {
  ready: "bg-emerald-500 text-emerald-700",
  failed: "bg-red-500 text-red-700",
  queued: "bg-gray-200 text-gray-500",
  generating: "bg-amber-500 text-amber-700",
  validating: "bg-amber-500 text-amber-700",
};

const TERMINAL = new Set(["ready", "failed"]);

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

  const [editorOpen, setEditorOpen] = useState(false);
  const [activeEditor, setActiveEditor] = useState<{ id: string; url: string } | null>(null);

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

        <div className="flex flex-col gap-2 max-h-48 overflow-y-auto">
          {decks.map((g) => (
            <div
              key={g.id}
              className="flex items-center justify-between rounded-lg border border-gray-100 bg-white p-3 shadow-sm hover:shadow transition-shadow group"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${STATUS_STYLE[g.status]?.split(' ')[0] ?? "bg-gray-200"}`} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 capitalize">
                    {t(`status.gen.${g.status}` as MessageKey)}
                  </p>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {(g.params.tone as string) ?? "—"} · {(g.params.n_slides as number) ?? "—"} {t("studio.slidesUnit")}
                  </p>
                </div>
              </div>

              {g.status === "ready" && (
                <div className="flex shrink-0 gap-1.5 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
                  {/* Hidden when the backend has no editor URL: the engine never
                      produced a presentation, so there is nothing to open (T-1.2). */}
                  {g.editor_url && (
                  <button
                    type="button"
                    onClick={() => {
                      setActiveEditor({ id: g.id, url: g.editor_url! });
                      setEditorOpen(true);
                      // DG-4: from this point NoteAI's own download stops being
                      // offered for this generation (server-enforced; this call
                      // just gets the UI to reflect it without a reload). Fired
                      // after opening, not blocking it -- editing is the
                      // primary action, this is bookkeeping around it.
                      api.markStudioOpened(g.id).then(loadDecks).catch(() => {
                        setError(t("studio.studioOpenedTrackingFailed"));
                      });
                    }}
                    className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7 border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950 dark:text-blue-300"
                    title="Open interactive drag-and-edit slide canvas in Presenton"
                  >
                    <span>🎨 Editor</span>
                  </button>
                  )}
                  {g.artifacts.pptx && (
                    <button
                      type="button"
                      onClick={() => download(g, "pptx")}
                      className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7"
                      title="Download PPTX"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      PPTX
                    </button>
                  )}
                  {g.artifacts.pdf && (
                    <button
                      type="button"
                      onClick={() => download(g, "pdf")}
                      className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7"
                      title="Download PDF"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      PDF
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <SlideEditorModal
        isOpen={editorOpen}
        onClose={() => setEditorOpen(false)}
        title="🎨 Interactive Presentation Slide Editor"
        subtitle={`Polishing deck generation (${activeEditor?.id.slice(0, 8)}...) — move components and adjust font styling`}
        // Composed by the backend from the ENGINE's presentation id. Building it here
        // from Generation.id sent Presenton a Postgres UUID it had never seen (T-1.2).
        editorUrl={activeEditor?.url}
      />
    </div>
  );
}
