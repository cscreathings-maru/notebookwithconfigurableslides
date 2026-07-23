"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Template } from "@/services/api";

export default function TemplatesPage() {
  const { me } = useAuth();
  const t = useT();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [name, setName] = useState("");
  const [primary, setPrimary] = useState("#0A0A0A");
  const [font, setFont] = useState("Inter");
  const [pptx, setPptx] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.listTemplates().then(setTemplates).catch(() => setTemplates([]));
  }, []);

  useEffect(() => load(), [load]);

  if (me && me.role !== "admin") {
    return <p className="text-sm text-ink/60">{t("templates.adminOnly")}</p>;
  }

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createTemplate({
        name,
        brand_tokens: { primary, font },
        pptx,
      });
      setName("");
      setPptx(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: string) => {
    try {
      await api.approveTemplate(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.approveFailed"));
    }
  };

  const inputCls =
    "rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none";

  return (
    <section aria-labelledby="templates-heading" className="flex flex-col gap-8">
      <header>
        <h1 id="templates-heading" className="text-2xl font-semibold text-ink">
          {t("templates.title")}
        </h1>
        <p className="mt-1 text-sm text-ink/60">{t("templates.subtitle")}</p>
      </header>

      <form onSubmit={create} className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
        <h2 className="text-lg font-semibold text-ink">{t("templates.new")}</h2>
        <div className="grid grid-cols-3 gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">{t("templates.name")}</span>
            <input required value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">{t("templates.primaryColor")}</span>
            <input value={primary} onChange={(e) => setPrimary(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">{t("templates.font")}</span>
            <input value={font} onChange={(e) => setFont(e.target.value)} className={inputCls} />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("templates.importPptx")}</span>
          <input
            type="file"
            accept=".pptx"
            onChange={(e) => setPptx(e.target.files?.[0] ?? null)}
            className="text-sm text-ink/70"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="self-start rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {busy ? t("templates.creating") : t("templates.create")}
        </button>
      </form>

      <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-ink/[0.03] text-left text-xs uppercase tracking-wide text-ink/50">
            <tr>
              <th className="px-4 py-3">{t("templates.name")}</th>
              <th className="px-4 py-3">{t("templates.colVersion")}</th>
              <th className="px-4 py-3">{t("templates.colPptx")}</th>
              <th className="px-4 py-3">{t("templates.colStatus")}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {templates.map((tpl) => (
              <tr key={`${tpl.id}-${tpl.version}`} className="border-t border-ink/5">
                <td className="px-4 py-3 font-medium text-ink">{tpl.name}</td>
                <td className="px-4 py-3 text-ink/60">v{tpl.version}</td>
                <td className="px-4 py-3 text-ink/60">
                  {tpl.has_pptx ? t("templates.imported") : "—"}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={tpl.status} />
                </td>
                <td className="px-4 py-3 text-right">
                  {tpl.status === "draft" && (
                    <button
                      type="button"
                      onClick={() => approve(tpl.id)}
                      className="rounded-lg border border-ink/15 px-3 py-1 text-xs hover:bg-ink/5"
                    >
                      {t("common.approve")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {templates.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-ink/50">
                  {t("templates.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
