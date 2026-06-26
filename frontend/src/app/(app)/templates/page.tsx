"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { api, ApiError, type Template } from "@/services/api";

export default function TemplatesPage() {
  const { me } = useAuth();
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
    return <p className="text-sm text-ink/60">Templates are managed by tenant admins.</p>;
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
      setError(err instanceof ApiError ? err.message : "Failed to create template");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: string) => {
    try {
      await api.approveTemplate(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Approve failed");
    }
  };

  const inputCls =
    "rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none";

  return (
    <section aria-labelledby="templates-heading" className="flex flex-col gap-8">
      <header>
        <h1 id="templates-heading" className="text-2xl font-semibold text-ink">
          Templates
        </h1>
        <p className="mt-1 text-sm text-ink/60">
          Company templates that pin brand and structure for generation. Import a PPTX to
          register it with the generation engine.
        </p>
      </header>

      <form onSubmit={create} className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
        <h2 className="text-lg font-semibold text-ink">New template</h2>
        <div className="grid grid-cols-3 gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">Name</span>
            <input required value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">Primary color</span>
            <input value={primary} onChange={(e) => setPrimary(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/60">Font</span>
            <input value={font} onChange={(e) => setFont(e.target.value)} className={inputCls} />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Import PPTX (optional)</span>
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
          {busy ? "Creating…" : "Create template"}
        </button>
      </form>

      <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-ink/[0.03] text-left text-xs uppercase tracking-wide text-ink/50">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">PPTX</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={`${t.id}-${t.version}`} className="border-t border-ink/5">
                <td className="px-4 py-3 font-medium text-ink">{t.name}</td>
                <td className="px-4 py-3 text-ink/60">v{t.version}</td>
                <td className="px-4 py-3 text-ink/60">{t.has_pptx ? "imported" : "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={t.status} />
                </td>
                <td className="px-4 py-3 text-right">
                  {t.status === "draft" && (
                    <button
                      type="button"
                      onClick={() => approve(t.id)}
                      className="rounded-lg border border-ink/15 px-3 py-1 text-xs hover:bg-ink/5"
                    >
                      Approve
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {templates.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-ink/50">
                  No templates yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
