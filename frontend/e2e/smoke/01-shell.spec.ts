import { expect, test } from "@playwright/test";

import { collectConsoleErrors, collectFailedRequests } from "../fixtures";

/**
 * The app loads and its own assets resolve.
 *
 * This is the journey the deleted regex script claimed to verify by checking that
 * `tailwind.config.ts` contained the string "2563EB".
 */
test.describe("shell", () => {
  test("loads with navigation and no console errors", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto("/");

    await expect(page.locator("nav")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("serves its own assets without 404s", async ({ page }) => {
    const failures = collectFailedRequests(page);

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Asset collisions are the failure mode /editor introduced: both apps are
    // Next.js and both serve /_next. The frontend must keep its own.
    expect(failures.filter((f) => f.includes("/_next"))).toEqual([]);
  });

  test("reaches the orchestrator through the proxy", async ({ page }) => {
    const res = await page.request.get("/api/v1/languages");

    expect(res.status()).toBe(200);
  });

  test("reports readiness per dependency (T-2.4)", async ({ page }) => {
    const res = await page.request.get("/api/readyz");
    const body = await res.json();

    expect(["ok", "degraded"]).toContain(body.status);
    expect(Object.keys(body.dependencies)).toEqual(
      expect.arrayContaining(["postgres", "redis", "minio"]),
    );
  });
});
