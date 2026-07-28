import { expect, test } from "@playwright/test";

import { collectFailedRequests } from "../fixtures";

/**
 * Presenton serves at /editor on the same origin, and the deep link opens a deck.
 *
 * Covers T-1.1 and T-1.2, both of which are still BLOCKED on vendoring the Presenton
 * source (TD-05 / TD-06). These specs are written now so the work has a target that
 * can fail; they SKIP rather than pass when /editor is unreachable, because a smoke
 * suite that silently reports green on a missing feature is the exact failure mode
 * the deleted regex script embodied.
 */
test.describe("editor", () => {
  test.beforeEach(async ({ page }) => {
    const res = await page.request.get("/editor", { failOnStatusCode: false });
    test.skip(
      res.status() >= 400,
      `/editor returned ${res.status()} — Presenton is not vendored/served yet (TD-05).`,
    );
  });

  test("serves the Presenton UI at 200", async ({ page }) => {
    const res = await page.request.get("/editor");

    expect(res.status()).toBe(200);
  });

  test("loads its assets from /editor/_next with no 404s", async ({ page }) => {
    const failures = collectFailedRequests(page);

    await page.goto("/editor");
    await page.waitForLoadState("networkidle");

    // The whole point of build-time basePath: the /_next collision between two
    // Next.js apps on one origin stops existing rather than being arbitrated.
    expect(failures).toEqual([]);
  });

  test("leaves the NoteAI frontend intact", async ({ page }) => {
    const failures = collectFailedRequests(page);

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("nav")).toBeVisible();
    expect(failures.filter((f) => f.includes("/_next"))).toEqual([]);
  });

  test("the editor deep link resolves to a real deck", async ({ page }) => {
    // T-1.2: the client was sending Generation.id, a Postgres UUID Presenton has
    // never seen. The backend must hand over a URL, not an engine identifier.
    const generations = await (await page.request.get("/api/v1/generations")).json();
    const ready = (generations as Array<{ status: string; editor_url?: string }>).find(
      (g) => g.status === "ready",
    );
    test.skip(!ready, "no ready deck to open");

    expect(ready?.editor_url, "GenerationResponse should expose editor_url (T-1.2)").toBeTruthy();

    const res = await page.request.get(ready!.editor_url!, { failOnStatusCode: false });
    expect(res.status()).toBe(200);
  });
});
