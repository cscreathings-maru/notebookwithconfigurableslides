"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { QuotaIndicator } from "@/components/usage/QuotaIndicator";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { api, type AuditEvent, type UsageReport } from "@/services/api";

function money(value: string | number): string {
  return `$${Number(value).toFixed(4)}`;
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="card shadow-sm border border-gray-100 bg-white p-6 flex flex-col gap-2 relative overflow-hidden group hover:border-accent/30 transition-colors">
      <div className="absolute right-0 top-0 p-4 text-gray-100 group-hover:text-accent/5 transition-colors">
        {icon}
      </div>
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 relative z-10">{label}</p>
      <p className="text-3xl font-bold tracking-tight text-gray-900 relative z-10">{value}</p>
    </div>
  );
}

export default function UsagePage() {
  const { me } = useAuth();
  const { locale } = useLocale();
  const t = useT();
  const [usage, setUsage] = useState<UsageReport | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    Promise.all([
      api.getUsage(from || undefined, to || undefined),
      api.getAudit(from || undefined, to || undefined),
    ])
      .then(([u, a]) => {
        setUsage(u);
        setAudit(a);
      })
      .catch(() => setError(t("usage.loadFailed")));
  }, [from, to, t]);

  useEffect(() => load(), [load]);

  if (me && me.role !== "admin") {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-12 h-12 text-gray-400 mb-4">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t("usage.adminOnly")}</h2>
        <p className="text-gray-500 max-w-md">You do not have permission to access the Usage & Audit dashboard. Please contact an administrator.</p>
      </div>
    );
  }

  return (
    <section aria-labelledby="usage-heading" className="flex flex-col gap-8 animate-fade-in">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h1 id="usage-heading" className="text-3xl font-bold tracking-tight text-gray-900">
            {t("usage.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500">{t("usage.subtitle")}</p>
        </div>
        <div className="flex items-end gap-4 text-sm bg-gray-50 p-3 rounded-xl border border-gray-100">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{t("usage.from")}</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="input-field py-1.5 px-3 w-36 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{t("usage.to")}</span>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="input-field py-1.5 px-3 w-36 text-sm"
            />
          </label>
        </div>
      </header>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-600 flex items-start gap-3">
          <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <p>{error}</p>
        </div>
      )}

      {usage && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard 
              label={t("usage.generations")} 
              value={String(usage.tenant.generations)} 
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-16 h-16"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" /></svg>}
            />
            <StatCard 
              label={t("usage.tokensIn")} 
              value={usage.tenant.tokens_in.toLocaleString()} 
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-16 h-16"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>}
            />
            <StatCard 
              label={t("usage.tokensOut")} 
              value={usage.tenant.tokens_out.toLocaleString()} 
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-16 h-16"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>}
            />
            <StatCard 
              label={t("usage.estCost")} 
              value={money(usage.tenant.cost_estimate)} 
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-16 h-16"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></svg>}
            />
          </div>

          <QuotaIndicator quota={usage.quota} />

          <div className="card overflow-hidden">
            <h2 className="bg-gray-50 border-b border-gray-100 px-6 py-4 text-sm font-semibold text-gray-900 uppercase tracking-wider">
              {t("usage.byUser")}
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-white border-b border-gray-100 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <tr>
                    <th className="px-6 py-4">{t("usage.colUser")}</th>
                    <th className="px-6 py-4">{t("usage.generations")}</th>
                    <th className="px-6 py-4">{t("usage.tokensIn")}</th>
                    <th className="px-6 py-4">{t("usage.tokensOut")}</th>
                    <th className="px-6 py-4">{t("usage.estCost")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50 bg-white">
                  {usage.per_user.map((u) => (
                    <tr key={u.user_id ?? "system"} className="hover:bg-gray-50/50 transition-colors">
                      <td className="px-6 py-4 font-medium text-gray-900">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-accent/10 text-accent flex items-center justify-center font-bold text-xs">
                            {u.email ? u.email.substring(0, 2).toUpperCase() : "SY"}
                          </div>
                          {u.email ?? t("usage.system")}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-600">{u.generations}</td>
                      <td className="px-6 py-4 text-gray-600">{u.tokens_in.toLocaleString()}</td>
                      <td className="px-6 py-4 text-gray-600">{u.tokens_out.toLocaleString()}</td>
                      <td className="px-6 py-4 font-medium text-gray-700">{money(u.cost_estimate)}</td>
                    </tr>
                  ))}
                  {usage.per_user.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                        {t("usage.noUsage")}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <div className="card overflow-hidden">
        <h2 className="bg-gray-50 border-b border-gray-100 px-6 py-4 text-sm font-semibold text-gray-900 uppercase tracking-wider">
          {t("usage.auditLog")}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-white border-b border-gray-100 text-left font-semibold uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-6 py-4">{t("usage.colWhen")}</th>
                <th className="px-6 py-4">{t("usage.colAction")}</th>
                <th className="px-6 py-4">{t("usage.colResource")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 bg-white">
              {audit.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-3 whitespace-nowrap text-gray-500">
                    {new Date(e.created_at).toLocaleString(locale === "id" ? "id-ID" : "en-US")}
                  </td>
                  <td className="px-6 py-3 font-medium text-gray-900">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                      {e.action}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-mono text-[11px] text-gray-500 break-all">
                    {JSON.stringify(e.resource)}
                  </td>
                </tr>
              ))}
              {audit.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-6 py-12 text-center text-gray-500 text-sm">
                    {t("usage.noAudit")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
