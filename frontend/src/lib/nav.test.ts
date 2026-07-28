/**
 * T-2.5: the nav mirrors backend RBAC. It is not the enforcement point, but showing
 * an admin-only link to a viewer produces a 403 the user cannot explain.
 */

import { describe, expect, it } from "vitest";

import { NAV_ITEMS, visibleNav } from "@/lib/nav";

const hrefs = (role: Parameters<typeof visibleNav>[0]) =>
  visibleNav(role).map((item) => item.href);

describe("role gating", () => {
  it("shows a viewer only the viewer-level surfaces", () => {
    // Act
    const visible = visibleNav("viewer");

    // Assert
    expect(visible.every((item) => item.minRole === "viewer")).toBe(true);
    expect(hrefs("viewer")).toContain("/projects");
  });

  it("hides admin surfaces from an author", () => {
    // Assert
    expect(hrefs("author")).not.toContain("/templates");
    expect(hrefs("author")).not.toContain("/usage");
  });

  it("gives an admin everything an author sees", () => {
    // Act
    const admin = new Set(hrefs("admin"));

    // Assert -- roles are cumulative, not disjoint
    for (const href of hrefs("author")) {
      expect(admin.has(href)).toBe(true);
    }
  });

  it("never shows more than the full item list", () => {
    expect(visibleNav("admin").length).toBeLessThanOrEqual(NAV_ITEMS.length);
  });
});

describe("item model", () => {
  it("gives every item a route and a translatable label", () => {
    for (const item of NAV_ITEMS) {
      expect(item.href.startsWith("/")).toBe(true);
      expect(item.labelKey).toBeTruthy();
    }
  });

  it("marks the SaaS-only surfaces for hiding in lite mode", () => {
    // Metering and per-tenant BYOK do not exist in the single-tenant demo build.
    const hidden = NAV_ITEMS.filter((i) => i.hideInLite).map((i) => i.href);

    expect(hidden).toEqual(expect.arrayContaining(["/usage", "/settings/llm"]));
  });

  it("keeps Projects visible in lite mode", () => {
    // The core surface must survive the lite build whatever else is stripped.
    const projects = NAV_ITEMS.find((i) => i.href === "/projects");

    expect(projects?.hideInLite).toBeFalsy();
  });
});
