/**
 * Navigation model with per-item minimum role. The nav renders only what the
 * current role may access — a UX mirror of the backend RBAC (which remains the
 * real enforcement point).
 */

import { config } from "@/lib/config";
import type { Role } from "@/services/api";

export interface NavItem {
  href: string;
  label: string;
  minRole: Role;
  // Hidden in lite mode: SaaS-only surfaces (metering / per-tenant BYOK) that the
  // demo build removes. Core features (Projects, Profiles, Templates) stay.
  hideInLite?: boolean;
}

const ROLE_RANK: Record<Role, number> = { viewer: 0, author: 1, admin: 2 };

export const NAV_ITEMS: NavItem[] = [
  { href: "/projects", label: "Projects", minRole: "viewer" },
  // Profiles drive the governed outline pipeline, which the freeform lite demo
  // does not use — hide it there. Templates stay for custom deck themes.
  { href: "/profiles", label: "Profiles", minRole: "admin", hideInLite: true },
  { href: "/templates", label: "Templates", minRole: "admin" },
  { href: "/usage", label: "Usage & Audit", minRole: "admin", hideInLite: true },
  { href: "/settings/llm", label: "LLM Provider", minRole: "admin", hideInLite: true },
];

export function visibleNav(role: Role): NavItem[] {
  return NAV_ITEMS.filter(
    (item) =>
      ROLE_RANK[role] >= ROLE_RANK[item.minRole] && !(config.liteMode && item.hideInLite),
  );
}
