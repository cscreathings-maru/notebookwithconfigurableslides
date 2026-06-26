"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";
import { visibleNav } from "@/lib/nav";

/** Role-aware sidebar navigation. */
export function Nav() {
  const { me, signOut } = useAuth();
  if (!me) return null;

  const items = visibleNav(me.role);

  return (
    <nav aria-label="Main navigation" className="flex h-full flex-col gap-1 p-4">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-wide text-ink/50">Tenant</p>
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
              {item.label}
            </Link>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={signOut}
        className="mt-auto rounded-lg px-3 py-2 text-left text-sm text-ink/60 transition-colors hover:bg-ink/5 hover:text-ink"
      >
        Sign out
      </button>
    </nav>
  );
}
