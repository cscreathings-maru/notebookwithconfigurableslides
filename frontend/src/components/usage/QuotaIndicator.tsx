"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { QuotaStatus } from "@/services/api";

export function QuotaIndicator({ quota }: { quota: QuotaStatus }) {
  const t = useT();
  const unlimited = quota.monthly_limit <= 0;
  const pct = unlimited
    ? 0
    : Math.min(100, Math.round((quota.used_this_month / quota.monthly_limit) * 100));
  const danger = !unlimited && pct >= 100;
  const warn = !unlimited && pct >= 80 && pct < 100;

  return (
    <div className="rounded-2xl border border-ink/10 bg-white p-5">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium text-ink">{t("usage.quotaTitle")}</p>
        <p className="text-xs text-ink/50">
          {unlimited
            ? t("usage.quotaUnlimited")
            : t("usage.quotaUsed", {
                used: quota.used_this_month,
                limit: quota.monthly_limit,
              })}
        </p>
      </div>
      {!unlimited && (
        <>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-ink/10">
            <div
              className={`h-full rounded-full ${
                danger ? "bg-red-500" : warn ? "bg-amber-500" : "bg-accent"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p
            className={`mt-2 text-xs ${
              danger ? "text-red-600" : warn ? "text-amber-600" : "text-ink/50"
            }`}
          >
            {danger
              ? t("usage.quotaReached")
              : t("usage.quotaRemaining", { remaining: quota.remaining ?? 0 })}
          </p>
        </>
      )}
    </div>
  );
}
