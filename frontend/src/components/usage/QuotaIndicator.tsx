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
    <div className="card shadow-sm p-6 bg-white border border-gray-100">
      <div className="flex items-baseline justify-between mb-4">
        <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-gray-400">
            <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
          {t("usage.quotaTitle")}
        </h3>
        <p className="text-sm text-gray-500 font-medium">
          {unlimited
            ? t("usage.quotaUnlimited")
            : t("usage.quotaUsed", {
                used: quota.used_this_month,
                limit: quota.monthly_limit,
              })}
        </p>
      </div>
      {!unlimited && (
        <div className="space-y-3">
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-100 shadow-inner">
            <div
              className={`h-full rounded-full transition-all duration-1000 ease-out ${
                danger ? "bg-red-500" : warn ? "bg-amber-500" : "bg-accent"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p
            className={`text-sm font-medium ${
              danger ? "text-red-600" : warn ? "text-amber-600" : "text-gray-500"
            }`}
          >
            {danger
              ? t("usage.quotaReached")
              : t("usage.quotaRemaining", { remaining: quota.remaining ?? 0 })}
          </p>
        </div>
      )}
    </div>
  );
}
