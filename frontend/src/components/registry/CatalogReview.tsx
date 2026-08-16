"use client";

import { useCallback, useEffect, useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Design, type DesignCatalog } from "@/services/api";

/**
 * LD-4 / L3: an admin reviews the LLM's `DesignCatalog` before a template is
 * usable for planning -- the review gate this plan moves from per-deck
 * (the old `LayoutPlanReview`) to per-template (assessment §6, §8).
 *
 * A schematic wireframe (like `deck/preview.py`'s layout diagrams) is NOT
 * shown here: `Anchor` carries no position, only `anchor_id`/`purpose`/
 * `char_budget` (deliberately -- `deck/catalog.py`'s module docstring), so
 * there is no geometry to draw from the stored catalog alone. This screen is
 * therefore textual: role + anchor purposes + current text, editable inline.
 * Recorded as a known gap in the phase report rather than left unstated.
 */
export function CatalogReview({
  templateId,
  onDone,
  onCancel,
}: {
  templateId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [catalog, setCatalog] = useState<DesignCatalog | null>(null);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getTemplateCatalog(templateId)
      .then((c) => {
        if (cancelled) return;
        setCatalog(c);
        setDesigns(c.designs);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t("catalog.loadFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [templateId, t]);

  const updateRole = useCallback((designId: string, role: string) => {
    setDesigns((prev) => prev.map((d) => (d.design_id === designId ? { ...d, role } : d)));
  }, []);

  const updateAnchorPurpose = useCallback((designId: string, anchorId: string, purpose: string) => {
    setDesigns((prev) =>
      prev.map((d) =>
        d.design_id !== designId
          ? d
          : { ...d, anchors: d.anchors.map((a) => (a.anchor_id === anchorId ? { ...a, purpose } : a)) },
      ),
    );
  }, []);

  const approve = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.reviewTemplateCatalog(templateId, designs);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("catalog.approveFailed"));
    } finally {
      setBusy(false);
    }
  }, [templateId, designs, onDone, t]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="catalog-review-heading">
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col gap-4 overflow-hidden rounded-xl bg-white p-6 shadow-elevated dark:bg-ink">
        <header className="flex flex-col gap-1">
          <h2 id="catalog-review-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t("catalog.reviewTitle")}
          </h2>
          <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400">{t("catalog.reviewSubtitle")}</p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {error && !catalog && (
            <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-950/50 dark:text-red-400">
              {error}
            </div>
          )}
          {!catalog && !error && <p className="p-3 text-sm text-gray-500">{t("catalog.loading")}</p>}

          {catalog && (
            <ol className="flex flex-col gap-3">
              {designs
                .slice()
                .sort((a, b) => a.slide_index - b.slide_index)
                .map((design) => (
                  <li
                    key={design.design_id}
                    className={`rounded-lg border p-3 ${
                      design.usable
                        ? "border-gray-200 bg-white dark:border-gray-800 dark:bg-slate-900/40"
                        : "border-amber-300 bg-amber-50/40 dark:border-amber-800/60 dark:bg-amber-950/20"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        {t("catalog.slideLabel", { n: design.slide_index + 1 })}
                      </span>
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                          design.usable
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/60 dark:text-emerald-300"
                            : "border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/60 dark:text-amber-300"
                        }`}
                      >
                        {t(design.usable ? "catalog.designUsable" : "catalog.designUnusable")}
                      </span>
                    </div>

                    <label className="mt-2 flex flex-col gap-1 text-xs">
                      <span className="font-medium text-gray-600 dark:text-gray-300">{t("catalog.role")}</span>
                      <input
                        value={design.role}
                        onChange={(e) => updateRole(design.design_id, e.target.value)}
                        className="rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs text-gray-800 focus:border-accent focus:outline-none dark:border-gray-700 dark:bg-slate-900 dark:text-gray-100"
                      />
                    </label>

                    {!design.usable && design.reason && (
                      <p className="mt-1.5 text-[11px] leading-snug text-amber-700 dark:text-amber-300">{design.reason}</p>
                    )}

                    {design.anchors.length > 0 && (
                      <div className="mt-2 flex flex-col gap-1.5">
                        <span className="text-[11px] text-gray-400">
                          {t("catalog.capacity", { n: design.capacity })} · {t("catalog.anchorCount", { n: design.anchors.length })}
                        </span>
                        <ul className="flex flex-col gap-1.5">
                          {design.anchors.map((anchor) => (
                            <li
                              key={anchor.anchor_id}
                              className="flex flex-col gap-1 rounded border border-gray-100 bg-gray-50/60 p-2 dark:border-gray-800 dark:bg-slate-950/40 sm:flex-row sm:items-center sm:gap-2"
                            >
                              <input
                                value={anchor.purpose}
                                onChange={(e) => updateAnchorPurpose(design.design_id, anchor.anchor_id, e.target.value)}
                                aria-label={t("catalog.anchorPurpose")}
                                className="w-40 shrink-0 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[11px] font-mono text-gray-700 focus:border-accent focus:outline-none dark:border-gray-700 dark:bg-slate-900 dark:text-gray-200"
                              />
                              <span className="min-w-0 flex-1 truncate text-[11px] text-gray-500 dark:text-gray-400" title={anchor.current_text}>
                                {anchor.current_text || "—"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </li>
                ))}
            </ol>
          )}
        </div>

        {error && catalog && (
          <div role="alert" className="rounded-lg bg-red-50 p-2 text-xs text-red-600 dark:bg-red-950/50 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
          <button type="button" onClick={onCancel} disabled={busy} className="btn-ghost text-sm">
            {t("catalog.close")}
          </button>
          <button type="button" onClick={approve} disabled={busy || !catalog} className="btn-primary text-sm">
            {busy ? t("catalog.approving") : t("catalog.approve")}
          </button>
        </div>
      </div>
    </div>
  );
}
