"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import type { RegistryStatus } from "@/services/api";

const STYLES: Record<RegistryStatus, string> = {
  draft: "bg-ink/10 text-ink/70",
  approved: "bg-accent/15 text-accent",
  archived: "bg-ink/5 text-ink/40 line-through",
};

export function StatusBadge({ status }: { status: RegistryStatus }) {
  const t = useT();
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {t(`status.registry.${status}` as MessageKey)}
    </span>
  );
}
