"use client";

import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import type { RegistryStatus } from "@/services/api";

const STYLES: Record<RegistryStatus, string> = {
  draft: "bg-gray-100 text-gray-700 border border-gray-200",
  approved: "bg-accent-faint text-accent border border-accent/20",
  archived: "bg-gray-50 text-gray-400 line-through border border-gray-100",
};

export function StatusBadge({ status }: { status: RegistryStatus }) {
  const t = useT();
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${STYLES[status]}`}
    >
      {t(`status.registry.${status}` as MessageKey)}
    </span>
  );
}
