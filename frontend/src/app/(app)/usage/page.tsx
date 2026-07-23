"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { QuotaIndicator } from "@/components/usage/QuotaIndicator";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { api, type AuditEvent, type UsageReport } from "@/services/api";

function money(value: string | number): string {
  return `$${Number(value).toFixed(4)}`;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-ink/10 bg-white p-5">
      <p className="text-xs uppercase tracking-wide text-ink/50">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
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
    return <p className="text-sm text-ink/60">{t("usage.adminOnly")}</p>;
  }

  return (
    <section aria-labelledby="usage-heading" className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 id="usage-heading" className="text-2xl font-semibold text-ink">
            {t("usage.title")}
          </h1>
          <p className="mt-1 text-sm text-ink/60">{t("usage.subtitle")}</p>
        </div>
        <div className="flex items-end gap-2 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink/50">{t("usage.from")}</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-lg border border-ink/15 px-2 py-1 focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink/50">{t("usage.to")}</span>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-lg border border-ink/15 px-2 py-1 focus:border-accent focus:outline-none"
            />
          </label>
        </div>
      </header>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {usage && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label={t("usage.generations")} value={String(usage.tenant.generations)} />
            <StatCard label={t("usage.tokensIn")} value={usage.tenant.tokens_in.toLocaleString()} />
            <StatCard label={t("usage.tokensOut")} value={usage.tenant.tokens_out.toLocaleString()} />
            <StatCard label={t("usage.estCost")} value={money(usage.tenant.cost_estimate)} />
          </div>

          <QuotaIndicator quota={usage.quota} />

          <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white">
            <h2 className="border-b border-ink/5 px-4 py-3 text-sm font-semibold text-ink">
              {t("usage.byUser")}
            </h2>
            <table className="w-full text-sm">
              <thead className="bg-ink/[0.03] text-left text-xs uppercase tracking-wide text-ink/50">
                <tr>
                  <th className="px-4 py-2">{t("usage.colUser")}</th>
                  <th className="px-4 py-2">{t("usage.generations")}</th>
                  <th className="px-4 py-2">{t("usage.tokensIn")}</th>
                  <th className="px-4 py-2">{t("usage.tokensOut")}</th>
                  <th className="px-4 py-2">{t("usage.estCost")}</th>
                </tr>
              </thead>
              <tbody>
                {usage.per_user.map((u) => (
                  <tr key={u.user_id ?? "system"} className="border-t border-ink/5">
                    <td className="px-4 py-2 text-ink/80">{u.email ?? t("usage.system")}</td>
                    <td className="px-4 py-2 text-ink/70">{u.generations}</td>
                    <td className="px-4 py-2 text-ink/70">{u.tokens_in.toLocaleString()}</td>
                    <td className="px-4 py-2 text-ink/70">{u.tokens_out.toLocaleString()}</td>
                    <td className="px-4 py-2 text-ink/70">{money(u.cost_estimate)}</td>
                  </tr>
                ))}
                {usage.per_user.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-ink/40">
                      {t("usage.noUsage")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white">
        <h2 className="border-b border-ink/5 px-4 py-3 text-sm font-semibold text-ink">
          {t("usage.auditLog")}
        </h2>
        <table className="w-full text-xs">
          <thead className="bg-ink/[0.03] text-left uppercase tracking-wide text-ink/50">
            <tr>
              <th className="px-4 py-2">{t("usage.colWhen")}</th>
              <th className="px-4 py-2">{t("usage.colAction")}</th>
              <th className="px-4 py-2">{t("usage.colResource")}</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((e) => (
              <tr key={e.id} className="border-t border-ink/5">
                <td className="px-4 py-2 text-ink/60">
                  {new Date(e.created_at).toLocaleString(locale === "id" ? "id-ID" : "en-US")}
                </td>
                <td className="px-4 py-2 font-medium text-ink/80">{e.action}</td>
                <td className="px-4 py-2 font-mono text-[11px] text-ink/50">
                  {JSON.stringify(e.resource)}
                </td>
              </tr>
            ))}
            {audit.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-ink/40">
                  {t("usage.noAudit")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
