"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { CatalogReview } from "@/components/registry/CatalogReview";
import { CatalogStatusBadge } from "@/components/registry/CatalogStatusBadge";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Template } from "@/services/api";

/**
 * TM-6: the 4-section brand-token configurator (colours, font, logo, aspect ratio,
 * header/footer text) is gone. None of it ever reached the renderer (TD-07) --
 * the uploaded .pptx is the only thing that determines branding. `brand_tokens`
 * stays on the API/model (not deleted -- see TD-07's re-classification), this
 * page just stops presenting a form that implies it does something.
 *
 * LD-3/L3 (Phase C cutover): a template's usable state is entirely
 * `catalog_status` + `catalog_reviewed` now -- the old geometric
 * `inspection_status`/`reinspect` (RM-3) is gone. Cataloguing is an async
 * job (an LLM call cannot be inline), and `status` only becomes `approved`
 * once an admin reviews the finished catalog.
 */
export default function TemplatesPage() {
  const { me } = useAuth();
  const t = useT();
  const [templates, setTemplates] = useState<Template[]>([]);

  const [name, setName] = useState("");
  const [pptx, setPptx] = useState<File | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [recataloguing, setRecataloguing] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listTemplates().then(setTemplates).catch(() => setTemplates([]));
  }, []);

  useEffect(() => load(), [load]);

  // Cataloguing finishes in a worker, minutes after the request that started
  // it, and nothing pushes that to the browser. Without this the page holds
  // whatever it fetched on mount: a template that finished long ago still
  // reads "cataloguing…", which is indistinguishable from a hang and is
  // exactly how an hour got lost (2026-08-23). Only polls while something is
  // actually in flight, so an idle Templates page makes no requests at all.
  const isCataloguing = templates.some((tpl) => tpl.catalog_status === "cataloguing");
  useEffect(() => {
    if (!isCataloguing) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [isCataloguing, load]);

  if (me && me.role !== "admin") {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-12 h-12 text-gray-400 mb-4">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t("templates.adminOnly")}</h2>
        <p className="text-gray-500 max-w-md">You do not have permission to access the Template Builder. Please contact an administrator.</p>
      </div>
    );
  }

  const resetForm = () => {
    setName("");
    setPptx(null);
    setShowCreate(false);
  };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pptx) {
      setError(t("templates.pptxRequired"));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.createTemplate({ name, brand_tokens: {}, pptx });
      resetForm();
      load();
      // Cataloguing is async (LD-3) -- the create response never carries a
      // terminal outcome to check here; `catalog_status` on the reloaded row
      // (and eventually `catalog_error` if it fails) is the honest signal.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  // LD-3: re-run LLM cataloguing against the stored .pptx -- async, so this
  // only starts the job. The poller above then follows it to completion; the
  // backend refuses to stack a second run on top of one already in flight,
  // so an impatient double-click costs nothing.
  const recatalog = async (id: string) => {
    setError(null);
    setRecataloguing(id);
    try {
      await api.recatalogTemplate(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("catalog.recatalogFailed"));
    } finally {
      setRecataloguing(null);
    }
  };

  const deleteTemplate = async (id: string) => {
    if (confirmingDelete !== id) {
      // First click: ask for confirmation rather than deleting immediately --
      // this is irreversible on the engine side too (TM-5).
      setConfirmingDelete(id);
      return;
    }
    setConfirmingDelete(null);
    setError(null);
    try {
      await api.deleteTemplate(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.deleteFailed"));
    }
  };

  return (
    <section aria-labelledby="templates-heading" className="flex flex-col gap-8 animate-fade-in">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 id="templates-heading" className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
            {t("templates.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500 max-w-2xl">{t("templates.subtitle")}</p>
        </div>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary shrink-0 self-start sm:self-auto shadow-sm"
          >
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t("templates.new")}
          </button>
        )}
      </header>

      {/* Page-level, not nested in the create form: reregister/delete errors
          fire with the form closed, and previously had nowhere to render. */}
      {error && (
        <div role="alert" className="rounded-lg bg-red-50 dark:bg-red-950/50 p-4 text-sm text-red-600 dark:text-red-400 flex items-start gap-3 border border-red-200 dark:border-red-800">
          <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <p>{error}</p>
        </div>
      )}

      {showCreate && (
        <div className="card animate-slide-up border border-accent/20 overflow-hidden shadow-elevated bg-white dark:bg-ink">
          <div className="bg-accent-faint dark:bg-blue-950/40 px-6 py-4 border-b border-accent/10">
            <h2 className="text-lg font-semibold text-accent dark:text-blue-400">{t("templates.new")}</h2>
            <p className="text-sm text-accent/80 dark:text-blue-300/80 mt-0.5">
              {t("templates.newSubtitle")}
            </p>
          </div>

          <form onSubmit={create} className="p-6 flex flex-col gap-6">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {t("templates.name")} <span className="text-red-500">*</span>
              </span>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Q4 Executive Report"
                className="input-field"
              />
            </label>

            <div className="bg-slate-50 dark:bg-slate-900/60 p-6 rounded-xl border-2 border-dashed border-blue-200 dark:border-blue-800/60 flex flex-col items-center justify-center text-center transition hover:border-blue-500">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-10 h-10 text-blue-600 dark:text-blue-400 mb-3">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <h3 className="font-semibold text-base text-foreground mb-1">
                {pptx ? pptx.name : t("templates.dropPptx")}
              </h3>
              <p className="text-xs text-muted-foreground max-w-md mb-4">{t("templates.dropPptxHint")}</p>
              <input
                type="file"
                accept=".pptx"
                onChange={(e) => setPptx(e.target.files?.[0] ?? null)}
                className="hidden"
                id="pptx-upload"
              />
              <button
                type="button"
                onClick={() => document.getElementById("pptx-upload")?.click()}
                className="btn-primary text-xs py-2 px-5 shadow-sm"
              >
                {pptx ? t("templates.changeFile") : t("templates.selectFile")}
              </button>
            </div>

            <div className="flex items-center gap-3 pt-2 border-t border-gray-100 dark:border-gray-800 justify-end">
              <button type="button" onClick={resetForm} className="btn-ghost">
                {t("common.cancel")}
              </button>
              <button type="submit" disabled={busy || !name || !pptx} className="btn-primary min-w-[160px] shadow-sm font-semibold">
                {busy ? t("templates.creating") : t("templates.create")}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card overflow-hidden bg-white dark:bg-ink">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-slate-900 border-b border-gray-100 dark:border-gray-800 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              <tr>
                <th className="px-6 py-4">{t("templates.name")}</th>
                <th className="px-6 py-4">{t("templates.colVersion")}</th>
                <th className="px-6 py-4">{t("templates.colStatus")}</th>
                <th className="px-6 py-4">{t("templates.colCatalog")}</th>
                <th className="px-6 py-4 text-right">{t("templates.colActions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {templates.map((tpl) => (
                <tr key={`${tpl.id}-${tpl.version}`} className="hover:bg-gray-50/50 dark:hover:bg-slate-900/50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{tpl.name}</div>
                  </td>
                  <td className="px-6 py-4 text-gray-600 dark:text-gray-400 font-mono">v{tpl.version}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={tpl.status} />
                  </td>
                  <td className="px-6 py-4">
                    <CatalogStatusBadge
                      status={tpl.catalog_status}
                      error={tpl.catalog_error}
                      reviewed={tpl.catalog_reviewed}
                    />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {tpl.catalog_status === "ready" && (
                        <button
                          type="button"
                          onClick={() => setReviewingId(tpl.id)}
                          className={`py-1.5 px-3 text-xs flex items-center gap-1 rounded-lg border transition ${
                            tpl.catalog_reviewed
                              ? "btn-secondary"
                              : "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-300"
                          }`}
                        >
                          {t("catalog.review")}
                        </button>
                      )}
                      {/* Offered while `cataloguing` too, not only on `failed`:
                          a job whose worker died mid-flight leaves the row at
                          `cataloguing` forever, and gating this button on
                          `failed` meant the only escape was a shell on the
                          server (hit in production 2026-08-17). An admin can
                          always restart a run they believe is stuck. */}
                      {(tpl.catalog_status === "failed" || tpl.catalog_status === "cataloguing") &&
                        tpl.has_pptx && (
                          <button
                            type="button"
                            onClick={() => recatalog(tpl.id)}
                            disabled={recataloguing === tpl.id}
                            className={`py-1.5 px-3 text-xs flex items-center gap-1 rounded-lg border transition disabled:opacity-50 ${
                              tpl.catalog_status === "failed"
                                ? "btn-secondary border-red-300 text-red-700 hover:bg-red-50 dark:text-red-300"
                                : "btn-secondary"
                            }`}
                            title={tpl.catalog_error ?? t("catalog.recatalogStuckHint")}
                          >
                            ↻ {recataloguing === tpl.id ? t("catalog.recataloguing") : t("catalog.recatalog")}
                          </button>
                        )}
                      <button
                        type="button"
                        onClick={() => deleteTemplate(tpl.id)}
                        onBlur={() => setConfirmingDelete((cur) => (cur === tpl.id ? null : cur))}
                        className={`py-1.5 px-3 text-xs flex items-center gap-1 rounded-lg border transition ${
                          confirmingDelete === tpl.id
                            ? "border-red-500 bg-red-600 text-white hover:bg-red-700"
                            : "btn-secondary hover:border-red-400 hover:text-red-600"
                        }`}
                      >
                        {confirmingDelete === tpl.id ? t("templates.confirmDelete") : t("templates.delete")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {templates.length === 0 && !showCreate && (
                <tr>
                  <td colSpan={5} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center justify-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950/60 mb-3 text-blue-600 dark:text-blue-400">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6">
                          <path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4" />
                          <polyline points="14 2 14 8 20 8" />
                          <path d="M2 15h10" />
                          <path d="M9 18l3-3-3-3" />
                        </svg>
                      </div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{t("templates.empty")}</p>
                      <button onClick={() => setShowCreate(true)} className="btn-primary mt-4 shadow-sm">
                        {t("templates.new")}
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {reviewingId && (
        <CatalogReview
          templateId={reviewingId}
          onDone={() => {
            setReviewingId(null);
            load();
          }}
          onCancel={() => setReviewingId(null)}
        />
      )}
    </section>
  );
}
