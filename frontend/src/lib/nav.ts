/**
 * Navigation model with per-item minimum role. The nav renders only what the
 * current role may access — a UX mirror of the backend RBAC (which remains the
 * real enforcement point).
 */

import type { Role } from "@/services/api";

export interface NavItem {
  href: string;
  label: string;
  minRole: Role;
}

const ROLE_RANK: Record<Role, number> = { viewer: 0, author: 1, admin: 2 };

export const NAV_ITEMS: NavItem[] = [
  { href: "/projects", label: "Projects", minRole: "viewer" },
  { href: "/profiles", label: "Profiles", minRole: "admin" },
  { href: "/templates", label: "Templates", minRole: "admin" },
  { href: "/usage", label: "Usage & Audit", minRole: "admin" },
  { href: "/settings/llm", label: "LLM Provider", minRole: "admin" },
];

export function visibleNav(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => ROLE_RANK[role] >= ROLE_RANK[item.minRole]);
}
