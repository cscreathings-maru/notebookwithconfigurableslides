"use client";

import Link from "next/link";

import { config } from "@/lib/config";
import { useAuth } from "@/components/AuthProvider";
import { LOCALES, type Locale } from "@/lib/i18n/config";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { visibleNav } from "@/lib/nav";

/** Role-aware sidebar navigation. */
export function Nav() {
  const { me, signOut } = useAuth();
  const { locale, setLocale } = useLocale();
  const t = useT();
  if (!me) return null;

  const items = visibleNav(me.role);

  return (
    <nav aria-label="Main navigation" className="flex h-full flex-col gap-1 p-4">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-wide text-ink/50">{t("nav.tenant")}</p>
        <p className="truncate font-semibold text-ink">{me.tenant.name}</p>
        <span className="mt-1 inline-block rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
          {me.role}
        </span>
      </div>

      <ul className="flex flex-col gap-1">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="block rounded-lg px-3 py-2 text-sm text-ink/80 transition-colors hover:bg-ink/5 hover:text-ink"
            >
              {t(item.labelKey)}
            </Link>
          </li>
        ))}
      </ul>

      <label className="mt-auto flex flex-col gap-1 pt-6 text-xs text-ink/50">
        <span className="uppercase tracking-wide">{t("nav.language")}</span>
        <select
          value={locale}
          onChange={(e) => setLocale(e.target.value as Locale)}
          className="rounded-lg border border-ink/15 px-2 py-1.5 text-sm text-ink focus:border-accent focus:outline-none"
        >
          {LOCALES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </label>

      {!config.liteMode && (
        <button
          type="button"
          onClick={signOut}
          className="mt-2 rounded-lg px-3 py-2 text-left text-sm text-ink/60 transition-colors hover:bg-ink/5 hover:text-ink"
        >
          {t("nav.signOut")}
        </button>
      )}
    </nav>
  );
}
